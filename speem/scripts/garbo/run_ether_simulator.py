# ========HEADER===========
import sys
from pathlib import Path
ROOT_PATH = Path(__file__).parent.parent.absolute()
sys.path.append(str(ROOT_PATH))
# =======END HEADER========

import pprint
from daq.ether_daq import EtherDAQSimulator

if __name__ == "__main__":
    simulator = EtherDAQSimulator()
    simulator.config.command_path = ROOT_PATH / "scratch" / "commands"
    simulator.start()