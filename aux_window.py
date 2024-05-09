from PySide6 import QtWidgets
from PySide6.QtCore import Signal


class AuxiliaryWindow(QtWidgets.QMainWindow):
    closed = Signal()

    def __init__(self, title):
        super().__init__()
        self.setWindowTitle(title)
    
    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()
