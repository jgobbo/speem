import os, socket
from typing import Union
from pathlib import Path
from colorama import Fore, Style
from loguru import logger

from autodidaqt import ManagedInstrument
from autodidaqt.instrument.spec import (
    ChoicePropertySpecification,
)

# from modbus_tk.modbus_tcp import TcpMaster
from pymodbus.client import ModbusTcpClient, AsyncModbusTcpClient
from .common import *

# from .rudi_modules import *
from .rudi_modules_pymodbus import *
from .panel import PowerSupplyPanel

__all__ = [
    "PowerSupplyController",
]

ROOT = Path(__file__).parent


class RudiEA2Driver:
    settings = PowerSupplySettings
    rudi_tcp_client: ModbusTcpClient = None
    modules: dict[Terminal, Union[RudiHV, RudiDAC]] = {}
    voltage_offset: int = 0

    def __init__(self) -> None:
        # rudi_tcp_master = TcpMaster(RUDI_IP_ADDRESS, timeout_in_sec=0.5)
        self.rudi_tcp_client = ModbusTcpClient(RUDI_IP_ADDRESS)
        self.rudi_tcp_client.connect()

        not_shorted = []
        for terminal, address in self.settings.terminal_configuration.items():
            try:
                if address > 31:
                    # self.modules[terminal] = RudiDAC(rudi_tcp_master, address)
                    self.modules[terminal] = RudiDAC(self.rudi_tcp_client, address)
                else:
                    # self.modules[terminal] = RudiHV(rudi_tcp_master, address)
                    self.modules[terminal] = RudiHV(self.rudi_tcp_client, address)
                    if not self.modules[terminal].shorted_on_startup:
                        not_shorted.append(terminal)
            except socket.timeout:
                raise Exception(
                    f"Power-supply terminal {terminal} timed out trying to connect at address {address}."
                )
        if not_shorted:
            logger.warning(
                f"Terminals:{not_shorted} weren't shut down properly. Using default voltage ranges for them."
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

    def shutdown(self) -> None:
        self.rudi_tcp_client.close()


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
        self.lens_table = ChoicePropertySpecification(
            where=[], choices=self.lens_tables, labels=lambda table, _: table.name
        )

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

    async def shutdown(self):
        self.driver.shutdown()
        return await super().shutdown()
