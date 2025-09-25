from enum import IntEnum, StrEnum, auto
import asyncio

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QImage, QPixmap, QTransform

from autodidaqt.panels import BasicInstrumentPanel
from autodidaqt.ui import (
    CollectUI,
    stack,
    vertical,
    horizontal,
    numeric_input,
    combo_box,
    button,
    label,
    slider,
)
from pylucam import LucamCamera

from .specs import (
    GlobalPosition,
    RealAxis,
    Z_SAMPLE_STAGE_MM,
    X_CENTER_MM,
    Y_CENTER_MM,
    x_CENTER_MM,
    y_CENTER_MM,
    SAMPLE_LOAD_POSITION,
)
from .drivers import MoveIntoLimitError

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instrument import MotionController
    from .drivers import MotorDriver
    from autodidaqt.widgets import ComboBox, Subjective, PushButton, NumericEdit, Slider
    from PyQt5.QtWidgets import QStackedWidget, QWidget, QLayout


class HomingState(IntEnum):
    UNHOMED = 0
    PHI = 1
    BETA = 2
    HOMED = 3


class CameraUpdate(StrEnum):
    GAIN = auto()
    WHITE_BALANCE = auto()
    IMAGE = auto()


class MotionPanel(BasicInstrumentPanel):
    TITLE = "Motors"
    SIZE = (450, 900)
    DEFAULT_OPEN = True

    _homing_state: HomingState = HomingState.UNHOMED

    _active_camera: LucamCamera
    camera_timer: QTimer
    camera_view_width: int = 450

    camera_update: CameraUpdate = CameraUpdate.IMAGE
    gain_scaling: int = 10

    instrument: "MotionController"
    real_axes: dict[str, "MotorDriver"]
    ui: dict[str, "Subjective"]
    axis_controls: list = []

    def __init__(self, *args, **kwargs) -> None:
        # TODO : figure out a consistent way to set the cameras
        # if you disconnect them they can get reordered
        self.speem_camera = LucamCamera(2)
        self.sample_loading_camera = LucamCamera(1)
        self._active_camera = self.sample_loading_camera
        self._active_camera.enable_fast_frames()

        super().__init__(*args, **kwargs)
        self.setMinimumWidth(self.camera_view_width)
        self.real_axes = self.instrument.driver.real_axes

        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self.update_camera_view)
        self.camera_timer.setInterval(round(1000 / 30))
        self.camera_timer.start()

    async def shutdown(self):
        # TODO fix this
        if self.camera_timer.isActive():
            self.camera_timer.stop()
            await asyncio.sleep(0.5)

    def before_close(self):
        self.camera_timer.stop()
        return super().before_close()

    @property
    def active_camera(self) -> LucamCamera:
        return self._active_camera

    @active_camera.setter
    def active_camera(self, camera: LucamCamera) -> None:
        self.active_camera.disable_fast_frames()
        camera.enable_fast_frames()
        self._active_camera = camera

    def update_gain(self, gain: float) -> None:
        self.active_camera.snapshot.gain = gain / self.gain_scaling
        self.camera_update = CameraUpdate.GAIN

    def white_balance(self, _: bool) -> None:
        self.camera_update = CameraUpdate.WHITE_BALANCE

    def update_camera_view(
        self,
    ) -> None:
        if self.camera_update == CameraUpdate.GAIN:
            self.active_camera.reset_fast_frames()
            self.camera_update = CameraUpdate.IMAGE
        elif self.camera_update == CameraUpdate.WHITE_BALANCE:
            self.active_camera.white_balance()
            self.camera_update = CameraUpdate.IMAGE
        else:
            assert self.camera_update == CameraUpdate.IMAGE

            image = self.active_camera.take_fast_frame_rgb()
            height, width, n_colors = image.shape
            q_image = (
                QImage(
                    image.data.tobytes(),
                    width,
                    height,
                    width * n_colors,
                    QImage.Format.Format_RGB888,
                )
                .transformed(QTransform().rotate(-90.0))
                .scaledToWidth(self.camera_view_width)
            )
            self.camera_view.setPixmap(QPixmap.fromImage(q_image))

    @property
    def homing_state(self) -> HomingState:
        return self._homing_state

    @homing_state.setter
    def homing_state(self, state: HomingState) -> None:
        control_stack: "QStackedWidget" = self.ui["control_stack"]
        control_stack.setCurrentIndex(state)
        self._homing_state = state

    async def move_axis(self, axis: str, position: float) -> None:
        axis_driver = self.instrument.driver.active_axes[axis]
        try:
            print(f"moving {axis} to {position}")
            await axis_driver.move_absolute(position)
        except MoveIntoLimitError:
            axis_control: "NumericEdit" = self.ui[axis]
            axis_control.setText(
                str(await axis_driver.get_position()), emit_signal=False
            )

    @property
    def axis_control_layout(self) -> "QLayout":
        axis_control_widget: "QWidget" = self.ui["axis_control"]
        return axis_control_widget.layout()

    def delete_axis_controls(self) -> None:
        while self.axis_controls:
            control: "QWidget" = self.axis_controls.pop()
            self.axis_control_layout.removeWidget(control)
            control.destroy()  # deleteLater was causing some weird bugs, hopefully using this doesn't cause issues

    def create_axis_controls(self) -> None:
        active_axes = self.instrument.driver.active_axes

        def axis_control(axis: str, increment: float):
            soft_limits = active_axes[axis].soft_limits
            n_decimals = 1
            validator_settings = {
                "bottom": soft_limits[0],
                "top": soft_limits[1],
                "decimals": n_decimals,
            }
            input = numeric_input(
                value=round(active_axes[axis].position, n_decimals),
                input_type=float,
                validator_settings=validator_settings,
                increment=increment,
                id=axis,
            )
            self.ui[axis] = input
            input.subject.subscribe(
                lambda input_value: asyncio.create_task(
                    self.move_axis(axis=axis, position=float(input_value))
                )
            )
            return horizontal(label(axis), input, label(active_axes[axis].unit))

        for axis in active_axes:
            axis_unit = active_axes[axis].unit
            increment = 1.0
            if axis_unit == "um":
                increment = 50.0
            control = axis_control(axis, increment)
            self.axis_controls.append(control)
            self.axis_control_layout.addWidget(control)

    async def go_to_position(self) -> None:
        global_position_combo: "ComboBox" = self.ui["global_position"]
        go_button: "PushButton" = self.ui["go"]

        go_button.setEnabled(False)
        position = GlobalPosition[global_position_combo.currentText()]

        if position in {
            GlobalPosition.SPEEM,
        }:
            self.active_camera = self.speem_camera
        else:
            self.active_camera = self.sample_loading_camera
        camera_gain_slider: "Slider" = self.ui["camera_gain"]
        camera_gain_slider.setValue(
            round(self.active_camera.snapshot.gain * self.gain_scaling)
        )

        self.delete_axis_controls()
        await self.instrument.driver.go_to_position(position.value)
        self.create_axis_controls()

        go_button.setEnabled(True)

    async def home_limited_axes(self, button_value: bool) -> None:
        assert button_value is True

        limited_axes = [
            RealAxis.Y,
            RealAxis.X,
            RealAxis.y,
            RealAxis.x,
            RealAxis.Z,
            RealAxis.Theta,
        ]
        all_homed = all(
            [await self.real_axes[axis].is_homed() for axis in limited_axes]
        )
        if not all_homed:
            for axis in limited_axes:
                axis_driver = self.real_axes[axis]
                axis_driver.enable()

                if await axis_driver.is_homed():
                    await axis_driver.get_position()
                else:
                    await axis_driver.home()

                await axis_driver.move_absolute(SAMPLE_LOAD_POSITION[axis])
                await axis_driver.wait_for_motion_done()

        await self.set_up_phi_homing()

    async def set_up_phi_homing(self) -> None:
        phi = self.real_axes[RealAxis.Phi]
        phi.enable()
        await phi.get_position()
        if await phi.is_homed():
            await self.set_up_beta_homing()
            return

        phi_homing_positions = {
            RealAxis.Y: Y_CENTER_MM,
            RealAxis.y: y_CENTER_MM,
            RealAxis.X: X_CENTER_MM,
            RealAxis.x: x_CENTER_MM,
            RealAxis.Z: Z_SAMPLE_STAGE_MM,
            RealAxis.Theta: 0.0,
        }
        for axis, position in phi_homing_positions.items():
            await self.real_axes[axis].move_absolute(position)
        self.homing_state = HomingState.PHI

    async def set_up_beta_homing(self) -> None:
        beta = self.real_axes[RealAxis.Beta]
        beta.enable()
        await beta.get_position()
        if await beta.is_homed():
            self.homing_state = HomingState.HOMED
            return

        beta_homing_positions = {
            RealAxis.Phi: 0.0,
            RealAxis.Y: Y_CENTER_MM,
            RealAxis.y: y_CENTER_MM,
            RealAxis.X: X_CENTER_MM,
            RealAxis.x: x_CENTER_MM,
            RealAxis.Z: -28.0,
            RealAxis.Theta: 85.0,
        }
        for axis, position in beta_homing_positions.items():
            await self.real_axes[axis].move_absolute(position)
        self.homing_state = HomingState.BETA

    async def home_phi(self, button_value: bool) -> None:
        assert button_value is True
        await self.real_axes[RealAxis.Phi].home()
        await self.set_up_beta_homing()

    async def home_beta(self, button_value: bool) -> None:
        assert button_value is True
        await self.real_axes[RealAxis.Beta].home()
        self.homing_state = HomingState.HOMED

    async def jog_real_axis(self, axis: RealAxis, distance: float) -> None:
        axis_driver = self.real_axes[axis]
        if await axis_driver.is_moving():
            return

        try:
            await axis_driver.move_relative(distance)
        except MoveIntoLimitError:
            pass

    async def abort_move(self) -> None:
        for real_axis in self.real_axes.values():
            await real_axis.abort_move()

    def set_layout(self) -> None:
        self.camera_view = QLabel(self)
        self.camera_view.resize(
            self.camera_view_width,
            round(
                self.active_camera.height
                / self.active_camera.width
                * self.camera_view_width
            ),
        )

        def camera_ui():
            gain_slider = slider(minimum=0, maximum=1000, interval=1, id="camera_gain")
            gain_slider.setValue(
                round(self.active_camera.snapshot.gain * self.gain_scaling)
            )
            gain_slider.valueChanged.connect(self.update_gain)
            whitebalance_button = button("White Balance")
            whitebalance_button.clicked.connect(self.white_balance)

            return vertical(
                self.camera_view, horizontal(whitebalance_button, gain_slider)
            )

        def real_axis_control(axis: RealAxis, jog_distance: float):
            """Real axis control for homing Phi and Beta"""
            decrement_button = button("<")
            increment_button = button(">")

            decrement_button.subject.subscribe(
                lambda _: asyncio.create_task(self.jog_real_axis(axis, -jog_distance))
            )
            increment_button.subject.subscribe(
                lambda _: asyncio.create_task(self.jog_real_axis(axis, jog_distance))
            )
            return horizontal(label(axis), decrement_button, increment_button)

        def stops():
            abort_button: "PushButton" = button("Abort Move", id="abort_move")
            abort_button.subject.subscribe(
                lambda _: asyncio.create_task(self.abort_move())
            )
            estop_button: "PushButton" = button("Emergency Stop", id="emergency_stop")
            estop_button.subject.subscribe(
                lambda _: self.instrument.driver.emergency_stop()
            )
            return vertical(abort_button, estop_button)

        with CollectUI(self.ui):
            vertical(
                camera_ui(),
                stack(
                    vertical(
                        label(
                            "Make sure the chamber and surroundings are safe for homing the"
                            " motors.\nOnce ready, press the button below."
                        ),
                        button("Start Homing", id="start_homing"),
                    ),
                    vertical(
                        label(
                            "Move Phi until the notch is pointing straight down.\nOnce done,"
                            " press the button below."
                        ),
                        real_axis_control(RealAxis.Phi, 1.0),
                        button("Home Phi", id="home_phi"),
                    ),
                    vertical(
                        label(
                            "Move Beta until the stage is roughly homed.\nIf you are not "
                            "sure how to do this, please ask for help\nor consult the "
                            "manual. Once done, press the button below."
                        ),
                        real_axis_control(RealAxis.Beta, 0.1),
                        button("Home Beta", id="home_beta"),
                    ),
                    vertical(
                        horizontal(
                            combo_box(
                                [position.name for position in GlobalPosition],
                                id="global_position",
                            ),
                            button("GO", id="go"),
                        ),
                        id="axis_control",
                    ),
                    id="control_stack",
                ),
                stops(),
                widget=self,
            )
        self.ui["start_homing"].subject.subscribe(
            lambda button_value: asyncio.create_task(
                self.home_limited_axes(button_value)
            )
        )
        self.ui["home_phi"].subject.subscribe(
            lambda button_value: asyncio.create_task(self.home_phi(button_value))
        )
        self.ui["home_beta"].subject.subscribe(
            lambda button_value: asyncio.create_task(self.home_beta(button_value))
        )
        self.ui["go"].subject.subscribe(
            lambda _: asyncio.create_task(self.go_to_position())
        )
