from pathlib import Path
import asyncio
import time
import os
import numpy as np
import warnings
from astropy.io import fits
from loguru import logger

from instruments.detector.instrument import EtherDAQCommunicationError

from .common import DetectorSettings, EtherDAQSimulatorSettings


def read_photon_list(path: Path):
    with fits.open(str(path.absolute()), ignore_missing_end=True, lazy_load_hdus=False) as f:
        data = f[1].data

    data = data.newbyteorder("S")

    raw_xs = data["X"].byteswap().newbyteorder()
    raw_ys = data["Y"].byteswap().newbyteorder()

    xs = raw_xs[::2]
    ys = raw_ys[::2]
    ts = raw_ys[1::2]

    return (xs, ys, ts)


class EtherDAQDriver:
    settings: DetectorSettings = None

    working_directory = None

    dispose_after = False
    communications_file_name = None
    active_communications_file = None
    query_time = 0.25
    fail_after_proportion = 3

    def __init__(self):
        self.settings = DetectorSettings()

    def clear_files(self):
        candidates = [self.settings.output_file_name, self.active_communications_file]
        clear_ps = [Path(f) for f in candidates if f]
        for clear_p in clear_ps:
            if clear_p.exists():
                try:
                    clear_p.unlink()
                except:
                    pass

    async def wait_until_output_exists(self):
        # perform an initial wait in correspondence with how long we think
        # the acquisition will take if we are performing acquisition in seconds
        # rather than in counts
        start = time.time()
        fail_after = None
        if self.settings.acquisition_type == "seconds":
            expected_total_time = self.settings.integration_time * self.settings.n_iterations
            fail_after = start + self.fail_after_proportion * expected_total_time

            await asyncio.sleep(expected_total_time - 0.25)  # no need to be greedy

        while True:
            if fail_after is not None and (time.time() > fail_after):
                raise EtherDAQCommunicationError(
                    f"File not found after {fail_after - start} seconds."
                )

            if Path(self.settings.output_file_name).exists():
                # wait until file is actually readable, i.e. EtherDAQ has actually closed it
                try:
                    os.rename(self.settings.output_file_name, self.settings.output_file_name)
                    return
                except (IOError, OSError):
                    # need to keep waiting since the file is still open
                    pass

            await asyncio.sleep(0.1)

    async def write_communications_file(self):
        message = self.settings.as_message()
        with open(self.communications_file_name, "w+") as f:
            f.write("\n".join(message))

        self.active_communications_file = self.communications_file_name
        logger.info(
            f"EtherDAQDriver opened communications file to EtherDAQ: {self.active_communications_file}"
        )

    async def bogus_read_frame(self):
        await asyncio.sleep(0.01)
        n_points = np.random.randint(5000, 10000)
        xs = np.random.randint(low=0, high=self.settings.data_size * 3 / 4, size=n_points)
        ys = np.random.randint(
            low=self.settings.data_size / 4, high=self.settings.data_size, size=n_points
        )
        ts = np.random.randint(
            low=self.settings.data_size / 4, high=self.settings.data_size * 3 / 4, size=n_points
        )

        return np.stack([xs, ys, ts], axis=-1)

    async def read_frame(self):
        # keep attempting reads if EtherDAQ is not functioning or misbehaves
        while True:
            try:
                self.clear_files()
                await self.write_communications_file()
                await self.wait_until_output_exists()

                output_path = Path(self.settings.output_file_name).resolve()
                try:
                    x, y, z = read_photon_list(output_path)
                except OSError:
                    x = np.array([], dtype=np.int16)
                    y, z = x[:], x[:]
                    warnings.warn("Corrupt fits file, removing...")
                    if output_path.exists():
                        output_path.unlink()
                data = (
                    x // self.settings.data_reduction,
                    y // self.settings.data_reduction,
                    z // self.settings.data_reduction,
                )
                # print(data)
                # print(len(x))
                def avg(arr):
                    return arr.astype(np.float64).mean()

                print(f"<x> = {data[0]}, <y> = {data[1]}, <z> = {data[2]}")
                output_path.unlink()

                return np.stack(data, axis=-1)
            except EtherDAQCommunicationError as e:
                logger.warning(f"No communication with EtherDAQ: {e}")
                continue
