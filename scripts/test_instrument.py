from speem.instruments import *
from daquiri import Daquiri, Experiment

app = Daquiri(
    __name__,
    # actors={"experiment": Experiment,},
    managed_instruments={
        # "motors": MotionController,
        "detector": DetectorController,
        # "power supply": PowerSupplyController,
        # "beam_pointer": BeamPointerController,
    },
)


if __name__ == "__main__":
    app.start()
