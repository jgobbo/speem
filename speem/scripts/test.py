from autodidaqt import AutodiDAQt
from speem.instruments import *


app = AutodiDAQt(__name__, managed_instruments={"power_meter": PowermeterController,})

if __name__ == "__main__":
    app.start()

# from daq.PM100USB import PowermeterDriver
# from time import sleep

# meter = PowermeterDriver()

# meter.calibrate()
# print(meter.read_power())


# from daq.MDT693B.instrument import MDTDriver

# mdt = MDTDriver()
# mdt.open()
# mdt.close()


# from beam_pointer.lib.MDT_COMMAND_LIB_TEST import *
# from beam_pointer.lib.MDT_COMMAND_LIB import *

# SERIAL_NUMBER = mdtListDevices()[0][0]
# BAUD_RATE = 115200
# TIMEOUT = 3

# MDT693BExample(SERIAL_NUMBER)

# from beam_pointer.instrument import *

# driver = MDTDriver()
# print(driver.voltages)
# driver.x_voltage = 3
# print(driver.voltages)


# driver.start()


# hdl = mdtOpen(SERIAL_NUMBER, BAUD_RATE, TIMEOUT)
# print(hdl)
# print(mdtClose(hdl))

# id=[]
# mdtGetId(hdl,id)
# print(id)


# hdl = CommonFunc(SERIAL_NUMBER)
# Check_X_AXiS(hdl)


# from daq.MDT693B.MDT_COMMAND_LIB import *

# print(mdtListDevices())

# SERIAL_NUMBER = '1904154480-07'
# BAUD_RATE = 115200
# TIMEOUT = 3

# hdl = mdtOpen(SERIAL_NUMBER, BAUD_RATE, TIMEOUT)
# print('hdl', hdl)

# print(mdtIsOpen(SERIAL_NUMBER))

# id=[]

# print(mdtGetId(hdl, id))

# print(id)
