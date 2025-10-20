from dataclasses import dataclass
import pyvisa as visa
from ThorlabsPM100 import ThorlabsPM100
import asyncio

from daquiri import ManagedInstrument
from daquiri.instrument import AxisSpecification
from daquiri.panels import BasicInstrumentPanel

from PyQt5.QtWidgets import QMessageBox, QPushButton

__all__ = ("PowermeterDriver", "PowermeterController")


class PopupCalibration(QMessageBox):
    def __init__(self, meter, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.meter = meter
        self.calibrated = False
        self.setWindowTitle("Calibrate Power Meter")
        self.setText("You need to calibrate the power-meter before using it.")
        calibrate_button = QPushButton(text="calibrate", parent=self)
        continue_button = QPushButton(text="continue", parent=self)
        calibrate_button.clicked.connect(self.calibrate)
        continue_button.clicked.connect(self.safe_close)

        self.show()

    def calibrate(self):
        self.calbrated = True
        self.meter.calibrate()

    def safe_close(self):
        if self.calibrated:
            self.close()


@dataclass
class PowermeterDriver:
    permanent_resource_name: str = "USB0::0x1313::0x8072::P2011720::INSTR"
    calibration_resource_name: str = "USB0::0x1313::0x8072::1914241::INSTR"

    power_ratio: float = None

    def open(self):
        self.rm = visa.ResourceManager()
        permanent_inst = self.rm.open_resource(self.permanent_resource_name)
        calibration_inst = self.rm.open_resource(self.calibration_resource_name)
        self.permanent_meter = ThorlabsPM100(inst=permanent_inst)
        self.calibration_meter = ThorlabsPM100(inst=calibration_inst)

    def close(self):
        self.rm.close()

    def calibrate(self):
        permanent_level = self.permanent_meter.read
        actual_level = self.calibration_meter.read

        self.power_ratio = actual_level / permanent_level

    async def read_power(self):
        if self.power_ratio == None:
            popup = PopupCalibration(meter=self)
            while popup.isVisible():
                await asyncio.sleep(0.5)

        power = self.permanent_meter.read * self.power_ratio
        return power


class PowermeterPanel(BasicInstrumentPanel):
    pass


class PowermeterController(ManagedInstrument):
    driver_cls = PowermeterDriver
    # panel_cls = PowermeterPanel

    pause_live_reading = False

    power = AxisSpecification(float, where=[], read="read_power")

    async def prepare(self):
        self.driver.open()
        self.driver.calibrate()
        return await super().prepare()

    async def shutdown(self):
        self.driver.close()
        return await super().shutdown()
