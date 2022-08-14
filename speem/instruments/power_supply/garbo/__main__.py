from scienta_7048.calibrated_supply import CalibratedSupply

supply = CalibratedSupply.from_config('config/config_stof_2020.toml')
print(supply.voltages)
print(supply.is_operational)

supply.startup()
supply.L1V1 = 0.
supply.lens_table = 'llt_sd_11eV_TI'
supply.shutdown()