from autodidaqt.ui.pg_extras import ArrayImageView
import pyqtgraph as pg
from PyQt5.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)

A = ArrayImageView()

print(dir(A.plot_item.axes["left"]["item"]))
