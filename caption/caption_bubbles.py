
import random
import sys
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import QRect, QSize, Qt, Slot, Signal
import qtlib


class CaptionBubbles(qtlib.ReorderWidget):
    remove = Signal(int)

    def __init__(self, showWeights=True, showRemove=False):
        super().__init__()
        self.text = ""
        self.separator = ','
        self.showWeights = showWeights
        self.showRemove = showRemove

        layout = qtlib.FlowLayout(spacing=5)
        self.setLayout(layout)

        self.updateBubbles()

    def setText(self, text):
        self.text = text
        self.updateBubbles()

    def getCaptions(self) -> list[str]:
        captions: list[str] = []
        layout = self.layout()
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget and isinstance(widget, Bubble): # TODO: Why is there other stuff in there?
                captions.append(widget.text)
        return captions

    def updateBubbles(self):
        self.clearLayout()

        for i, tag in enumerate(self.text.split(self.separator)):
            tag = tag.strip()
            bubble = Bubble(i, self.remove, self.showWeights, self.showRemove, editable=False)
            bubble.text = tag
            self.layout().addWidget(bubble)
            bubble.forceUpdateWidth()

    def clearLayout(self):
        layout = self.layout()
        for i in reversed(range(layout.count())):
            item = layout.takeAt(i)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            else:
                item.spacerItem().deleteLater()
    
    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.


# TODO: Change background color according to weight (blue=low, red=high?)
class Bubble(QtWidgets.QFrame):
    def __init__(self, index, removeSignal, showWeights=True, showRemove=False, editable=True):
        super().__init__()

        self._text = ""
        self.weight = 1.0
        self.setContentsMargins(4, 1, 4, 1)

        # self.setStyleSheet(f"background-color: {self.color.name()}")
        self.setStyleSheet(".Bubble{border: 1px solid #181818; background-color: #161616; border-radius: 8px}")

        if editable:
            self.textField = qtlib.DynamicLineEdit()
        else:
            self.textField = QtWidgets.QLabel()
            self.textField.setContentsMargins(0, 0, 4, 0)
        
        qtlib.setMonospace(self.textField)
        self.textField.setStyleSheet(".DynamicLineEdit{background-color: #161616; border: 0px}")

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.textField)

        if showWeights:
            self.spinWeight = QtWidgets.QDoubleSpinBox()
            self.spinWeight.setRange(-10.0, 10.0)
            self.spinWeight.setValue(1.0)
            self.spinWeight.setSingleStep(0.05)
            self.spinWeight.setFixedWidth(55)
            layout.addWidget(self.spinWeight)
        else:
            self.spinWeight = None

        if showRemove:
            btnRemove = QtWidgets.QPushButton("⨯")
            btnRemove.setStyleSheet(".QPushButton{color: #D54040; background-color: #161616; border: 1px solid #401616; border-radius: 4px}")
            btnRemove.setFixedWidth(18)
            btnRemove.setFixedHeight(18)
            btnRemove.clicked.connect(lambda: removeSignal.emit(index))
            layout.addWidget(btnRemove)

        self.setLayout(layout)

        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)

    @property
    def text(self):
        return self._text
    
    @text.setter
    def text(self, text):
        self._text = text
        self.textField.setText(text)

    def forceUpdateWidth(self):
        if isinstance(self.textField, qtlib.DynamicLineEdit):
            self.textField.updateWidth()

    def wheelEvent(self, event):
        if self.spinWeight:
            self.spinWeight.wheelEvent(event)
            self.spinWeight.lineEdit().setCursorPosition(0) # Clear text selection



class TestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        import random

        self.setWindowTitle("Caption Bubbles Test")
        self.setAttribute(Qt.WA_QuitOnClose)

        widget = CaptionBubbles()
        self.setCentralWidget(widget)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication([])

    screenSize = app.primaryScreen().size()

    win = TestWindow()
    win.resize(screenSize.width()//2, screenSize.height()//2)
    win.move(screenSize.width()//4, 300)
    win.show()

    sys.exit(app.exec())