import asyncio
import os
from math import ceil
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

# TODO fix the deadzone issue


class RudiEA2Driver:
    settings = PowerSupplySettings
    modules: dict[Electrode, Union[RudiHV, RudiDAC]] = {}
    voltage_offset: int = 0

    def __init__(self) -> None:
        for electrode, address in self.settings.electrode_configuration.items():
            if address > 30:
                self.modules[electrode] = RudiDAC(address)
            else:
                self.modules[electrode] = RudiHV(address)

        # ANODE & MCP always operate at relatively high voltages
        # so we should ignore them when setting the voltage offset
        # anode_address = self.settings.electrode_configuration[Electrode.ANODE]
        # mcp_address = self.settings.electrode_configuration[Electrode.MCP]

        # for module in self.modules.values():
        #     if (module.min_output > self.voltage_offset) and (
        #         module.module_address not in {anode_address, mcp_address}
        #     ):
        #         # modules have a deadzone around 0, so we need to offset all voltages and correct with the baseline
        #         self.voltage_offset = ceil(module.min_output)

    def corrected_table(self, table: dict[str, float]) -> dict[str, float]:
        try:
            correction = table[Electrode.V13]
        except KeyError:
            correction = 0

        for electrode, voltage in table.items():
            if electrode != Electrode.V13:
                table[electrode] = voltage - correction
        return table

    def bogus_apply_table(self, table: LensTable) -> None:
        for electrode, voltage in self.corrected_table(table.table).items():
            print(f"{electrode} : {voltage:.3f}")

    def apply_table(self, table: LensTable) -> None:
        # asyncio.gather(
        #     *[
        #         self.apply_voltage(electrode, voltage)
        #         for electrode, voltage in self.corrected_table(table.table).items()
        #     ]
        # )

        for electrode, voltage in self.corrected_table(table.table).items():
            self.apply_voltage(electrode, voltage)

    def apply_voltage(self, electrode: Electrode, voltage: float) -> None:
        try:
            module = self.modules[electrode]

            corrected_voltage = (
                voltage + self.voltage_offset
                if electrode != Electrode.BASELINE
                else voltage - self.voltage_offset
            )
            print(
                f"{Fore.BLUE}setting {corrected_voltage} on {electrode.name} with address {module.module_address}{Style.RESET_ALL}"
            )
            module.set_setpoint(corrected_voltage)

        except KeyError:
            print(
                f"{Fore.RED}Electrode: {electrode.name} doesn't have a module. Check the configuration and connections.{Style.RESET_ALL}"
            )


class PowerSupplyController(ManagedInstrument):
    driver_cls = RudiEA2Driver
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
                if electrode in {"ANODE", "MCP"}:
                    print(
                        f"""Anode and MCP voltages should never be included in lens tables.
                            {filepath.name} contains Anode and MCP values"""
                    )
                else:
                    try:
                        table[Electrode[electrode]] = voltage
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

    # async def prepare(self):
    #     self.import_lens_tables()
    #     return await super().prepare()

    # async def shutdown(self):
    #     return await super().shutdown()
