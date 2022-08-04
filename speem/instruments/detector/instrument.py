import asyncio
import numpy as np
import itertools
from math import ceil

from autodidaqt import ManagedInstrument
from autodidaqt.instrument import AxisSpecification
from autodidaqt_common.schema import ArrayType

from .panel import DetectorPanel
from .common import DetectorSettings
from .etherdaq_udp import EtherDAQListener

__all__ = ("DetectorController", "EtherDAQUDPDriver")


class EtherDAQCommunicationError(Exception):
    """
    An Exception class used to handle situations where we cannot
    communicate with EtherDAQ for some reason: typically because
    it is not started.
    """


class EtherDAQUDPDriver:
    frame_time: float = 0.5
    listener: EtherDAQListener
    settings = DetectorSettings
    running: bool = None

    def __init__(self) -> None:
        self.listener = EtherDAQListener()

    def set_frame_time(
        self, value
    ):  # seemingly necessary to set attributes during scans
        self.frame_time = value

    def read_messages(self) -> list[list]:
        messages = []
        while not self.listener.messages.empty():
            messages.append(self.listener.messages.get())
        return messages

    async def read_frame(self):
        _ = self.read_messages()
        await asyncio.sleep(self.frame_time)
        contents = self.read_messages()
        all_events = list(
            itertools.chain(*[messages for _time, _id, messages in contents])
        )

        try:
            as_array = np.stack(all_events, axis=0)
        except:
            as_array = np.ndarray(shape=(0, 3), dtype=int)

        # print("Received:", as_array)
        # try:
        #     time_mode = mode([t for t in as_array[:, 2]]).mode[0]
        #     print(f"{time_mode = }")
        # except Exception:
        #     print("no counts")

        return as_array

    async def bogus_read_frame(self):
        await asyncio.sleep(self.frame_time)
        n_points = ceil(np.random.randint(5000, 10000) * self.frame_time)
        xs = np.random.randint(
            low=0, high=self.settings.input_size * 3 / 4, size=n_points
        )
        ys = np.random.randint(
            low=self.settings.input_size / 4,
            high=self.settings.input_size,
            size=n_points,
        )
        ts = np.random.randint(
            low=self.settings.input_size / 4,
            high=self.settings.input_size * 3 / 4,
            size=n_points,
        )

        return np.stack([xs, ys, ts], axis=-1)


class DetectorController(ManagedInstrument):
    driver_cls = EtherDAQUDPDriver
    panel_cls = DetectorPanel

    pause_live_reading = False

    # change to "bogus_read_frame" to simulate data instead
    frame = AxisSpecification(ArrayType(), where=[], read="bogus_read_frame")

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
            await asyncio.sleep(1)
        else:
            await self.frame.read()

