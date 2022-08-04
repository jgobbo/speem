from dataclasses import dataclass
from autodidaqt import ManagedInstrument
from autodidaqt.instrument import AxisSpecification
from autodidaqt_common.schema import ArrayType

# from .calibrated_supply import CalibratedSupply
from .common import PowerSupplySettings
from .panel import PowerSupplyPanel

__all__ = ("PowerSupplyController", "HVC20Driver")

# class HVC20CommunicationError(Exception):
#     """
#     An Exception class used to handle situations where we cannot
#     communicate with the power supply for some reason.
#     """


class HVC20Driver:
    settings = PowerSupplySettings
    # supply: CalibratedSupply = None
    pass_energy: float = 1

    def __init__(self):
        pass
        # super().__init__(self)
        # self.supply = CalibratedSupply(config=None)

    def read(self):
        # having no read causes problems?
        pass

    def set_voltages(self, table: dict[str, float]):
        pass

    def bogus_set_voltages(self, table: dict[str, float]):
        for key, val in table.items():
            print(f"{key} : {val:.3f}")


class PowerSupplyController(ManagedInstrument):
    driver_cls = HVC20Driver
    panel_cls = PowerSupplyPanel
    settings = PowerSupplySettings

    voltages = AxisSpecification(
        ArrayType(shape=settings.n_electrodes),
        where=[],
        read="read",
        write="bogus_set_voltages",
    )
    pass_energy = AxisSpecification(float, where=["pass_energy"])

    # async def prepare(self):
    #     return await super().prepare()

    # async def shutdown(self):
    #     return await super().shutdown()
