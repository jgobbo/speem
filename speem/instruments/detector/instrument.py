import asyncio
import numpy as np
import itertools
from math import ceil
from pathlib import Path

# from scipy.stats import mode
import json

from autodidaqt import ManagedInstrument
from autodidaqt.instrument import AxisSpecification
from autodidaqt_common.schema import ArrayType

# from .panel import DetectorPanel
from .panel import DetectorPanel
from .common import DetectorSettings
from .etherdaq_udp import EtherDAQListener
from instruments.srs.srsdg645 import SRSDG645
from quantities import ns

__all__ = ("DetectorController", "EtherDAQUDPDriver")

DG645_ADDRESS = "130.102.202.2"
DG645_BARE_SOCKET_PORT = 5025
DG645_TELNET_PORT = 5024

DETECTOR_DIAMETER = 24  # mm
DETECTOR_BIN_WIDTH = 2677  # bins
DETECTOR_DISTANCE_PER_BIN = DETECTOR_DIAMETER / DETECTOR_BIN_WIDTH  # mm/bin

CALIBRATION_FOLDER = Path(__file__).parent.absolute() / "calibration"


class EtherDAQCommunicationError(Exception):
    """
    An Exception class used to handle situations where we cannot
    communicate with EtherDAQ for some reason: typically because
    it is not started.
    """


class EtherDAQUDPDriver:
    frame_time: float = 0.5
    timing_delay: float
    listener: EtherDAQListener
    settings = DetectorSettings
    running: bool = None
    timing_offset: float = None  # ns
    timing_slope: float = None  # ns/pixel
    t_bins: np.ndarray = None  # need this here to give the panel convient access

    def __init__(self) -> None:
        self.listener = EtherDAQListener()

        self.delay_generator = SRSDG645.open_tcpip(
            DG645_ADDRESS, DG645_BARE_SOCKET_PORT
        )

        self.delay_generator.trigger_source = (
            self.delay_generator.TriggerSource.external_rising
        )
        self.delay_generator.channel["D"].delay = (
            self.delay_generator.channel["C"],
            10 * ns,
        )

        self.delay_generator.output["CD"].level_amplitude = 1
        self.delay_generator.output["CD"].level_offset = -1.09
        self.delay_generator.output[
            "CD"
        ].polarity = self.delay_generator.LevelPolarity.negative

        with open(CALIBRATION_FOLDER / "18ns.json", "r") as f:
            timing_calibration = json.load(f)
        self.timing_offset = timing_calibration["offset"]
        self.timing_slope = timing_calibration["slope"]
        self.timing_delay = (
            float(self.delay_generator.channel["C"].delay[1]) * 1e9
        )  # ns

    def __setattr__(self, name: str, value) -> None:
        # I need to have a custom setter for timing_delay but a quick getter.
        super().__setattr__(name, value)
        if name == "timing_delay":
            self.delay_generator.channel["C"].delay = (
                self.delay_generator.channel["T0"],
                value * ns,
            )
            self.t_bins = np.linspace(
                self.bin_to_time(self.settings.bins_per_channel),
                self.bin_to_time(0),
                self.settings.data_size + 1,
            )

    def bins_to_position(self, bins: np.ndarray) -> np.ndarray:
        """converts bin from detector to position on detector (center is 0,0) in mm"""
        return np.multiply(
            np.subtract(bins, self.settings.bins_per_channel // 2),
            DETECTOR_DISTANCE_PER_BIN,
        )

    def bins_to_time(self, bins: np.ndarray) -> np.ndarray:
        """converts bin from detector to time of flight in ns"""
        return np.subtract(
            (self.timing_delay - self.timing_offset),
            np.multiply(bins, self.timing_slope),
        )

    def bin_to_time(self, bin: int) -> float:
        """same as bins_to_time but for a single bin"""
        return (self.timing_delay - self.timing_offset) - (bin * self.timing_slope)

    def coordinate_convert(self, counts: np.ndarray) -> np.ndarray:
        return np.stack(
            [
                self.bins_to_position(counts[:, 0]),
                self.bins_to_position(counts[:, 1]),
                self.bins_to_time(counts[:, 2]),
            ],
            axis=1,
        )

    def read_messages(self) -> list[list]:
        messages = []
        while True:
            try:
                messages.append(self.listener.messages.get_nowait())
            except asyncio.QueueEmpty:
                return messages

    async def read_frame(self):
        _ = self.read_messages()
        await asyncio.sleep(self.frame_time)
        contents = self.read_messages()
        all_events = list(
            itertools.chain(*[messages for _time, _id, messages, _n_failed in contents])
        )

        try:
            as_array = np.stack(all_events, axis=0)
            converted_array = self.coordinate_convert(as_array)
            return converted_array
        except ValueError:
            return np.ndarray(shape=(0, 3), dtype=int)

    async def bogus_read_frame(self):
        await asyncio.sleep(self.frame_time)
        n_points = ceil(np.random.randint(5000, 10000) * self.frame_time)
        xs = np.random.randint(
            low=0, high=self.settings.bins_per_channel * 3 / 4, size=n_points
        )
        ys = np.random.randint(
            low=self.settings.bins_per_channel / 4,
            high=self.settings.bins_per_channel,
            size=n_points,
        )
        ts = np.random.randint(
            low=self.settings.bins_per_channel / 4,
            high=self.settings.bins_per_channel * 3 / 4,
            size=n_points,
        )

        return self.coordinate_convert(np.stack([xs, ys, ts], axis=-1))


class DetectorController(ManagedInstrument):
    driver_cls = EtherDAQUDPDriver
    driver: EtherDAQUDPDriver
    panel_cls = DetectorPanel

    pause_live_reading = False

    # change to "bogus_read_frame" to simulate data instead
    frame = AxisSpecification(ArrayType(), where=[], read="bogus_read_frame")
    frame_time = AxisSpecification(float, where=["frame_time"])
    timing_delay = AxisSpecification(float, where=["timing_delay"])

    async def prepare(self):
        self.driver.listener.start()
        self.running = True
        return await super().prepare()

    async def shutdown(self):
        self.running = False
        self.driver.listener.stop()
        return await super().shutdown()

    async def run_step(self):
        if self.pause_live_reading:
            await asyncio.sleep(0.25)
        else:
            await self.frame.read()
