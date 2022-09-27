import os, asyncio, socket
from typing import Union
from pathlib import Path
from colorama import Fore, Style

from autodidaqt import ManagedInstrument

from .common import *
from .rudi_modules import *
from .panel import PowerSupplyPanel

__all__ = [
    "PowerSupplyController",
]

ROOT = Path(__file__).parent

# TODO test changes
# TODO table correction seems to be broken


class RudiEA2Driver:
    settings = PowerSupplySettings
    modules: dict[Terminal, Union[RudiHV, RudiDAC]] = {}
    voltage_offset: int = 0
    ramp_rate: int = 50  # V/s

    def __init__(self) -> None:
        for terminal, address in self.settings.terminal_configuration.items():
            try:
                if address > 31:
                    self.modules[terminal] = RudiDAC(address)
                else:
                    self.modules[terminal] = RudiHV(address)
            except socket.timeout:
                raise Exception(
                    f"Power-supply terminal {terminal} failed to connect at address {address}."
                )

    def corrected_table(self, table: dict[Electrode, float]) -> dict[str, float]:
        """
            Corrects the lens-table according to physical connections and to avoid deadzones in the modules
        """

        positive_offset = 0
        offsets = [0.0]
        while offsets:
            positive_offset += max(offsets)
            offsets = []
            for electrode, voltage in table.items():
                try:
                    min_output = self.modules[electrode].min_output
                    if voltage == 0 or electrode is Electrode.BASELINE:
                        continue
                    offset = min_output - (voltage + positive_offset)
                    if 0 < offset < 2 * min_output:
                        offsets.append(offset)
                except KeyError:
                    print(
                        f"{Fore.RED}Electrode: {electrode.name} doesn't have a module. Check the configuration and connections.{Style.RESET_ALL}"
                    )

        negative_offset = 0
        offsets = [0.0]
        while offsets:
            negative_offset -= min(offsets)
            offsets = []
            for electrode, voltage in table.items():
                try:
                    min_output = self.modules[electrode].min_output
                    if voltage == 0 or electrode is Electrode.BASELINE:
                        continue
                    offset = -min_output - (voltage + negative_offset)
                    if -2 * min_output < offset < 0:
                        offsets.append(offset)
                except KeyError:
                    print(
                        f"{Fore.RED}Electrode: {electrode.name} doesn't have a module. Check the configuration and connections.{Style.RESET_ALL}"
                    )

        final_offset = (
            positive_offset
            if positive_offset < abs(negative_offset)
            else negative_offset
        )
        corrected_table = {
            electrode: voltage + final_offset
            if electrode is not Electrode.BASELINE
            else -voltage + final_offset
            for electrode, voltage in table.items()
        }

        flipped = {Electrode.V23, Electrode.V33}
        return {
            terminal: voltage if terminal not in flipped else -voltage
            for terminal, voltage in corrected_table.items()
        }

    def bogus_apply_table(self, table: LensTable) -> None:
        for electrode, voltage in self.corrected_table(table.table).items():
            print(f"{electrode} : {voltage:.3f}")

    def apply_table(self, table: LensTable) -> None:
        for electrode, voltage in self.corrected_table(table.table).items():
            self.apply_voltage(electrode, voltage)

    def apply_voltage(self, terminal: Terminal, voltage: float) -> None:
        try:
            self.modules[terminal].set_setpoint(voltage)

        except KeyError:
            print(
                f"{Fore.RED}Terminal: {terminal.name} doesn't have a module. Check the configuration and connections.{Style.RESET_ALL}"
            )

    # async def ramp(self, module: Union[RudiHV, RudiDAC], voltage: float):
    #     curr_voltage = module.get_voltage()
    #     while abs(curr_voltage - voltage) > self.ramp_rate:
    #         curr_voltage = (
    #             curr_voltage + self.ramp_rate
    #             if voltage > curr_voltage
    #             else curr_voltage - self.ramp_rate
    #         )
    #         module.set_setpoint(curr_voltage)
    #         await asyncio.sleep(1)
    #     module.set_setpoint(voltage)

    # async def shutdown(self) -> None:
    #     for module in self.modules.values():
    #         await self.ramp(module, 0)


class PowerSupplyController(ManagedInstrument):
    driver_cls = RudiEA2Driver
    driver: RudiEA2Driver
    panel_cls = PowerSupplyPanel
    settings = PowerSupplySettings

    TABLE_FOLDER: Path = ROOT / "lens_tables"
    lens_tables: list[LensTable] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.import_lens_tables()

    def import_table_file(self, filepath: Path):
        with open(filepath, "r") as f:
            metadata = f.readline()
            table = {}
            for line in f:
                electrode, voltage = [item.strip() for item in line.split(":")]
                try:
                    table[Electrode[electrode]] = float(voltage)
                except KeyError:
                    print(
                        f"Electrode: {electrode} in lens-table file {filepath.name} isn't valid."
                    )
        return LensTable(
            table=table, name=filepath.name, conversion_map=None, metadata=metadata
        )

    def import_lens_tables(self):
        for filename in os.listdir(self.TABLE_FOLDER):
            self.lens_tables.append(
                self.import_table_file(self.TABLE_FOLDER / filename)
            )
