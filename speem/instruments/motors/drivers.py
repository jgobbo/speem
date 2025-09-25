import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum, auto
from warnings import warn

from pymdrive import MdriveAxis, MdriveComm
from pymdrive import emergency_stop as mdrive_emergency_stop

from automation1 import (
    Controller,
    StatusItemConfiguration,
    AxisStatusItem,
    AxisStatus,
    AxisParameterId,
    SystemParameterId,
    AxisDataSignal,
    AxisFault,
    ControllerOperationException,
)

__all__ = [
    "MotorDriver",
    "MdriveDriver",
    "Automation1Driver",
    "VirtualAxisDriver",
    "emergency_stop",
]


class MoveIntoLimitError(Exception):
    """Exception raised when an axis attempts to move into an active limit."""

    def __init__(
        self,
        axis: str,
        active_limit: str,
        soft_limits: tuple[float, float],
        position: float,
    ):
        self.axis = axis
        self.message = (
            f"Attempted to move {axis} into its {active_limit}. {axis} has "
            f"{soft_limits = } and was commanded to move to {position}."
        )
        super().__init__(self.message)


# TODO : implement hard limits which can be calculated from other axis positions
# i.e. x and y hard limits depend on Y position and Theta to prevent crashing into ToF
class MotorDriver(ABC):
    axis: str
    unit: str
    position: float
    speed: float
    soft_limits: tuple[float, float]
    default_soft_limits: tuple[float, float] | None = None

    @abstractmethod
    def enable(self) -> None: ...

    @abstractmethod
    def disable(self) -> None: ...

    @abstractmethod
    async def get_position(self) -> float: ...

    @abstractmethod
    async def move_relative(self, distance: float, speed: float = None) -> None: ...

    @abstractmethod
    async def move_absolute(self, position: float, speed: float = None) -> None: ...

    @abstractmethod
    async def abort_move(self) -> None: ...

    @abstractmethod
    async def is_moving(self) -> bool: ...

    async def wait_for_motion_done(self) -> None:
        while await self.is_moving() is True:
            await asyncio.sleep(0.25)

    @abstractmethod
    async def home(self) -> None: ...

    @abstractmethod
    async def is_homed(self) -> bool: ...


class HomeDirection(StrEnum):
    NEGATIVE = auto()
    POSITIVE = auto()
    MANUAL = auto()


MDRIVE_COMM = MdriveComm("COM3")


class MdriveDriver(MdriveAxis, MotorDriver):
    axis: str
    unit: str
    unit_ratio: float
    home_direction: HomeDirection
    soft_limits: tuple[float, float]
    default_soft_limits: tuple[float, float]

    position: float = None
    last_speed: float = None

    def __init__(
        self,
        axis: str,
        unit: str,
        unit_ratio: float,
        home_direction: HomeDirection,
        speed: float,
        default_soft_limits: tuple[float, float],
    ) -> None:
        super().__init__(comm=MDRIVE_COMM, name=axis)
        self.axis = axis
        self.unit = unit
        self.unit_ratio = unit_ratio
        self.home_direction = home_direction

        self.speed = speed
        self.check_speed(speed)

        self.default_soft_limits = default_soft_limits
        self.soft_limits = default_soft_limits

    def clamp_position(self, position: float) -> float:
        if position > self.soft_limits[1]:
            return self.soft_limits[1]
        elif position < self.soft_limits[0]:
            return self.soft_limits[0]
        return position

    def clamp_distance(self, distance: float) -> float:
        if (self.position + distance) > self.soft_limits[1]:
            return self.soft_limits[1] - self.position
        elif (self.position + distance) < self.soft_limits[0]:
            return self.soft_limits[0] - self.position
        return distance

    async def get_position(self) -> float:
        self.position = await super().get_position() / self.unit_ratio
        return self.position

    def check_speed(self, speed: float) -> None:
        if speed != self.last_speed:
            self.set_velocity(round(speed * self.unit_ratio))
            self.last_speed = speed

    async def move_relative(self, distance: float, speed: float = None) -> None:
        if await self.is_moving():
            warn(f"Move command on {self.axis} while moving.")
            return

        speed = self.speed if speed is None else speed
        self.check_speed(speed)

        clamped_distance = self.clamp_distance(distance)
        await super().move_relative(int(clamped_distance * self.unit_ratio))
        self.position += clamped_distance

    async def move_absolute(self, position: float, speed: float = None) -> None:
        speed = self.speed if speed is None else speed
        self.check_speed(speed)

        clamped_position = self.clamp_position(position)
        print(f"moving real {self.axis} to {clamped_position}")
        await super().move_absolute(int(clamped_position * self.unit_ratio))
        self.position = clamped_position

    async def abort_move(self) -> None:
        await super().abort_move()
        await self.wait_for_motion_done()
        await self.get_position()

    async def home(self) -> None:
        if self.home_direction == HomeDirection.NEGATIVE:
            await self.home_negative()
        elif self.home_direction == HomeDirection.POSITIVE:
            await self.home_positive()

        await self.get_position()


CONTROLLER = Controller.connect_usb()

FAULT_MASK = 0x50C40FFF
FAULT_MASK_DECEL = 0x11060C3C
FAULT_MASK_DISABLE = 0x50CE0BC3

EMERGENCY_STOP_INPUT_NUMBER = 0
VIRTUAL_BINARY_INPUT_TYPE = 100663296
CONTROLLER.runtime.commands.io.virtualbinaryinputset(EMERGENCY_STOP_INPUT_NUMBER, True)
CONTROLLER.runtime.parameters.system[
    SystemParameterId.SoftwareEmergencyStopInput
].value = (VIRTUAL_BINARY_INPUT_TYPE + EMERGENCY_STOP_INPUT_NUMBER)


class Automation1Driver(MotorDriver):
    axis: str
    unit: str
    unit_ratio: float
    home_direction: HomeDirection
    soft_limits: tuple[float, float]
    default_soft_limits: tuple[float, float]

    homed: bool = False
    position: float = None
    speed: float = None

    _motion_commands = CONTROLLER.runtime.commands.motion
    _advanced_motion_commands = CONTROLLER.runtime.commands.advanced_motion
    _fault_and_error_commands = CONTROLLER.runtime.commands.fault_and_error
    _status = CONTROLLER.runtime.status

    def __init__(
        self,
        axis: str,
        unit: str,
        unit_ratio: float,
        home_direction: HomeDirection,
        speed: float,
        default_soft_limits: tuple[float, float] | None = None,
    ) -> None:
        self._parameters = CONTROLLER.runtime.parameters.axes[axis]
        self._parameters[AxisParameterId.FaultMask].value = FAULT_MASK
        self._parameters[AxisParameterId.FaultMaskDecel].value = FAULT_MASK_DECEL
        self._parameters[AxisParameterId.FaultMaskDisable].value = FAULT_MASK_DISABLE
        self._parameters[AxisParameterId.ReverseMotionDirection].value = False

        self.axis = axis
        self.unit = unit
        self.unit_ratio = unit_ratio
        self.home_direction = home_direction
        self.speed = speed

        if self.home_direction == HomeDirection.POSITIVE:
            self.disable_clamping()

        default_soft_limits = (
            default_soft_limits if default_soft_limits is not None else self.soft_limits
        )
        self.soft_limits = default_soft_limits
        self.default_soft_limits = default_soft_limits

    def enable(self) -> None:
        self._motion_commands.enable(axes=self.axis)

    def disable(self) -> None:
        self._motion_commands.disable(axes=self.axis)

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, speed: float) -> None:
        self._speed = speed
        self._parameters[AxisParameterId.DefaultAxisSpeed].value = (
            speed * self.unit_ratio
        )
        self._parameters[AxisParameterId.HomeSpeed].value = speed * self.unit_ratio

    @property
    def soft_limits(self) -> tuple[float, float]:
        return (
            self._parameters[AxisParameterId.SoftwareLimitLow].value / self.unit_ratio,
            self._parameters[AxisParameterId.SoftwareLimitHigh].value / self.unit_ratio,
        )

    @soft_limits.setter
    def soft_limits(self, limits: tuple[float, float]) -> None:
        self._parameters[AxisParameterId.SoftwareLimitLow].value = (
            limits[0] * self.unit_ratio
        )
        self._parameters[AxisParameterId.SoftwareLimitHigh].value = (
            limits[1] * self.unit_ratio
        )

    def disable_clamping(self) -> None:
        setup = int(self._parameters[AxisParameterId.SoftwareLimitSetup].value)
        self._parameters[AxisParameterId.SoftwareLimitSetup].value = setup & 0x2

    @property
    def faults(self) -> list[AxisFault]:
        status_item_config = StatusItemConfiguration()
        status_item_config.axis.add(AxisDataSignal.AxisFault, self.axis)
        fault_status = int(
            self._status.get_status_items(status_item_config)
            .axis.get(AxisDataSignal.AxisFault, self.axis)
            .value
        )

        fault_list = []
        for fault in AxisFault:
            if fault_status & int(fault):
                fault_list.append(fault)

        return fault_list

    def clear_soft_limit_faults(self) -> None:
        for fault in self.faults:
            if fault in {
                AxisFault.CwSoftwareLimitFault,
                AxisFault.CcwSoftwareLimitFault,
            }:
                self._fault_and_error_commands.faultacknowledge(self.axis)
                break

    @property
    def axis_status(self) -> int:
        status_item_config = StatusItemConfiguration()
        status_item_config.axis.add(AxisStatusItem.AxisStatus, self.axis)
        return int(
            self._status.get_status_items(status_item_config)
            .axis.get(AxisStatusItem.AxisStatus, self.axis)
            .value
        )

    def _is_moving(self) -> bool:
        return not bool(self.axis_status & int(AxisStatus.MotionDone))

    async def is_moving(self) -> bool:
        return self._is_moving()

    async def is_homed(self) -> bool:
        return bool(self.axis_status & int(AxisStatus.Homed))

    @property
    def drive_status(self) -> int:
        status_item_config = StatusItemConfiguration()
        status_item_config.axis.add(AxisStatusItem.DriveStatus, self.axis)
        return int(
            self._status.get_status_items(status_item_config)
            .axis.get(AxisStatusItem.DriveStatus, self.axis)
            .value
        )

    async def get_position(self) -> float:
        return self._get_position()

    def _get_position(self) -> float:
        status_item_config = StatusItemConfiguration()
        status_item_config.axis.add(AxisStatusItem.PositionFeedback, self.axis)
        axis_status = self._status.get_status_items(status_item_config)
        self.position = (
            axis_status.axis.get(AxisStatusItem.PositionFeedback, self.axis).value
            / self.unit_ratio
        )
        return self.position

    async def _check_for_limit_fault(
        self,
        exception: ControllerOperationException,
        position: float,
    ):
        self._get_position()

        faults = self.faults
        if (len(faults) == 1) and (
            faults[0]
            in {
                AxisFault.CwSoftwareLimitFault,
                AxisFault.CcwSoftwareLimitFault,
                AxisFault.CwEndOfTravelLimitFault,
                AxisFault.CcwEndOfTravelLimitFault,
            }
        ):
            raise MoveIntoLimitError(
                axis=self.axis,
                active_limit=faults[0].name,
                soft_limits=self.soft_limits,
                position=position,
            )
        else:
            raise exception

    async def move_relative(self, distance: float, speed: float = None) -> None:
        if await self.is_moving():
            warn(f"Move command on {self.axis} while moving.")
            return

        speed = speed if speed is not None else self.speed
        try:
            self._motion_commands.moveincremental(
                axes=self.axis,
                distances=[distance * self.unit_ratio],
                speeds=[speed * self.unit_ratio],
            )
        except ControllerOperationException as e:
            await self._check_for_limit_fault(e, self.position + distance)

        # TODO: get a reliable position
        self.position += distance

    async def move_absolute(self, position: float, speed: float = None) -> None:
        print(f"moving real {self.axis} to {position}")
        speed = speed if speed is not None else self.speed
        try:
            self._motion_commands.moveabsolute(
                axes=self.axis,
                positions=[position * self.unit_ratio],
                speeds=[speed * self.unit_ratio],
            )
        except ControllerOperationException as e:
            await self._check_for_limit_fault(e, position)

        self.position = position

    async def abort_move(self) -> None:
        self._motion_commands.abort(axes=self.axis)
        await self.wait_for_motion_done()
        await self.get_position()

    async def home(self) -> None:
        async def move_out_of_limit() -> bool:
            while not bool(self.axis_status & int(AxisStatus.CommandValid)):
                await asyncio.sleep(0.5)

            # need position to be 0 for moveoutoflimit to avoid issues with soft limits
            self._motion_commands.home(self.axis)

            self._advanced_motion_commands.moveoutoflimit(self.axis)

        if self.home_direction == HomeDirection.POSITIVE:
            self._advanced_motion_commands.movetolimitcw(self.axis)
            await move_out_of_limit()
        elif self.home_direction == HomeDirection.NEGATIVE:
            self._advanced_motion_commands.movetolimitccw(self.axis)
            await move_out_of_limit()
        else:
            assert (
                self.home_direction is HomeDirection.MANUAL
            ), f"Invalid home direction for {self.axis}."

        await self.wait_for_motion_done()
        self._motion_commands.home(self.axis)
        await self.get_position()


class VirtualAxisDriver(MotorDriver):
    """
    A virtual axis is a linear combination of real axes. It can be used to
    simultaneously move multiple axes along a virtual axis, to scale an axis to
    different units, to apply an offset to an axis, or to apply soft limits to an axis.

    args:
        axis: The name of the virtual axis.
        real_axes: The list of real axis drivers in this virtual axis.
        unit: The unit of the virtual axis.
        soft_limits: The soft limits of the virtual axis.
    """

    axis: str
    real_axes: list[MotorDriver]
    scalings: list[float]
    offsets: list[float]
    soft_limits: tuple[float, float]
    unit: str

    position: float = None

    def __init__(
        self,
        name: str,
        axes: list[MotorDriver],
        scalings: list[float],
        offsets: list[float],
        soft_limits: tuple[float, float],
        unit: str,
        speed: float,
    ) -> None:
        self.axis = name
        self.real_axes = axes
        self.scalings = scalings
        self.offsets = offsets
        self.soft_limits = soft_limits
        self.unit = unit
        self.speed = speed

        self.enable()

    async def get_position(self):
        real_positions = await asyncio.gather(
            *[axis.get_position() for axis in self.real_axes]
        )
        virtual_positions = [
            (real_position - offset) / scaling
            for real_position, scaling, offset in zip(
                real_positions, self.scalings, self.offsets
            )
        ]
        self.position = sum(virtual_positions)
        return self.position

    async def is_moving(self) -> bool:
        return all(await asyncio.gather([axis.is_moving() for axis in self.real_axes]))

    @property
    def default_soft_limits(self) -> None:
        raise NotImplementedError("Virtual axes don't have default soft limits.")

    @property
    def soft_limits(self) -> tuple[float, float]:
        return self._soft_limits

    @soft_limits.setter
    def soft_limits(self, limits: tuple[float, float]) -> None:
        self._soft_limits = limits
        for axis, scaling, offset in zip(self.real_axes, self.scalings, self.offsets):
            if scaling > 0:
                axis.soft_limits = (
                    limits[0] * scaling + offset,
                    limits[1] * scaling + offset,
                )
            else:
                axis.soft_limits = (
                    limits[1] * scaling + offset,
                    limits[0] * scaling + offset,
                )

    def enable(self):
        for axis in self.real_axes:
            axis.enable()

    def disable(self):
        for axis in self.real_axes:
            axis.disable()

    async def move_relative(self, distance: float, speed: float = None):
        speed = speed if speed is not None else self.speed
        full_move = [
            axis.move_relative(distance=distance * scaling, speed=speed * scaling)
            for axis, scaling in zip(self.real_axes, self.scalings)
        ]
        await asyncio.gather(*full_move)

    async def move_absolute(self, position: float, speed: float = None):
        speed = speed if speed is not None else self.speed
        full_move = [
            axis.move_absolute(position * scaling + offset, speed=speed * scaling)
            for axis, scaling, offset in zip(
                self.real_axes, self.scalings, self.offsets
            )
        ]
        await asyncio.gather(*full_move)

    async def abort_move(self):
        full_abort = [axis.abort_move() for axis in self.real_axes]
        await asyncio.gather(*full_abort)

    async def home(self):
        raise NotImplementedError("Homing not implemented for virtual axis")

    async def is_homed(self):
        raise NotImplementedError("Homing not implemented for virtual axis")


def emergency_stop() -> None:
    """
    Stop all axes immediately. You have to restart the program to remove the
    emergency stop.
    """

    CONTROLLER.runtime.commands.io.virtualbinaryinputset(
        EMERGENCY_STOP_INPUT_NUMBER, False
    )

    mdrive_emergency_stop(comm=MDRIVE_COMM)
