from speem.instruments.power_supply.rudi_modules import *
from speem.instruments.power_supply.common import *

for addr in PowerSupplySettings.electrode_configuration.values():
    if addr > 30:
        rudi = RudiDAC(addr)
    else:
        rudi = RudiHV(addr)
    try:
        rudi.show_info()
        # print(f"{addr}: status - {rudi.get_status()}")
        # print(rudi.get_voltage())
        # print(rudi.get_setpoint())
    except Exception:
        print(f"address {addr} failed")

