from pathlib import Path

import rpyc
from rpyc.utils.server import ThreadedServer

from .calibrated_supply import CalibratedSupply


class CalibratedSupplyService(rpyc.Service):
    def __init__(self, supply: CalibratedSupply):
        self.supply = supply
        super().__init__()

    def exposed_set_voltage(self, name: str, value: float):
        setattr(self.supply, name, value)

    def exposed_get_voltages(self):
        return self.supply.voltages

    def exposed_set_table(self, table_name: str):
        self.supply.lens_table = table_name

    def exposed_get_table(self) -> str:
        return self.supply.lens_table

    def exposed_available_lens_tables(self):
        return self.supply.config.lens_tables


supply = CalibratedSupply.from_config(Path(__file__).parent / 'config' / 'config_stof_2020.toml')
supply.startup()
server = ThreadedServer(CalibratedSupplyService(supply), port=18861)
#supply.shutdown()