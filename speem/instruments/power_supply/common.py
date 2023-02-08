from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "Electrode",
    "Corrector",
    "Detector",
    "Terminal",
    "PowerSupplySettings",
    "LensTable",
]


class Electrode(str, Enum):  # str subclassing required for json serialization
    BASELINE = auto()
    V00 = auto()
    V01 = auto()
    V02 = auto()
    V11 = auto()
    V12 = auto()
    V13 = auto()
    V21 = auto()
    V22 = auto()
    V23 = auto()
    V31 = auto()
    V32 = auto()
    V33 = auto()

    def __repr__(self) -> str:
        return self.name


class Corrector(Enum):
    ST0 = auto()
    ST1 = auto()
    ST2 = auto()
    ST3 = auto()
    D00 = auto()
    D01 = auto()
    D02 = auto()
    D10 = auto()
    D11 = auto()
    D12 = auto()

    def __repr__(self) -> str:
        return self.name


class Detector(Enum):
    GRID = auto()
    MCP = auto()
    ANODE = auto()

    def __repr__(self) -> str:
        return self.name


Terminal = Union[Electrode, Corrector, Detector]

null_configuration = {}

temp_configuration = {
    Detector.ANODE: 1,
    Detector.MCP: 6,
    Electrode.V00: 7,
    Electrode.V01: 8,
    Electrode.V02: 9,
    Electrode.V11: 33,
    Electrode.V12: 34,
    Electrode.V13: 35,
    Electrode.BASELINE: 36,
}


test_configuration = {
    Detector.ANODE: 1,
    Detector.MCP: 6,
    Electrode.V21: 7,
    Electrode.V22: 8,
    Electrode.V23: 9,
    Electrode.V31: 33,
    Electrode.V32: 34,
    Electrode.V33: 35,
    Electrode.BASELINE: 36,
}

nominal_configuration = {
    Detector.ANODE: 2,
    Detector.MCP: 3,
    Electrode.V00: 4,
    Electrode.V01: 5,
    Electrode.V02: 6,
    Electrode.V11: 7,
    Electrode.V12: 8,
    Electrode.V13: 9,
    Electrode.V21: 10,
    Electrode.V22: 11,
    Electrode.V23: 12,
    Electrode.V31: 13,
    Electrode.V32: 14,
    Electrode.V33: 15,
    Electrode.BASELINE: 33,
    Corrector.D00: 34,
    Corrector.D01: 35,
    Corrector.D02: 36,
    Corrector.D10: 37,
    Corrector.D11: 38,
    Corrector.D12: 39,
    Corrector.ST0: 40,
    Corrector.ST1: 41,
    Corrector.ST2: 42,
    Detector.GRID: 44,
}


@dataclass
class PowerSupplySettings:
    hv_ramp: int = 0
    DAC_ramp: int = 0
    n_electrodes: int = 15
    terminal_configuration = nominal_configuration


@dataclass
class LensTable:
    table: dict[Electrode, float]
    name: str = None
    conversion_map: "np.ndarray" = None
    metadata: str = None

    def __str__(self) -> str:
        return f"LensTable : {self.name}"

    def __repr__(self) -> str:
        return f"LensTable : {self.name}"
