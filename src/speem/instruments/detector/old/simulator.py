from pathlib import Path
import time
import numpy as np

from .common import DetectorSettings, EtherDAQSimulatorSettings
from astropy.table import Table


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


class EtherDAQEchoer:
    wait_between = 1.0
    dest_format_string: str
    command_path: Path = None
    settings: DetectorSettings = None

    def __init__(self, dest_format_string, command_path, settings):
        self.dest_format_string = dest_format_string
        self.dest_format_string.format(0)  # Sanity check
        self.command_path = command_path
        self.settings = settings

    def write_command_file(self):
        message = self.settings.as_message()
        with open(str(self.command_path), "w+") as f:
            f.write("\n".join(message))

    def wait_until_output_exists(self):
        while True:
            if Path(self.settings.output_file_name).exists():
                time.sleep(0.2)
                return

            time.sleep(0.05)

    def read_output(self):
        output_path = Path(self.settings.output_file_name)
        data = read_photon_list(output_path)
        print("RECEIVED DATA:")
        print(data)
        output_path.unlink()

    def start(self):
        for i in range(10):
            # Write a command file
            self.settings.output_file_name = self.dest_format_string.format(i)
            self.write_command_file()

            self.wait_until_output_exists()
            self.read_output()
            time.sleep(self.wait_between)


class EtherDAQSimulator:
    config: EtherDAQSimulatorSettings
    command: DetectorSettings

    def __init__(self):
        self.config = EtherDAQSimulatorSettings()
        self.command = None

    def generate_events(self, n_events: int = 5000):
        rs = np.random.triangular(left=0, right=0.9, mode=0.9, size=n_events)
        thetas = np.random.uniform(0, 2 * np.pi, size=n_events)
        ts = np.random.uniform(0.05, 0.95, size=n_events)

        xs, ys = np.sin(thetas) * rs, np.cos(thetas) * rs
        xs = (xs + 1) / 2
        ys = (xs + 1) / 2

        xs = self.config.shape[0] * xs
        ys = self.config.shape[1] * ys
        ts = self.config.shape[2] * ts

        xs = np.floor(xs)
        ys = np.floor(ys)
        ts = np.floor(ts)

        return xs.astype(int), ys.astype(int), ts.astype(int)

    @staticmethod
    def parse_commands(raw_command_lines):
        command_config = [line.split(";")[0].strip() for line in raw_command_lines]
        command_config = [l for l in command_config if l]
        return DetectorSettings(
            acquisition_type=command_config[0],
            integration_time=float(command_config[1]),
            n_iterations=int(command_config[2]),
            output_file_name=command_config[3],
        )

    def handle_command(self):
        total_wait_time = self.command.n_iterations * self.command.integration_time
        print(f"waiting {total_wait_time}")
        time.sleep(total_wait_time)

        print("Generating events")
        events = self.generate_events(1000)
        self.write_fits(events)
        print("Finished writing")
        self.command = None  # all done!

    @staticmethod
    def interleave_arrays(a, b):
        c = np.empty((a.size + b.size,), dtype=a.dtype)
        c[0::2] = a
        c[1::2] = b
        return c

    def write_fits(self, events):
        xs, ys, ts = events

        # Need to generate the actual data format which
        # consists of pairs of observations because there
        # are two DAQ boards
        X = self.interleave_arrays(xs, xs * 0)
        Y = self.interleave_arrays(ys, ts)
        P = self.interleave_arrays(xs * 0, xs * 0)

        t = Table([X, Y, P], names=("X", "Y", "P"))
        t.write(self.command.output_file_name, format="fits")

    def start(self):
        while True:
            time.sleep(self.config.communication_time / 1000)
            commands = list(self.config.command_path.glob("*"))
            if commands:
                command_file = commands[0]
                try:
                    with open(str(command_file.absolute()), "r") as f:
                        command_lines = f.readlines()

                    command_file.unlink()
                    self.command = self.parse_commands(command_lines)
                    self.handle_command()

                except IOError:
                    pass
            else:
                print("Nothing to handle.")
