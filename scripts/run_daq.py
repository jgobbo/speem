from dataclasses import dataclass
import numpy as np
import json

from autodidaqt import AutodiDAQt, Experiment
from autodidaqt.mock import MockMotionController

from speem.instruments import *
from speem.instruments.power_supply.common import Electrode

from datetime import date


@dataclass
class RepeatScan:
    name: str = "gimme a name"

    n_repeats: int = 1
    frame_s: int = 1

    def sequence(
        self,
        experiment: Experiment,
        detector: DetectorController,
        power_supply: PowerSupplyController,
        phony: MockMotionController,
        **kwargs,
    ):
        experiment.collate(
            independent=[[phony.stages[0], "x"]],
            dependent=[
                [detector.frame, "frames"],
            ],
        )

        yield [power_supply.terminal_voltages.read()]
        yield [detector.timing_delay.read()]

        original_frame_time = (yield [detector.frame_time.read()])[0]
        yield [detector.frame_time.write(self.frame_s)]

        detector.driver.empty_message_queue()
        for step_i in range(self.n_repeats):
            with experiment.point():
                yield [phony.stages[0].write(step_i)]
                yield [detector.frame.read()]

        yield [detector.frame_time.write(original_frame_time)]

    @property
    def metadata(self):
        return dict(name=self.name, n_repeats=self.n_repeats, frame_s=self.frame_s)


@dataclass
class ScanElectrode:
    name: str = "electrode scan"

    electrode: Electrode = Electrode.V13
    start: float = 0.0
    step: float = 0.5
    stop: float = 20

    frame_time: float = 5.0

    @property
    def metadata(self):
        return dict(
            name=self.name,
            electrode=self.electrode,
            start=self.start,
            step=self.step,
            stop=self.stop,
            frame_time=self.frame_time,
        )

    def sequence(
        self,
        experiment: Experiment,
        detector: DetectorController,
        power_supply: PowerSupplyController,
        phony: MockMotionController,
        **kwargs,
    ):
        experiment.collate(
            independent=[[phony.stages[0], self.electrode.name]],
            dependent=[[detector.frame, "frames"]],
        )

        original_frame_time = detector.driver.frame_time
        yield [detector.frame_time.write(self.frame_time)]

        voltage = self.start
        while abs(voltage) < abs(self.stop):
            with experiment.point():
                yield power_supply.driver.apply_voltage(self.electrode, voltage)
                yield [phony.stages[0].write(voltage)]
                yield [detector.frame.read()]

            voltage += self.step

        yield power_supply.driver.apply_voltage(self.electrode, self.stop)
        yield [phony.stages[0].write(self.stop)]
        yield [detector.frame.read()]

        yield power_supply.driver.apply_voltage(self.electrode, 0)
        yield [detector.frame_time.write(original_frame_time)]


# @dataclass
# class DelayScan:
#     delay_start_ps:float = 0
#     delay_stop_ps:float = 1000
#     delay_step_ps:float = 100
#     n_delay_steps:int = 0
#     stop_inclusive:bool=False

#     def sequence(
#         self,
#         experiment: Experiment,
#         detector: DetectorController,
#         laser: LaserController,
#     ):
#         experiment.collate(
#             independent=[
#                 (laser.delay, "delay"),
#             ],
#             dependent=[(detector.frame, "frame")],
#         )

#         delay_step = self.delay_step_ps if self.n_delay_steps < 1 else (self.delay_stop_ps - self.delay_start_ps) / self.n_delay_steps

#         for delay_ps in range(self.delay_start_ps, self.delay_stop_ps, delay_step):
#             yield [laser.delay.write(delay_ps)]
#             yield [detector.frame.read()]

#         if self.stop_inclusive:
#             yield [laser.delay.write(self.delay_stop_ps)]
#             yield [detector.frame.read()]


@dataclass
class CalibrateToF:
    filename: str = date.today().strftime("%Y_%m_%d")
    starting_delay: float = 0
    ending_delay: float = 0

    def sequence(self, experiment: Experiment, detector: DetectorController):
        from scipy.stats import mode

        timing_delays = []
        peak_pixels = []
        for delay in np.linspace(self.starting_delay, self.ending_delay, 100):
            yield [detector.timing_delay.write(delay)]
            frame = yield [detector.raw_frame.read()]

            timing_delays.append(delay)
            peak_pixels.append(mode(frame[:, 2]).mode[0])

        slope, intercept = np.polyfit(timing_delays, peak_pixels, 1)
        data = {"slope": slope, "offset": intercept}
        with open(f"{self.filename}.json", "w") as f:
            json.dump(data, f, indent=1)


class SPEEMExperiment(Experiment):
    scan_methods = [RepeatScan, ScanElectrode]


app = AutodiDAQt(
    __name__,
    actors={
        "experiment": SPEEMExperiment,
    },
    managed_instruments={
        "detector": DetectorController,
        "power_supply": PowerSupplyController,
        # "beam_pointer": BeamPointerController,
        # "power_meter": PowermeterController,
        "phony": MockMotionController,
        "motion": MotionController,
    },
)

if __name__ == "__main__":
    # from cProfile import Profile
    # import pstats

    # with Profile() as pr:
    #     app.start()
    # stats = pstats.Stats(pr)
    # stats.sort_stats(pstats.SortKey.TIME)
    # stats.dump_stats(filename="random.prof")

    app.start()

    # try:
    #     app.start()
    # except:
    #     import pdb, traceback, sys

    #     extype, value, tb = sys.exc_info()
    #     traceback.print_exc()
    #     pdb.post_mortem(tb)
