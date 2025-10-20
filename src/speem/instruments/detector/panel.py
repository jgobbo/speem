import time
import numpy as np

# from numba import njit
from PyQt5 import QtWidgets
import pyqtgraph as pg
from xarray import DataArray

from daquiri.panels import BasicInstrumentPanel
from daquiri.ui.timing import debounce
from daquiri.ui import (
    CollectUI,
    vertical,
    horizontal,
    group,
    button,
    check_box,
    label,
    numeric_input,
)
from daquiri.ui.lens import LensSubject
from daquiri.ui.pg_extras import (
    ArrayImageView,
    ArrayPlot,
    CursorRegion,
    RescalableCursorRegion,
)

from .common import DetectorSettings

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .instrument import DetectorController
    from daquiri.widgets import CheckBox
    from daquiri.ui.pg_extras import CoordAxis

__all__ = ("DetectorPanel",)


# @njit
def generate_marginal(
    event_list: np.ndarray,
    marginal_index: int,
    bounds: tuple[float, float],
    other_indices: tuple[int, int],
    bins: list[np.ndarray],
) -> np.ndarray:
    marginal_events = event_list[:, marginal_index]
    trimmed_list = event_list[
        np.logical_and(marginal_events > bounds[0], marginal_events < bounds[1])
    ]
    return np.histogram2d(
        trimmed_list[:, other_indices[0]], trimmed_list[:, other_indices[1]], bins=bins
    )[0]


class DetectorPanel(BasicInstrumentPanel):
    TITLE = "Detector"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = DetectorSettings
    instrument: "DetectorController"

    xy_bins: np.ndarray = None  # x and y bins are identical

    data_x: DataArray = None
    data_y: DataArray = None
    data_t: DataArray = None
    image_x: ArrayImageView = None
    image_y: ArrayImageView = None
    image_t: ArrayImageView = None

    cursor_horiz_x: RescalableCursorRegion = None
    cursor_vert_x: RescalableCursorRegion = None
    cursor_horiz_y: RescalableCursorRegion = None
    cursor_vert_y: RescalableCursorRegion = None
    cursor_horiz_t: RescalableCursorRegion = None
    cursor_vert_t: RescalableCursorRegion = None

    cursor_1d_x: RescalableCursorRegion = None
    cursor_1d_y: RescalableCursorRegion = None
    cursor_1d_t: RescalableCursorRegion = None

    x_bounds = LensSubject((0, settings.data_size))
    y_bounds = LensSubject((0, settings.data_size))
    t_bounds = LensSubject((0, settings.data_size))

    events: np.ndarray = np.empty((0, 3))

    save_only_latest = True

    start_time: float = None
    interval_start_time: float = None
    averaging_time: float = 1

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
    def t_bins(self) -> np.ndarray:
        return np.linspace(
            self.instrument.driver.bin_to_time(self.settings.bins_per_channel),
            self.instrument.driver.bin_to_time(0),
            self.settings.data_size + 1,
        )

    @property
    def t_coords(self) -> np.ndarray:
        return self.t_bins[-2::-1]

    @property
    def save_only_latest(self) -> bool:
        save_only_latest_check_box: "CheckBox" = self.ui["save-only-latest"]
        return save_only_latest_check_box.isChecked()

    @property
    def remove_overrange(self) -> bool:
        remove_overrange_checkbox: "CheckBox" = self.ui["remove-overrange"]
        return remove_overrange_checkbox.isChecked()

    def reset(self, *_) -> None:
        # first we reset the marginals, we keep marginals only for data storage reasons
        # data_x is a marginal with x integrated out, and similarly for data_y and data_t
        if self.data_x is None:
            xy_coords = self.xy_bins[:-1]
            t_coords = self.t_coords

            self.data_x = DataArray(
                np.zeros(
                    shape=(self.settings.data_size, self.settings.data_size),
                    dtype=float,
                ),
                coords={"y": xy_coords, "t": t_coords},
                dims=("y", "t"),
            )
            self.data_y = DataArray(
                np.zeros(
                    shape=(self.settings.data_size, self.settings.data_size),
                    dtype=float,
                ),
                coords={"x": xy_coords, "t": t_coords},
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
            for data in [self.data_x, self.data_y, self.data_t]:
                data.data[:] = 0

        now = time.time()
        self.start_time = now
        self.interval_start_time = now

        self.n_elec = 0
        self.n_elec_list = []

    def marginal_bounds(self, marginal_index: int) -> tuple[float, float]:
        return {
            0: self.xy_bins.take(self.x_bounds.value),
            1: self.xy_bins.take(self.y_bounds.value),
            2: self.t_bins.take(self.t_bounds.value),
        }[marginal_index]

    def compute_marginal(self, event_list: np.ndarray, marginal_index: int):
        other_indices = tuple(i for i in (0, 1, 2) if i != marginal_index)
        bins_by_index = {0: self.xy_bins, 1: self.xy_bins, 2: self.t_bins}
        bins = [bins_by_index[index] for index in other_indices]

        marginal = generate_marginal(
            event_list,
            marginal_index,
            self.marginal_bounds(marginal_index),
            other_indices,
            bins,
        )
        if marginal_index in {0, 1}:
            return marginal[:, ::-1]
        return marginal

    @debounce(1)
    def recompute_marginal(self, marginal_index) -> None:
        if self.save_only_latest:
            return

        image = {0: self.data_x, 1: self.data_y, 2: self.data_t}[marginal_index]
        image.data = self.compute_marginal(self.events, marginal_index)

    def activate_cursors(self, check_box_value: str) -> None:
        self.cursors_active = bool(check_box_value)
        for i in range(3):
            image: ArrayImageView
            image, cursors = {
                0: (self.image_x, (self.cursor_horiz_x, self.cursor_vert_x)),
                1: (self.image_y, (self.cursor_horiz_y, self.cursor_vert_y)),
                2: (self.image_t, (self.cursor_horiz_t, self.cursor_vert_t)),
            }[i]
            if self.cursors_active:
                [image.addItem(cursor) for cursor in cursors]
            else:
                [image.removeItem(cursor) for cursor in cursors]

    @debounce(0.01)
    def update_timing_delay(self, new_time: str) -> None:
        new_time = float(new_time)
        self.instrument.driver.timing_delay = new_time

        t_coords = self.t_coords
        self.data_x.coords["t"] = t_coords
        self.data_y.coords["t"] = t_coords

        # hacky way to update axis labels; gotten from AxisItem source code
        for image in (self.image_x, self.image_y):
            t_axis: "CoordAxis" = image.plot_item.axes["left"]["item"]
            t_axis.picture = None
            t_axis.update()

    def set_layout(self) -> None:
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

        cursor_bounds = (0, self.settings.data_size)
        self.cursor_horiz_x = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal,
            movable=True,
            subject=self.t_bounds,
            bounds=cursor_bounds,
        )
        self.cursor_vert_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.y_bounds,
            bounds=cursor_bounds,
        )

        self.cursor_horiz_y = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal,
            movable=True,
            subject=self.t_bounds,
            bounds=cursor_bounds,
        )
        self.cursor_vert_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.x_bounds,
            bounds=cursor_bounds,
        )

        self.cursor_horiz_t = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal,
            movable=True,
            subject=self.y_bounds,
            bounds=cursor_bounds,
        )
        self.cursor_vert_t = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.x_bounds,
            bounds=cursor_bounds,
        )

        self.cursor_1d_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.x_bounds,
            bounds=cursor_bounds,
        )
        self.cursor_1d_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.y_bounds,
            bounds=cursor_bounds,
        )
        self.cursor_1d_t = RescalableCursorRegion(
            orientation=CursorRegion.Vertical,
            movable=True,
            subject=self.t_bounds,
            bounds=cursor_bounds,
        )

        with CollectUI(self.ui):
            vertical(
                horizontal(
                    group(
                        button("Clear", id="clear-integration"),
                        check_box("Save only latest", id="save-only-latest"),
                        check_box("Cursors", default=False, id="cursors"),
                        check_box(
                            "Remove Overrange", default=False, id="remove-overrange"
                        ),
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
                                numeric_input(
                                    self.instrument.driver.timing_delay,
                                    input_type=float,
                                    validator_settings={
                                        "bottom": 0,
                                        "top": 3000,
                                        "decimals": 3,
                                    },
                                    id="timing_delay",
                                    increment=1,
                                    multiplier=10,
                                ),
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
        self.ui["remove-overrange"].subject.subscribe(self.reset)
        self.ui["cursors"].subject.subscribe(self.activate_cursors)
        self.ui["averaging-time"].subject.subscribe(
            lambda x: setattr(self, "averaging_time", float(x))
        )
        self.ui["frame-time"].subject.subscribe(
            lambda x: setattr(self.instrument.driver, "frame_time", float(x))
        )
        self.ui["timing_delay"].subject.subscribe(self.update_timing_delay)

        self.x_bounds.subscribe(lambda *_: self.recompute_marginal(0))
        self.y_bounds.subscribe(lambda *_: self.recompute_marginal(1))
        self.t_bounds.subscribe(lambda *_: self.recompute_marginal(2))

        multiplier = 1.25
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
        if self.save_only_latest:
            self.events = frame
            self.data_x.data = self.compute_marginal(frame, 0)
            self.data_y.data = self.compute_marginal(frame, 1)
            self.data_t.data = self.compute_marginal(frame, 2)
        else:
            self.events = np.concatenate((self.events, frame))
            self.data_x.data += self.compute_marginal(frame, 0)
            self.data_y.data += self.compute_marginal(frame, 1)
            self.data_t.data += self.compute_marginal(frame, 2)

        for i in range(3):
            self.replot_1d_marginal(i)

        for image, data in zip(
            [self.image_x, self.image_y, self.image_t],
            [self.data_x, self.data_y, self.data_t],
        ):
            if self.remove_overrange:
                # we can safely remove the edges of each DataArray since there's never
                # meaningful data there (except overrange t which we want to remove)
                data = data[1:-1, 1:-1]

            image.setImage(data, keep_levels=True)

        self.update_countrates(frame.shape[0])

    def replot_1d_marginal(self, marginal_index):
        plot: ArrayPlot
        plot, data, sum_axis = {
            0: (self.plot_x_marginal, self.data_t, 1),
            1: (self.plot_y_marginal, self.data_t, 0),
            2: (self.plot_t_marginal, self.data_x[:, :-1], 0),
        }[marginal_index]

        data = np.sum(data, axis=sum_axis)
        plot.clear()
        p = plot.plot(data)
        p.setPen(pg.mkPen(width=1, color=(0, 0, 0)))

    def update_countrates(self, n_in_frame: int) -> None:
        now = time.time()
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
