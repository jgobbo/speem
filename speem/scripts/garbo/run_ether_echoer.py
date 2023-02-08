# ========HEADER===========
import sys
from pathlib import Path
ROOT_PATH = Path(__file__).parent.parent.absolute()
sys.path.append(str(ROOT_PATH))
# =======END HEADER========

import pprint
from daq.ether_daq import EtherDAQEchoer, EtherDAQSettings

if __name__ == "__main__":
    settings = EtherDAQSettings(n_iterations=1, integration_time=5)
    dest_format_string = str((ROOT_PATH / "scratch" / "ether_data" / "data-{}.fits").absolute())

    echoer = EtherDAQEchoer(
        dest_format_string=dest_format_string,
        command_path=ROOT_PATH / "scratch" / "commands" / "command.txt",
        settings=settings,
    )

    echoer.start()
    