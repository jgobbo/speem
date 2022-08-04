import time
import numpy as np
import pyqtgraph as pg
from numba import njit

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
from autodidaqt.ui.lens import LensSubject
from autodidaqt.ui.pg_extras import (
    ArrayImageView,
    ArrayPlot,
    CursorRegion,
    RescalableCursorRegion,
)

from .common import DetectorSettings

__all__ = ("DetectorPanel",)

# TODO redo a lot of stuff to make it more efficient after all the janky changes added


@njit
def _acc_into_marginal(target_marginal, index_list, ir, ix, iy, low, high):
    """
    JITted code for reaccumulating marginals so that we can support large arrays.
    """
    # step through the electron list and accumulate those in range
    for i in range(index_list.shape[0]):
        if low <= index_list[i, ir] <= high:
            target_marginal[index_list[i, ix], index_list[i, iy]] += 1


@njit
def in_marginal(value, low, high):
    return low <= value <= high


class DetectorPanel(BasicInstrumentPanel):
    TITLE = "Detector"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = DetectorSettings

    DATA_SIZE = (DetectorSettings.data_size,) * 3

    data_x: np.ndarray = None
    data_y: np.ndarray = None
    data_z: np.ndarray = None
    image_x: ArrayImageView = None
    image_y: ArrayImageView = None
    image_z: ArrayImageView = None

    cursor_1d_x = None
    cursor_1d_y = None
    cursor_1d_z = None

    electron_arrs: list[np.ndarray] = None

    x_bounds = LensSubject((0, DATA_SIZE[0]))
    z_bounds = LensSubject((0, DATA_SIZE[1]))
    y_bounds = LensSubject((0, DATA_SIZE[2]))

    show_only_latest = True
    show_cursors = True

    start_time: float = None
    interval_start_time: float = None
    n_elec_list: list[tuple] = []
    n_elec: int = 0
    averaging_time: float = 5

    marginal_interval_start_time: float = None
    marginal_n_elec: int = 0
    marginal_n_elec_list: list[tuple] = None

    def reset(self, *_):
        # first we reset the marginals, we keep marginals only for data storage reasons
        # data_x is a marginal with x integrated out, and similarly for data_y and data_z
        if self.data_x is None:
            self.data_x = np.zeros(
                shape=(self.DATA_SIZE[1], self.DATA_SIZE[2]), dtype=float
            )
            self.data_y = np.zeros(
                shape=(self.DATA_SIZE[0], self.DATA_SIZE[2]), dtype=float
            )
            self.data_z = np.zeros(
                shape=(self.DATA_SIZE[0], self.DATA_SIZE[1]), dtype=float
            )
        else:
            self.data_x[:] = 0
            self.data_y[:] = 0
            self.data_z[:] = 0

        self.electron_arrs = []

        now = time.time()
        self.start_time = now
        self.interval_start_time = now
        self.marginal_interval_start_time = now

        self.n_elec = 0
        self.n_elec_list = []
        self.marginal_n_elec = 0
        self.marginal_n_elec_list = []

    @debounce(0.2)
    def recompute_marginal(self, marginal_index=0, recompute_counts=True):
        marginal_arr = {0: self.data_x, 1: self.data_y, 2: self.data_z}[marginal_index]

        marginal_arr[:] = 0

        low, high = self.get_bounds(marginal_index)
        ix, iy = self.get_other_marginal_indices(marginal_index)

        electron_arrs = self.electron_arrs
        if self.show_only_latest:
            electron_arrs = electron_arrs[-1:]

        for electron_arr in electron_arrs:
            _acc_into_marginal(
                marginal_arr, electron_arr, marginal_index, ix, iy, low, high
            )

        for i in range(3):
            if i != marginal_index:
                self.replot_1d_marginal(i)

        # resetting marginal count-rates
        if recompute_counts:
            self.marginal_n_elec = 0
            for electron_arr in self.electron_arrs:
                self.marginal_n_elec += self.n_in_marginals(electron_arr)

            self.marginal_interval_start_time = time.time()
            self.marginal_n_elec_list = []

    def recompute_all_marginals(self):
        for i in range(3):
            if i == 2:
                self.recompute_marginal(
                    i, True
                )  # TODO set to True again once it isn't so slow
            else:
                self.recompute_marginal(i, False)

    def in_all_marginals(self, count):
        for i in range(3):
            if not in_marginal(count[i], *self.get_bounds(i)):
                return False
        return True

    def n_in_marginals(self, frame):
        n_total = 0
        for count in frame:
            if self.in_all_marginals(count):
                n_total += 1
        return n_total

    def update_averaging_time(self, new_time):
        self.averaging_time = float(new_time)

        # validator isn't working for some reason
        if self.averaging_time < 0.5:
            self.averaging_time = 0.5
        elif self.averaging_time > 1000:
            self.averaging_time = 1000.0

        now = time.time()
        self.interval_start_time = now
        self.marginal_interval_start_time = now
        self.n_elec_list = []
        self.marginal_n_elec_list = []

    def update_frame_time(self, new_time):
        new_time = float(new_time)
        # validator isn't working for some reason
        if new_time < 0.1:
            new_time = 0.1
        elif new_time > 10:
            new_time = 10.0

        self.instrument.driver.frame_time = new_time

    def toggle_show_only_latest(self, ui_value):
        self.show_only_latest = bool(ui_value)
        self.recompute_all_marginals()

    def toggle_show_cursors(self, ui_value):
        self.show_cursors = bool(ui_value)
        # unfinished
        # I tried adding in self.widget=self.layout() to rebuild ui

    def layout(self):
        self.reset()

        # Here is where we configure the main data plots
        # and selection cursors. Because we want to link the views
        # of the different plots, this becomes a little repetetive and complex
        # but there's no need to refactor at the moment because this is the only
        # view where this sort of logic happens, (unlike, for instance, in the PyARPES code)
        self.image_x = ArrayImageView()
        self.image_y = ArrayImageView()
        self.image_z = ArrayImageView()
        self.plot_x_marginal = ArrayPlot(orientation="horiz")
        self.plot_y_marginal = ArrayPlot(orientation="horiz")
        self.plot_z_marginal = ArrayPlot(orientation="horiz")

        # configure cursors:
        cursor_horiz_x = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.z_bounds
        )
        cursor_vert_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.y_bounds
        )

        cursor_horiz_y = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.z_bounds
        )
        cursor_vert_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )

        cursor_horiz_z = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.y_bounds
        )
        cursor_vert_z = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )

        self.cursor_1d_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )
        self.cursor_1d_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.y_bounds
        )
        self.cursor_1d_z = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.z_bounds
        )

        self.image_x.addItem(cursor_vert_x)
        self.image_x.addItem(cursor_horiz_x)
        self.image_y.addItem(cursor_vert_y)
        self.image_y.addItem(cursor_horiz_y)
        self.image_z.addItem(cursor_vert_z)
        self.image_z.addItem(cursor_horiz_z)

        self.plot_x_marginal.addItem(self.cursor_1d_x)
        self.plot_y_marginal.addItem(self.cursor_1d_y)
        self.plot_z_marginal.addItem(self.cursor_1d_z)

        with CollectUI(self.ui):
            vertical(
                horizontal(
                    group(
                        button("Clear", id="clear-integration",),
                        check_box("Show only latest", id="show-only-latest",),
                    ),
                    group(
                        "counts/s",
                        horizontal(
                            group(
                                "total",
                                label("rice", id="global-count-rate"),
                                label("beans", id="interval-count-rate"),
                            ),
                            group(
                                "marginal",
                                label("thai", id="marginal-global-count-rate"),
                                label("curry", id="marginal-interval-count-rate"),
                            ),
                        ),
                        horizontal(
                            "Averaging interval [s]: ",
                            numeric_input(
                                self.averaging_time,
                                float,
                                validator_settings={
                                    "bottom": 0.5,
                                    "top": 1000,
                                    "decimals": 3,
                                },
                                id="averaging_time",
                            ),
                        ),
                        horizontal(
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
                    ),
                ),
                self.plot_x_marginal,
                self.plot_y_marginal,
                self.plot_z_marginal,
                horizontal(
                    group("x/z", self.image_y),
                    group("x/y", self.image_z),
                    group("y/z", self.image_x),
                ),
                widget=self,
            )

        self.ui["clear-integration"].subject.subscribe(self.reset)
        self.ui["show-only-latest"].subject.subscribe(self.toggle_show_only_latest)
        self.ui["averaging_time"].subject.subscribe(self.update_averaging_time)
        self.ui["frame-time"].subject.subscribe(self.update_frame_time)

        self.x_bounds.subscribe(lambda *_: self.recompute_marginal(0))
        self.y_bounds.subscribe(lambda *_: self.recompute_marginal(1))
        self.z_bounds.subscribe(lambda *_: self.recompute_marginal(2))

        self.image_x.setFixedSize(self.DATA_SIZE[1], self.DATA_SIZE[2])
        self.image_y.setFixedSize(self.DATA_SIZE[0], self.DATA_SIZE[2])
        self.image_z.setFixedSize(self.DATA_SIZE[0], self.DATA_SIZE[1])

        self.image_x.setImage(self.data_x, keep_levels=True)
        self.image_y.setImage(self.data_y, keep_levels=True)
        self.image_z.setImage(self.data_z, keep_levels=True)
        self.image_x.show()
        self.image_y.show()
        self.image_z.show()

        self.replot_1d_marginal(0)
        self.replot_1d_marginal(1)
        self.replot_1d_marginal(2)

        self.retrieve(["frame"]).raw_value_stream.subscribe(
            self.update_frame
        )  # subscribe to updates from spectrometer

    def update_frame(self, value):
        value = value["value"]
        self.receive_frame(value)

    def replot_1d_marginal(self, marginal_index):
        plot, data, sum_axis, cursor = {
            0: (self.plot_x_marginal, self.data_z, 1, self.cursor_1d_x),
            1: (self.plot_y_marginal, self.data_z, 0, self.cursor_1d_y),
            2: (self.plot_z_marginal, self.data_x, 0, self.cursor_1d_z),
        }[marginal_index]

        bounds = self.get_bounds(sum_axis)

        sel = [slice(None, None)] * 2
        sel[sum_axis] = slice(*bounds)
        sel = tuple(sel)

        data = np.sum(data[sel], axis=sum_axis)
        plot.clear()
        plot.addItem(cursor)
        p = plot.plot(data)
        p.setPen(pg.mkPen(width=1, color=(0, 0, 0)))

    def get_bounds(self, marginal_index):
        low, high = {
            0: self.x_bounds.value,
            1: self.y_bounds.value,
            2: self.z_bounds.value,
        }[marginal_index]

        if high < low:
            low, high = high, low

        return low, high

    def get_marginal(self, marginal_index):
        return {0: self.data_x, 1: self.data_y, 2: self.data_z,}[marginal_index]

    def get_other_marginal_indices(self, marginal_index):
        return [i for i in [0, 1, 2] if i != marginal_index]

    def acc_marginal_i(self, electron_arr, marginal_index):
        low, high = self.get_bounds(marginal_index)
        marginal = self.get_marginal(marginal_index)

        if self.show_only_latest:
            marginal[:] = 0

        ix, iy = self.get_other_marginal_indices(marginal_index)
        _acc_into_marginal(marginal, electron_arr, marginal_index, ix, iy, low, high)

    def acc_marginals(self, electron_arr):
        for i in range(3):
            self.acc_marginal_i(electron_arr, i)

        for j in range(3):
            self.replot_1d_marginal(j)

    def update_n_elec_list(self, list: list, n_elec, now):
        list.append((n_elec, now))
        for frame in list:
            if (now - frame[1]) > self.averaging_time:
                list.remove(frame)

    def receive_frame(self, raw_frame: np.ndarray):
        frame: np.ndarray = raw_frame // self.settings.data_reduction
        self.acc_marginals(frame)
        self.electron_arrs.append(frame)

        now = time.time()
        n_in_frame = frame.shape[0]
        self.n_elec += n_in_frame
        n_in_marginals = self.n_in_marginals(frame)
        self.marginal_n_elec += n_in_marginals

        self.update_n_elec_list(self.n_elec_list, n_in_frame, now)
        # marginal_n_elec_list can get messy when marginals are recomputed
        self.update_n_elec_list(self.marginal_n_elec_list, n_in_marginals, now)

        if now != self.start_time:
            avg_since_start = self.n_elec / (now - self.start_time)
            marginal_avg_since_start = self.marginal_n_elec / (now - self.start_time)

            n_elec_interval = sum(frame[0] for frame in self.n_elec_list)
            marginal_n_elec_interval = sum(
                frame[0] for frame in self.marginal_n_elec_list
            )

            if (now - self.interval_start_time) < self.averaging_time:
                avg_interval = n_elec_interval / (now - self.interval_start_time)
                marginal_avg_interval = marginal_n_elec_interval / (
                    now - self.interval_start_time
                )
            else:
                avg_interval = n_elec_interval / self.averaging_time
                marginal_avg_interval = marginal_n_elec_interval / self.averaging_time

            self.ui["global-count-rate"].setText(f"From start: {avg_since_start:.3f}")
            self.ui["interval-count-rate"].setText(f"In interval: {avg_interval:.3f}")

            self.ui["marginal-global-count-rate"].setText(
                f"From start: {marginal_avg_since_start:.3f}"
            )
            self.ui["marginal-interval-count-rate"].setText(
                f"In interval: {marginal_avg_interval:.3f}"
            )

        for image, data in zip(
            [self.image_x, self.image_y, self.image_z],
            [self.data_x, self.data_y, self.data_z],
        ):
            image.setImage(data, keep_levels=True)

