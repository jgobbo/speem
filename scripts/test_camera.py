import sys
from PyQt5.QtWidgets import (
    QWidget,
    QApplication,
    QLabel,
    QVBoxLayout,
    QSlider,
    QPushButton,
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread
import numpy as np
from pylucam import LucamCamera
import time

from warnings import simplefilter

simplefilter("always")


class VideoThread(QThread):
    """Thread for capturing video frames"""

    update: str | None = None
    change_pixmap_signal = pyqtSignal(np.ndarray)

    def __init__(self, number=1):
        super().__init__()
        self._run_flag = True
        self.camera = LucamCamera(number)
        self.camera.enable_fast_frames()

    @pyqtSlot(int)
    def update_gain(self, value: int):
        self.gain = value
        self.update = "gain"

    def _update_gain(self):
        self.camera.snapshot.gain = self.gain
        self.camera.reset_fast_frames()
        self.update = None

    @pyqtSlot(bool)
    def white_balance(self, _: bool) -> None:
        self.update = "white_balance"

    def _white_balance(self):
        self.camera.white_balance()
        self.update = None

    def run(self):
        while self._run_flag:
            time.sleep(1 / 30)
            if self.update == "gain":
                self._update_gain()
            elif self.update == "white_balance":
                self._white_balance()
            else:
                assert self.update is None
                self.change_pixmap_signal.emit(self.camera.take_fast_frame_rgb())

    def stop(self):
        """Sets run flag to False and waits for thread to finish"""
        self._run_flag = False
        self.wait()
        self.camera.disable_fast_frames()
        self.camera.camera_close()


class MainWindow(QWidget):
    def __init__(self, number=1):
        super().__init__()
        self.setWindowTitle("Live Camera Feed")
        self.disply_width = 1096
        self.display_height = 1944

        # Create layout and label
        self.image_label = QLabel(self)
        self.image_label.resize(self.disply_width, self.display_height)

        self.thread: VideoThread = VideoThread(number)
        self.thread.change_pixmap_signal.connect(self.update_image)

        # Set up layout

        vbox = QVBoxLayout()
        vbox.addWidget(self.image_label)

        gain_slider = QSlider(self, orientation=Qt.Orientation.Horizontal)
        gain_slider.setRange(1, 100)
        gain_slider.valueChanged.connect(self.thread.update_gain)
        vbox.addWidget(gain_slider)

        white_balance_button = QPushButton("white_balance", self)
        white_balance_button.clicked.connect(self.thread.white_balance)
        vbox.addWidget(white_balance_button)

        self.setLayout(vbox)

        # Initialize and start the video capture thread
        self.thread.start()

    @pyqtSlot(np.ndarray)
    def update_image(self, image):
        """Updates the image_label with a new opencv image"""
        qt_img = self.convert_bayer_qpixmap(image)
        self.image_label.setPixmap(qt_img)

    def convert_bayer_qpixmap(self, image: np.ndarray) -> QPixmap:
        """Convert from an opencv image to QPixmap"""
        h, w, n_colors = image.shape
        bytes_per_line = w * n_colors
        convert_to_Qt_format = QImage(
            image.data.tobytes(), w, h, bytes_per_line, QImage.Format.Format_RGB888
        )
        p = convert_to_Qt_format.scaled(
            self.disply_width, self.display_height, Qt.KeepAspectRatio
        )
        return QPixmap.fromImage(p)

    def closeEvent(self, event):
        """Proper cleanup when window is closed"""
        self.thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(2)
    window.show()
    sys.exit(app.exec_())
