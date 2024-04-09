from imgview import ImgView
import sys
from PySide6 import QtWidgets


class MyWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Compare")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.buildScene()

    def buildScene(self):
        self.view = ImgView()
        self.layout.addWidget(self.view)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    widget = MyWidget()
    widget.resize(800, 600)
    widget.move(100, 500)
    widget.show()

    sys.exit(app.exec())