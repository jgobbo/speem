import time
import numpy as np
import pyqtgraph as pg
from numba import njit
from functools import partial

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

from ..common import DetectorSettings

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..instrument import DetectorController

__all__ = ("DetectorPanel",)


@njit
def _acc_into_marginal(target_marginal, count_list, ir, i_hori, i_vert, low, high):
    """
    JITted code for reaccumulating marginals so that we can support large arrays.
    """
    # step through the electron list and accumulate those in range
    in_range = (count_list[:, ir] >= low) & (count_list[:, ir] <= high)
    for count in count_list[in_range]:
        target_marginal[count[i_hori], count[i_vert]] += 1

    # Conrad's original method. I think mine is way cooler. If performance issues come up, try using this instead.
    # I wasn't able to detect a difference in testing but I didn't bother trying to time it.
    # for i in range(count_list.shape[0]):
    #     if low <= count_list[i, ir] <= high:
    #         target_marginal[count_list[i, i_hori], count_list[i, i_vert]] += 1


@njit
def _n_in_marginals(count_list: np.ndarray, x_range, y_range, t_range):
    # progressively cutting out counts that aren't in range and then counting what's left
    in_range = (count_list[:, 0] >= x_range[0]) & (count_list[:, 0] <= x_range[1])
    in_range = (count_list[in_range, 1] >= y_range[0]) & (
        count_list[in_range, 1] <= y_range[1]
    )
    in_range = (count_list[in_range, 2] >= t_range[0]) & (
        count_list[in_range, 2] <= t_range[1]
    )

    return np.count_nonzero(in_range)


class DetectorPanel(BasicInstrumentPanel):
    TITLE = "Detector"
    SIZE = (800, 400)
    DEFAULT_OPEN = True
    settings = DetectorSettings
    instrument: "DetectorController"

    DATA_SIZE = (DetectorSettings.data_size,) * 3

    data_x: np.ndarray = None
    data_y: np.ndarray = None
    data_t: np.ndarray = None
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

    electron_arrs: list[np.ndarray] = None

    x_bounds = LensSubject((0, DATA_SIZE[0]))
    t_bounds = LensSubject((0, DATA_SIZE[1]))
    y_bounds = LensSubject((0, DATA_SIZE[2]))

    show_only_latest = True
    save_only_latest = True
    show_cursors = True

    start_time: float = None
    interval_start_time: float = None
    marginal_interval_start_time: float = None
    averaging_time: float = 5

    n_elec: int = 0
    n_elec_list: list[tuple] = []
    marginal_n_elec: int = 0
    marginal_n_elec_list: list[tuple] = None

    def reset(self, *_):
        # first we reset the marginals, we keep marginals only for data storage reasons
        # data_x is a marginal with x integrated out, and similarly for data_y and data_t
        if self.data_x is None:
            self.data_x = np.zeros(
                shape=(self.DATA_SIZE[1], self.DATA_SIZE[2]), dtype=float
            )
            self.data_y = np.zeros(
                shape=(self.DATA_SIZE[0], self.DATA_SIZE[2]), dtype=float
            )
            self.data_t = np.zeros(
                shape=(self.DATA_SIZE[0], self.DATA_SIZE[1]), dtype=float
            )
        else:
            self.data_x[:] = 0
            self.data_y[:] = 0
            self.data_t[:] = 0

        self.electron_arrs = []

        now = time.time()
        self.start_time = now
        self.interval_start_time = now
        self.marginal_interval_start_time = now

        self.n_elec = 0
        self.n_elec_list = []
        self.marginal_n_elec = 0
        self.marginal_n_elec_list = []

    @debounce(1)
    def recompute_marginal(self, marginal_index):
        marginal_arr = self.get_marginal(marginal_index)
        marginal_arr[:] = 0

        low, high = self.get_bounds(marginal_index)
        ix, iy = self.get_other_marginal_indices(marginal_index)

        electron_arrs = (
            self.electron_arrs[-1:] if self.show_only_latest else self.electron_arrs
        )

        for electron_arr in electron_arrs:
            _acc_into_marginal(
                marginal_arr, electron_arr, marginal_index, ix, iy, low, high
            )

        for i in range(3):
            if i != marginal_index:
                self.replot_1d_marginal(i)

        self.marginal_n_elec = 0
        for electron_arr in self.electron_arrs:
            self.marginal_n_elec += self.n_in_marginals(electron_arr)

        self.marginal_interval_start_time = time.time()
        self.marginal_n_elec_list = []

    def recompute_all_marginals(self):
        electron_arrs = (
            self.electron_arrs[-1:] if self.show_only_latest else self.electron_arrs
        )

        for i in range(3):
            marginal_arr = self.get_marginal(i)
            marginal_arr[:] = 0

            low, high = self.get_bounds(i)
            ix, iy = self.get_other_marginal_indices(i)

            for electron_arr in electron_arrs:
                _acc_into_marginal(marginal_arr, electron_arr, i, ix, iy, low, high)

        for j in range(3):
            self.replot_1d_marginal(j)

        self.marginal_n_elec = 0
        for electron_arr in self.electron_arrs:
            self.marginal_n_elec += self.n_in_marginals(electron_arr)

        self.marginal_interval_start_time = time.time()
        self.marginal_n_elec_list = []

    def n_in_marginals(self, electron_arr: list[np.ndarray]):
        return _n_in_marginals(electron_arr, *[self.get_bounds(i) for i in range(3)])

    def update_averaging_time(self, new_time):
        try:
            self.averaging_time = float(new_time)

            # validator isn't working for some reason
            if self.averaging_time < 0.5:
                self.averaging_time = 0.5
            elif self.averaging_time > 1000:
                self.averaging_time = 1000.0

            self.interval_start_time = time.time()
            self.n_elec_list = []
            self.marginal_n_elec_list = []
        except ValueError:
            pass

    def update_frame_time(self, new_time):
        try:
            new_time = float(new_time)
        except ValueError:
            new_time = 0.5
        # validator isn't working for some reason
        if new_time < 0.1:
            new_time = 0.1
        elif new_time > 10:
            new_time = 10.0

        self.instrument.driver.frame_time = new_time

    @debounce(0.15)  # need to add parens?
    def update_timing_delay(self, new_time):
        try:
            new_time = float(new_time)

            self.instrument.driver.timing_delay = new_time
            # self.ui["timing_delay"].setText(f"{new_time}")
        except ValueError:
            pass

    def toggle_show_only_latest(self, ui_value):
        self.show_only_latest = bool(ui_value)
        self.recompute_all_marginals()

    def toggle_save_only_latest(self, ui_value):
        self.save_only_latest = bool(ui_value)
        self.recompute_all_marginals()

    def toggle_show_cursors(self, ui_value):
        self.show_cursors = bool(ui_value)
        for i in range(3):
            image, cursors = {
                0: (self.image_x, (self.cursor_horiz_x, self.cursor_vert_x)),
                1: (self.image_y, (self.cursor_horiz_y, self.cursor_vert_y)),
                2: (self.image_t, (self.cursor_horiz_t, self.cursor_vert_t)),
            }[i]
            if self.show_cursors:
                [image.addItem(cursor) for cursor in cursors]
            else:
                [image.removeItem(cursor) for cursor in cursors]

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

        # configure cursors:
        self.cursor_horiz_x = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.t_bounds
        )
        self.cursor_vert_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.y_bounds
        )

        self.cursor_horiz_y = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.t_bounds
        )
        self.cursor_vert_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )

        self.cursor_horiz_t = RescalableCursorRegion(
            orientation=CursorRegion.Horizontal, movable=True, subject=self.y_bounds
        )
        self.cursor_vert_t = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )

        self.cursor_1d_x = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.x_bounds
        )
        self.cursor_1d_y = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.y_bounds
        )
        self.cursor_1d_t = RescalableCursorRegion(
            orientation=CursorRegion.Vertical, movable=True, subject=self.t_bounds
        )

        with CollectUI(self.ui):
            vertical(
                horizontal(
                    group(
                        button("Clear", id="clear-integration"),
                        check_box("Show only latest", id="show-only-latest"),
                        check_box("Save only latest", id="save-only-latest"),
                        check_box("Show cursors", default=True, id="show-cursors"),
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
                                input_type=float,
                                subject=self.averaging_time,
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
                                input_type=float,
                                subject=self.instrument.driver.frame_time,
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
                                self.instrument.driver.timing_delay, id="timing_delay"
                            ),
                            button(">", id="delay_u"),
                            button(">>", id="delay_uu"),
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
        self.ui["show-only-latest"].subject.subscribe(self.toggle_show_only_latest)
        self.ui["save-only-latest"].subject.subscribe(self.toggle_save_only_latest)
        self.ui["show-cursors"].subject.subscribe(self.toggle_show_cursors)
        # self.ui["averaging_time"].subject.subscribe(self.update_averaging_time)
        # self.ui["frame-time"].subject.subscribe(self.update_frame_time)

        def shift_timing_delay(shift, _button_val):
            curr_delay = float(self.ui["timing_delay"].text())
            self.ui["timing_delay"].setText(str(curr_delay + shift))

        self.ui["timing_delay"].subject.subscribe(self.update_timing_delay)
        for button_name, shift in zip(
            ["delay_dd", "delay_d", "delay_u", "delay_uu"], [-10, -1, 1, 10]
        ):
            self.ui[button_name].subject.subscribe(partial(shift_timing_delay, shift))

        self.x_bounds.subscribe(lambda *_: self.recompute_marginal(0))
        self.y_bounds.subscribe(lambda *_: self.recompute_marginal(1))
        self.t_bounds.subscribe(lambda *_: self.recompute_marginal(2))

        multiplier = 1.5
        self.image_x.setFixedSize(
            self.DATA_SIZE[1] * multiplier, self.DATA_SIZE[2] * multiplier
        )
        self.image_y.setFixedSize(
            self.DATA_SIZE[0] * multiplier, self.DATA_SIZE[2] * multiplier
        )
        self.image_t.setFixedSize(
            self.DATA_SIZE[0] * multiplier, self.DATA_SIZE[1] * multiplier
        )

        self.image_x.setImage(self.data_x, keep_levels=True)
        self.image_y.setImage(self.data_y, keep_levels=True)
        self.image_t.setImage(self.data_t, keep_levels=True)
        # self.image_t.plot_item.addItem(
        #     pg.CircleROI(
        #         [
        #             self.DATA_SIZE[0] * multiplier / 2,
        #             self.DATA_SIZE[1] * multiplier / 2,
        #         ],
        #         radius=100,
        #     )
        # )
        self.image_x.show()
        self.image_y.show()
        self.image_t.show()

        self.retrieve(["frame"]).raw_value_stream.subscribe(
            self.update_frame
        )  # subscribe to updates from instrument

    def update_frame(self, value):
        value = value["value"]
        self.receive_frame(value)

    def replot_1d_marginal(self, marginal_index):
        plot, data, sum_axis, cursor = {
            0: (self.plot_x_marginal, self.data_t, 1, self.cursor_1d_x),
            1: (self.plot_y_marginal, self.data_t, 0, self.cursor_1d_y),
            2: (self.plot_t_marginal, self.data_x, 0, self.cursor_1d_t),
        }[marginal_index]

        bounds = self.get_bounds(sum_axis)

        sel = [slice(None, None)] * 2
        sel[sum_axis] = slice(*bounds)
        sel = tuple(sel)

        data = np.sum(data[sel], axis=sum_axis)
        plot.clear()
        if self.show_cursors:
            plot.addItem(cursor)
        p = plot.plot(data)
        p.setPen(pg.mkPen(width=1, color=(0, 0, 0)))

    def get_bounds(self, marginal_index):
        low, high = {
            0: self.x_bounds.value,
            1: self.y_bounds.value,
            2: self.t_bounds.value,
        }[marginal_index]

        if high < low:
            return high, low
        return low, high

    def get_marginal(self, marginal_index):
        return {
            0: self.data_x,
            1: self.data_y,
            2: self.data_t,
        }[marginal_index]

    def get_other_marginal_indices(self, marginal_index):
        return [i for i in [0, 1, 2] if i != marginal_index]

    def acc_marginal_i(self, electron_arr, marginal_index):
        low, high = self.get_bounds(marginal_index)
        marginal = self.get_marginal(marginal_index)
        if self.show_only_latest:
            marginal[:] = 0

        i_hori, i_vert = self.get_other_marginal_indices(marginal_index)
        _acc_into_marginal(
            marginal, electron_arr, marginal_index, i_hori, i_vert, low, high
        )

    def acc_marginals(self, electron_arr):
        for i in range(3):
            self.acc_marginal_i(electron_arr, i)

        for j in range(3):
            self.replot_1d_marginal(j)

    def update_n_elec_list(self, count_list: list, n_elec, now):
        count_list.append((n_elec, now))
        for count in count_list:
            if (now - count[1]) > self.averaging_time:
                count_list.remove(count)
            else:
                break

    def receive_frame(self, raw_frame: np.ndarray):
        print(self.averaging_time)
        frame: np.ndarray = raw_frame // self.settings.data_reduction
        if self.save_only_latest:
            self.reset()
            self.electron_arrs = [frame]
        else:
            self.electron_arrs.append(frame)
        self.acc_marginals(frame)

        for image, data in zip(
            [self.image_x, self.image_y, self.image_t],
            [self.data_x, self.data_y, self.data_t],
        ):
            image.setImage(data, keep_levels=True)

        now = time.time()
        n_in_frame = frame.shape[0]
        self.n_elec += n_in_frame
        n_in_marginals = self.n_in_marginals(frame)
        self.marginal_n_elec += n_in_marginals

        self.update_n_elec_list(self.n_elec_list, n_in_frame, now)
        self.update_n_elec_list(self.marginal_n_elec_list, n_in_marginals, now)

        if now != self.start_time:
            avg_since_start = self.n_elec / (now - self.start_time)
            marginal_avg_since_start = self.marginal_n_elec / (now - self.start_time)

            n_elec_interval = sum(n_elec for (n_elec, _time) in self.n_elec_list)
            marginal_n_elec_interval = sum(
                n_elec for (n_elec, _time) in self.marginal_n_elec_list
            )

            if (now - self.interval_start_time) < self.averaging_time:
                avg_interval = n_elec_interval / (now - self.interval_start_time)
                marginal_avg_interval = marginal_n_elec_interval / (
                    now - self.marginal_interval_start_time
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

            self.ui["total-counts"].setText(str(self.n_elec))
