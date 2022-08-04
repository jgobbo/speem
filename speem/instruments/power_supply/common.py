from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class PowerSupplySettings:
    hv_ramp: int = 0
    DAC_ramp: int = 0
    n_electrodes: int = 15