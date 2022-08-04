# ========HEADER===========
import sys
from pathlib import Path

HOME_ROOT = Path(__file__).parent.parent.parent.absolute()
# sys.path.append(str(HOME_ROOT / "autodidaqt-common"))
# sys.path.append(str(HOME_ROOT / "autodidaqt"))
sys.path.append(str(HOME_ROOT / "peem-daq/instruments"))
# =======END HEADER========
from dataclasses import dataclass

from autodidaqt import AutodiDAQt, Experiment
from autodidaqt.mock import MockMotionController

from power_supply import PowerSupplyController

@dataclass
class RepeatScan:
    name: str = "Im tired"

    n_repeats: int = 5

    def sequence(self, experiment, power_supply, phony, **kwargs):
        experiment.collate(
            independent=[[phony.stages[0], 'x']],
            dependent=[
                [power_supply.voltages, 'voltages'],
            ]
        )

        for step_i in range(self.n_repeats):
            with experiment.point():
                yield [phony.stages[0].write(step_i)]
                yield [power_supply.voltages.write()]

class PSTest(Experiment):
    scan_methods = [RepeatScan,]


app = AutodiDAQt(__name__,
    managed_instruments={
        'power_supply': PowerSupplyController,
        'phony': MockMotionController,
    })

if __name__ == '__main__':
    app.start()
    