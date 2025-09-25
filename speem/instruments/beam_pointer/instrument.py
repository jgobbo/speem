from dataclasses import dataclass

from .lib.MDT_COMMAND_LIB import *
import numpy as np
import asyncio

from autodidaqt import ManagedInstrument
from autodidaqt.instrument import AxisSpecification
from autodidaqt.panels import BasicInstrumentPanel
from autodidaqt.utils import safe_lookup

from autodidaqt.ui.pg_extras import ArrayImageView
from autodidaqt.ui import (
    CollectUI,
    grid,
    vertical,
    horizontal,
    tabs,
    numeric_input,
    label,
    button,
    splitter,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from speem.instruments import DetectorController

__all__ = ("BeamPointerController", "MDTDriver")

BAUD_RATE = 115200
TIMEOUT = 3


@dataclass
class MDTDriver:
    x_voltage: float = 0
    y_voltage: float = 0
    z_voltage: float = 0

    x_range: tuple = (0, 150)
    y_range: tuple = (0, 150)
    z_range: tuple = (0, 150)

    step_resolution: float = None

    def __post_init__(self):
        try:
            self.SERIAL_NUMBER = mdtListDevices()[0][0]
        except IndexError:
            print(
                "MDT device for beam pointer not detected. Check power and connections."
            )

    def start(self):
        self.hdl = mdtOpen(self.SERIAL_NUMBER, BAUD_RATE, TIMEOUT)
        assert self.hdl >= 0

        temp = [None]
        assert mdtGetXAxisVoltage(self.hdl, temp) == 0
        self.x_voltage = temp[0]
        assert mdtGetYAxisVoltage(self.hdl, temp) == 0
        self.y_voltage = temp[0]
        assert mdtGetZAxisVoltage(self.hdl, temp) == 0
        self.z_voltage = temp[0]
        del temp

        assert mdtSetMasterScanEnable(self.hdl, 0) == 0
        assert mdtSetXAxisMinVoltage(self.hdl, self.x_range[0]) == 0
        assert mdtSetXAxisMaxVoltage(self.hdl, self.x_range[1]) == 0
        assert mdtSetYAxisMinVoltage(self.hdl, self.y_range[0]) == 0
        assert mdtSetYAxisMaxVoltage(self.hdl, self.y_range[1]) == 0
        assert mdtSetZAxisMinVoltage(self.hdl, self.z_range[0]) == 0
        assert mdtSetZAxisMaxVoltage(self.hdl, self.z_range[1]) == 0

    def stop(self):
        assert mdtClose(self.hdl) == 0

    def set_x(self, voltage: float):
        voltage = np.clip(voltage, *self.x_range)
        assert mdtSetXAxisVoltage(self.hdl, voltage) == 0
        self.x_voltage = voltage

    def set_y(self, voltage: float):
        voltage = np.clip(voltage, *self.y_range)
        assert mdtSetYAxisVoltage(self.hdl, voltage) == 0
        self.y_voltage = voltage

    def set_z(self, voltage: float):
        voltage = np.clip(voltage, *self.z_range)
        assert mdtSetZAxisVoltage(self.hdl, voltage) == 0
        self.z_voltage = voltage


class BeamPointerPanel(BasicInstrumentPanel):
    TITLE = "Beam Pointer"
    SIZE = (800, 400)
    DEFAULT_OPEN = True

    arr: np.ndarray = np.zeros((2, 2))
    scanning: bool = False
    i_x: int = 0
    i_y: int = 0

    detector: "DetectorController" = None

    def __init__(self, parent, id, app, instrument_description, instrument_actor):
        super().__init__(parent, id, app, instrument_description, instrument_actor)
        self.detector = self.app.managed_instruments["detector"]

    @property
    def frame_time(self):
        return float(self.ui["frame-time"].text())

    @property
    def x_start(self):
        return float(self.ui["x-start"].text())

    @property
    def x_stop(self):
        return float(self.ui["x-stop"].text())

    @property
    def n_xs(self):
        return int(self.ui["n-xs"].text())

    @property
    def y_start(self):
        return float(self.ui["y-start"].text())

    @property
    def y_stop(self):
        return float(self.ui["y-stop"].text())

    @property
    def n_ys(self):
        return int(self.ui["n-ys"].text())

    async def start_scan(self, _):
        await self.detector.frame_time.write(self.frame_time)
        self.scanning = True

        self.arr = np.zeros((self.n_xs, self.n_ys))
        self.i_x = 0
        self.i_y = 0

    def abort_scan(self, _):
        self.scanning = False

    def collect_frame(self, frame):
        if self.scanning:
            self.arr[self.i_x, self.i_y] = len(frame["value"])
            # TODO - set meaningful tick labels
            self.image.setImage(
                self.arr,
                keep_levels=False,
            )

            self.i_y += 1
            if self.i_y >= self.n_ys:
                self.i_y = 0
                self.i_x += 1

                if self.i_x >= self.n_xs:
                    self.scanning = False
                else:
                    self.instrument.driver.set_x(
                        self.x_start
                        + (self.x_stop - self.x_start) * self.i_x / (self.n_xs - 1)
                    )
            else:
                self.instrument.driver.set_y(
                    self.y_start
                    + (self.y_stop - self.y_start) * self.i_y / (self.n_ys - 1)
                )

    def optimize_widget(self):
        return splitter(
            vertical(
                horizontal(
                    label("frame time"), numeric_input(value=1, id="frame-time")
                ),
                horizontal(label("x start"), numeric_input(value=0, id="x-start")),
                horizontal(label("x stop"), numeric_input(value=150, id="x-stop")),
                horizontal(label("n xs"), numeric_input(value=11, id="n-xs")),
                horizontal(label("y start"), numeric_input(value=0, id="y-start")),
                horizontal(label("y stop"), numeric_input(value=150, id="y-stop")),
                horizontal(label("n ys"), numeric_input(value=11, id="n-ys")),
                button("Start Scan", id="start-scan"),
                button("Abort", id="abort"),
            ),
            self.image,
            direction=splitter.Horizontal,
            size=[self.SIZE[0] // 5, self.SIZE[0] // 5 * 4],
        )

    def layout(self):
        self.image = ArrayImageView()

        with CollectUI(self.ui):
            grid(
                tabs(
                    *[
                        [k, self.tab_for_axis_group(k)]
                        for k in self.description["axes"]
                    ],
                    ["optimize", self.optimize_widget()],
                ),
                widget=self,
            )
        for axis_view in self.axis_views:
            axis_view.attach(self.ui)

        self.ui["start-scan"].subscribe(
            lambda value: asyncio.create_task(self.start_scan(value))
        )
        self.ui["abort"].subscribe(self.abort_scan)

        self.image.setImage(self.arr, keep_levels=False)
        self.image.show()

        # subscribe to frames from the detector
        safe_lookup(
            self.app.managed_instruments["detector"], ["frame"]
        ).raw_value_stream.subscribe(self.collect_frame)


class BeamPointerController(ManagedInstrument):
    driver_cls = MDTDriver
    panel_cls = BeamPointerPanel

    x = AxisSpecification(float, where=[], write="set_x", read="x_voltage")
    y = AxisSpecification(float, where=[], write="set_y", read="y_voltage")
    z = AxisSpecification(float, where=[], write="set_z", read="z_voltage")

    async def prepare(self):
        self.driver.start()
        return await super().prepare()

    async def shutdown(self):
        self.driver.stop()
        return await super().shutdown()
