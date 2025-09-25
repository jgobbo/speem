from autodidaqt import ManagedInstrument

from .drivers import (
    MotorDriver,
    MDRIVE_COMM,
    MdriveDriver,
    Automation1Driver,
    VirtualAxisDriver,
    emergency_stop,
)
from .panel import MotionPanel
from .specs import RealAxis, REAL_AXIS_SPECS, GlobalPositionSpec, VirtualAxisSpec


class MotionDriver:
    real_axes: dict[RealAxis, MotorDriver]
    active_axes: dict[str, MotorDriver]
    global_position: str = None

    def __init__(self):
        self.real_axes = {}
        for axis, spec in REAL_AXIS_SPECS.items():
            if axis in {RealAxis.X, RealAxis.Y}:
                self.real_axes[axis] = MdriveDriver(axis, **spec)
            else:
                self.real_axes[axis] = Automation1Driver(axis, **spec)
        self.active_axes = {}

    async def go_to_position(self, position_spec: GlobalPositionSpec) -> None:
        self.global_position = position_spec.name

        for axis, position in position_spec.real_axis_positions.items():
            real_axis_driver = self.real_axes[axis]
            real_axis_driver.enable()
            real_axis_driver.soft_limits = real_axis_driver.default_soft_limits
            if isinstance(real_axis_driver, Automation1Driver):
                real_axis_driver.clear_soft_limit_faults()

            await real_axis_driver.move_absolute(position)
            await real_axis_driver.wait_for_motion_done()
            real_axis_driver.disable()

        self.active_axes = {}
        for axis, axis_spec in position_spec.virtual_axes.items():
            if isinstance(axis_spec.axes, RealAxis):
                virtual_axis = self._copy_real_axis(axis, axis_spec)
            else:
                virtual_axis = VirtualAxisDriver(
                    name=axis,
                    axes=[self.real_axes[axis] for axis in axis_spec.axes],
                    scalings=axis_spec.scalings,
                    offsets=axis_spec.offsets,
                    soft_limits=axis_spec.soft_limits,
                    unit=axis_spec.unit,
                    speed=axis_spec.speed,
                )

            await virtual_axis.get_position()
            self.active_axes[axis] = virtual_axis

    def _copy_real_axis(self, axis: str, axis_spec: VirtualAxisSpec):
        real_axis = self.real_axes[axis_spec.axes]
        return VirtualAxisDriver(
            name=axis,
            axes=[real_axis],
            scalings=[1],
            offsets=[0],
            soft_limits=real_axis.soft_limits,
            unit=real_axis.unit,
            speed=real_axis.speed,
        )

    def emergency_stop(self) -> None:
        emergency_stop()

    async def write_axis(self, axis: str, value: float) -> None:
        try:
            await self.active_axes[axis].move_absolute(value)
        except KeyError:
            # TODO: handle this such that it aborts a scan rather than crashing the program
            raise ValueError(f"Axis {axis} not found in active axes.")

    async def read_axis(self, axis: str) -> float:
        try:
            return await self.active_axes[axis].get_position()
        except KeyError:
            # TODO: handle this such that it aborts a scan rather than crashing the program
            raise ValueError(f"Axis {axis} not found in active axes.")


class MotionController(ManagedInstrument):
    """
    Controls the motors of the chamber. Axis specifications are only given for the SPEEM
    axes. The axes at other global positions are only adjusted by the user.
    """

    driver_cls = MotionDriver
    panel_cls = MotionPanel
    driver: MotionDriver
    panel: MotionPanel

    async def prepare(self):
        await MDRIVE_COMM.start()
        return await super().prepare()

    async def shutdown(self):
        await MDRIVE_COMM.stop()
        await self.panel.shutdown()
        return await super().shutdown()
