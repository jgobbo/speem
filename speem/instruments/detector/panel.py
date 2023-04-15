import time
import numpy as np
from PyQt5 import QtWidgets
import pyqtgraph as pg
from functools import partial
from xarray import DataArray

from autodidaqt.panels import BasicInstrumentPanel
from autodidaqt.ui.timing import debounce
from autodidaqt.ui import (
    CollectUI,
    vertical,
    horizontal,
    group,
    button,
    check_box,
    label,
    numeric_input,
)
from autodidaqt.ui.pg_extras import (
    ArrayImageView,
    ArrayPlot,
)

from .common import DetectorSettings

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instrument import DetectorController
    from autodidaqt.ui.pg_extras import CoordAxis

__all__ = ("DetectorPanel",)


class DetectorPanel(BasicInstrumentPanel):
    TITLE = "Detector"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = DetectorSettings
    instrument: "DetectorController"

    xy_bins: np.ndarray = None

    data_x: DataArray = None
    data_y: DataArray = None
    data_t: DataArray = None
    image_x: ArrayImageView = None
    image_y: ArrayImageView = None
    image_t: ArrayImageView = None

    electron_arrs: list[np.ndarray] = None

    save_only_latest = True

    start_time: float = None
    interval_start_time: float = None
    averaging_time: float = 5

    n_elec: int = 0
    n_elec_list: list[tuple] = []

    def __init__(
        self, parent, id, app, instrument_description, instrument_actor, *args, **kwargs
    ):
        self.xy_bins = np.linspace(-13, 13, self.settings.data_size + 1)
        super().__init__(
            parent, id, app, instrument_description, instrument_actor, *args, **kwargs
        )

    @property
    def t_coords(self):
        return np.linspace(
            self.instrument.driver.bin_to_time(0),
            self.instrument.driver.bin_to_time(self.settings.bins_per_channel),
            self.settings.data_size,
        )

    def reset(self, *_):
        # first we reset the marginals, we keep marginals only for data storage reasons
        # data_x is a marginal with x integrated out, and similarly for data_y and data_t
        if self.data_x is None:
            xy_coords = np.linspace(-13, 13, self.settings.data_size)

            self.data_x = DataArray(
                np.zeros(
                    shape=(self.settings.data_size, self.settings.data_size),
                    dtype=float,
                ),
                coords={"y": xy_coords, "t": self.t_coords},
                dims=("y", "t"),
            )
            self.data_y = DataArray(
                np.zeros(
                    shape=(self.settings.data_size, self.settings.data_size),
                    dtype=float,
                ),
                coords={"x": xy_coords, "t": self.t_coords},
                dims=("x", "t"),
            )
            self.data_t = DataArray(
                np.zeros(
                    shape=(self.settings.data_size, self.settings.data_size),
                    dtype=float,
                ),
                coords={"x": xy_coords, "y": xy_coords},
                dims=("x", "y"),
            )
        else:
            self.data_x.data[:] = 0
            self.data_y.data[:] = 0
            self.data_t.data[:] = 0

        now = time.time()
        self.start_time = now
        self.interval_start_time = now

        self.n_elec = 0
        self.n_elec_list = []

    def update_frame_time(self, new_time):
        self.instrument.driver.frame_time = float(new_time)

    @debounce(0.01)
    def update_timing_delay(self, new_time):
        try:
            new_time = float(new_time)
            self.instrument.driver.timing_delay = new_time
            self.data_x.coords["t"] = self.t_coords
            self.data_y.coords["t"] = self.t_coords

            # hacky way to update axis labels; gotten from AxisItem source code
            for image in (self.image_x, self.image_y):
                t_axis: "CoordAxis" = image.plot_item.axes["left"]["item"]
                t_axis.picture = None
                t_axis.update()

        except ValueError:
            pass

    def layout(self):
        self.reset()

        # Here is where we configure the main data plots
        # and selection cursors. Because we want to link the views
        # of the different plots, this becomes a little repetetive and complex
        # but there's no need to refactor at the moment because this is the only
        # view where this sort of logic happens, (unlike, for instance, in the PyARPES code)
        self.image_x = ArrayImageView()
        self.image_y = ArrayImageView()
        self.image_t = ArrayImageView()
        self.plot_x_marginal = ArrayPlot(orientation="horiz")
        self.plot_y_marginal = ArrayPlot(orientation="horiz")
        self.plot_t_marginal = ArrayPlot(orientation="horiz")

        with CollectUI(self.ui):
            vertical(
                horizontal(
                    group(
                        button("Clear", id="clear-integration"),
                        check_box("Save only latest", id="save-only-latest"),
                    ),
                    horizontal(
                        vertical(
                            horizontal(
                                "Averaging interval [s]: ",
                                numeric_input(
                                    self.averaging_time,
                                    input_type=float,
                                    validator_settings={
                                        "bottom": 0.5,
                                        "top": 100,
                                        "decimals": 3,
                                    },
                                    id="averaging-time",
                                ),
                                "Frame Time [s]:",
                                numeric_input(
                                    self.instrument.driver.frame_time,
                                    float,
                                    validator_settings={
                                        "bottom": 0.1,
                                        "top": 10,
                                        "decimals": 1,
                                    },
                                    id="frame-time",
                                ),
                            ),
                            horizontal(
                                "Timing Delay [ns]:",
                                button("<<", id="delay_dd"),
                                button("<", id="delay_d"),
                                numeric_input(
                                    self.instrument.driver.timing_delay,
                                    id="timing_delay",
                                ),
                                button(">", id="delay_u"),
                                button(">>", id="delay_uu"),
                            ),
                        ),
                        group(
                            "total",
                            label("rice", id="global-count-rate"),
                            label("beans", id="interval-count-rate"),
                        ),
                    ),
                    group("total counts", label("0", id="total-counts")),
                ),
                self.plot_x_marginal,
                self.plot_y_marginal,
                self.plot_t_marginal,
                horizontal(
                    group("x/t", self.image_y),
                    group("x/y", self.image_t),
                    group("y/t", self.image_x),
                ),
                widget=self,
            )

        self.ui["clear-integration"].subject.subscribe(self.reset)
        self.ui["averaging-time"].subject.subscribe(
            lambda x: setattr(self, "averaging_time", float(x))
        )
        self.ui["frame-time"].subject.subscribe(
            lambda x: setattr(self.instrument.driver, "frame_time", float(x))
        )

        def shift_timing_delay(shift, _button_val):
            curr_delay = float(self.ui["timing_delay"].text())
            self.ui["timing_delay"].setText(str(curr_delay + shift))

        self.ui["timing_delay"].subject.subscribe(self.update_timing_delay)
        for button_name, shift in zip(
            ["delay_dd", "delay_d", "delay_u", "delay_uu"], [-10, -1, 1, 10]
        ):
            self.ui[button_name].subject.subscribe(partial(shift_timing_delay, shift))

        multiplier = 1.5
        for image in (self.image_x, self.image_y, self.image_t):
            image.setFixedSize(
                *[round(self.settings.data_size * multiplier)] * 2,
            )

        circle_diameter = 500
        p_ellipse = QtWidgets.QGraphicsEllipseItem(
            (self.settings.data_size - circle_diameter) // 2,
            (self.settings.data_size - circle_diameter) // 2,
            circle_diameter,
            circle_diameter,
        )
        p_ellipse.setPen(pg.mkPen(width=1, color=(0, 255, 255)))
        self.image_t.addItem(p_ellipse)

        self.image_x.setImage(self.data_x)
        self.image_y.setImage(self.data_y)
        self.image_t.setImage(self.data_t)
        self.image_x.show()
        self.image_y.show()
        self.image_t.show()

        self.retrieve(["frame"]).raw_value_stream.subscribe(
            self.update_frame
        )  # subscribe to updates from instrument

    def update_frame(self, value):
        value = value["value"]
        self.receive_frame(value)

    def receive_frame(self, frame: np.ndarray):
        if self.ui["save-only-latest"].isChecked():
            self.data_x.data = np.histogram2d(
                frame[:, 1],
                frame[:, 2],
                bins=[self.xy_bins, self.instrument.driver.t_bins],
            )[0]
            self.data_y.data = np.histogram2d(
                frame[:, 0],
                frame[:, 2],
                bins=[self.xy_bins, self.instrument.driver.t_bins],
            )[0]
            self.data_t.data = np.histogram2d(
                frame[:, 0], frame[:, 1], bins=[self.xy_bins, self.xy_bins]
            )[0]
        else:
            self.data_x.data += np.histogram2d(
                frame[:, 1],
                frame[:, 2],
                bins=[self.xy_bins, self.instrument.driver.t_bins],
            )[0]
            self.data_y.data += np.histogram2d(
                frame[:, 0],
                frame[:, 2],
                bins=[self.xy_bins, self.instrument.driver.t_bins],
            )[0]
            self.data_t.data += np.histogram2d(
                frame[:, 0], frame[:, 1], bins=[self.xy_bins, self.xy_bins]
            )[0]

        for i in range(3):
            self.replot_1d_marginal(i)

        for image, data in zip(
            [self.image_x, self.image_y, self.image_t],
            [self.data_x, self.data_y, self.data_t],
        ):
            image.setImage(data, keep_levels=True)

        now = time.time()
        n_in_frame = frame.shape[0]
        self.n_elec += n_in_frame
        self.n_elec_list.append((n_in_frame, now))

        for frame_count, frame_time in self.n_elec_list:
            if (now - frame_time) > self.averaging_time:
                self.n_elec_list.remove((frame_count, frame_time))
            else:
                break

        if now != self.start_time:
            avg_since_start = self.n_elec / (now - self.start_time)

            n_elec_interval = sum(n_elec for (n_elec, _time) in self.n_elec_list)
            interval_time = min(now - self.interval_start_time, self.averaging_time)
            avg_interval = n_elec_interval / interval_time

            self.ui["global-count-rate"].setText(f"From start: {avg_since_start:.3f}")
            self.ui["interval-count-rate"].setText(f"In interval: {avg_interval:.3f}")
            self.ui["total-counts"].setText(str(self.n_elec))

    def replot_1d_marginal(self, marginal_index):
        plot: ArrayPlot
        plot, data, sum_axis = {
            0: (self.plot_x_marginal, self.data_t, 1),
            1: (self.plot_y_marginal, self.data_t, 0),
            2: (self.plot_t_marginal, self.data_x, 0),
        }[marginal_index]

        data = np.sum(data, axis=sum_axis)
        plot.clear()
        p = plot.plot(data)
        p.setPen(pg.mkPen(width=1, color=(0, 0, 0)))
