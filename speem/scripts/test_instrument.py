from speem.instruments import *
from autodidaqt import AutodiDAQt, Experiment

app = AutodiDAQt(
    __name__,
    # actors={"experiment": Experiment,},
    managed_instruments={
        "detector": DetectorController
        # "power supply": PowerSupplyController,
        # "beam_pointer": BeamPointerController,
    },
)


if __name__ == "__main__":
    app.start()
    # try:
    #     app.start()
    # except:
    #     import pdb, traceback, sys

    #     extype, value, tb = sys.exc_info()
    #     traceback.print_exc()
    #     pdb.post_mortem(tb)
