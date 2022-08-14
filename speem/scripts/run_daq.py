from dataclasses import dataclass
import numpy as np

from autodidaqt import AutodiDAQt, Experiment
from autodidaqt.mock import MockMotionController
from speem.instruments import *


@dataclass
class RepeatScan:
    name: str = "Im tired"

    n_repeats: int = 5
    frame_s: int = 1

    def sequence(
        self,
        experiment: Experiment,
        detector: DetectorController,
        phony: MockMotionController,
        **kwargs,
    ):
        experiment.collate(
            independent=[[phony.stages[0], "x"]],
            dependent=[[detector.frame, "frames"],],
        )

        yield detector.driver.set_frame_time(self.frame_s)
        # yield setattr

        for step_i in range(self.n_repeats):
            with experiment.point():
                yield [phony.stages[0].write(step_i)]
                yield [detector.frame.read()]

        yield detector.driver.set_frame_time(0.5)

    @property
    def metadata(self):
        return dict(name=self.name, n_repeats=self.n_repeats, frame_s=self.frame_s)


class SPEEMExperiment(Experiment):
    scan_methods = [RepeatScan]


app = AutodiDAQt(
    __name__,
    actors={"experiment": SPEEMExperiment,},
    managed_instruments={
        "detector": DetectorController,
        "power_supply": PowerSupplyController,
        # "beam_pointer": BeamPointerController,
        # "power_meter": PowermeterController,
        "phony": MockMotionController,
    },
)

if __name__ == "__main__":
    app.start()
