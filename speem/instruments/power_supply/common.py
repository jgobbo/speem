from dataclasses import dataclass
from enum import Enum, auto

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

__all__ = ["Electrode", "PowerSupplySettings", "LensTable"]


class Electrode(Enum):
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
    BASELINE = auto()
    ANODE = auto()
    MCP = auto()
    MESH = auto()


test_configuration = {
    Electrode.ANODE: 1,
    Electrode.MCP: 6,
    Electrode.V02: 7,
    Electrode.V31: 8,
    Electrode.V32: 9,
    Electrode.ST0: 33,
    Electrode.ST1: 34,
    Electrode.ST2: 35,
    Electrode.ST3: 36,
}


@dataclass
class PowerSupplySettings:
    hv_ramp: int = 0
    DAC_ramp: int = 0
    n_electrodes: int = 15
    electrode_configuration = test_configuration


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
