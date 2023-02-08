# ========HEADER===========
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.absolute()))
# =======END HEADER========
from pathlib import Path
from daq.ether_daq.common import read_photon_list

result = read_photon_list(Path(r"C:\Users\admin.TOF-PEEM\tmp\output\frame.fits"))
print(result)