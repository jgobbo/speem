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


# @dataclass
# class OptimizeLaserPosition:
#     name: str = "Optimize Beam Position"

#     # must be float/int/str for dataclass binding (I think)
#     x_start: float = 0
#     x_stop: float = 150
#     y_start: float = 0
#     y_stop: float = 150
#     n_points: int = 10
#     frame_s: int = 1
#     z_value: float = 0

#     def sequence(
#         self,
#         experiment: Experiment,
#         detector: DetectorController,
#         beam_pointer: BeamPointerController,
#         **kwargs,
#     ):
#         experiment.collate(
#             independent=[
#                 [beam_pointer.x, "laser_x"],
#                 [beam_pointer.y, "laser_y"],
#                 [beam_pointer.z, "laser_z"],
#             ],
#             dependent=[[detector.frame, "frames"]],
#         )

#         experiment.plot(
#             independent=["beam_pointer.x", "beam_pointer.y",],
#             dependent="detector.frame",
#             name="Photoemission Intensity",
#             dep_processor=len,
#             cmap="magma",
#         )

#         yield beam_pointer.driver.set_z(self.z_value)
#         yield detector.driver.set_frame_time(self.frame_s)

#         for x_voltage in np.linspace(self.x_start, self.x_stop, self.n_points):
#             for y_voltage in np.linspace(self.y_start, self.y_stop, self.n_points):
#                 with experiment.point():
#                     yield [
#                         beam_pointer.x.write(x_voltage),
#                         beam_pointer.y.write(y_voltage),
#                     ]
#                     yield [detector.frame.read()]

#         yield detector.driver.set_frame_time(0.5)


class SPEEMExperiment(Experiment):
    scan_methods = [RepeatScan]


app = AutodiDAQt(
    __name__,
    actors={"experiment": SPEEMExperiment,},
    managed_instruments={
        "detector": DetectorController,
        "beam_pointer": BeamPointerController,
        "phony": MockMotionController,
    },
)

if __name__ == "__main__":
    app.start()
