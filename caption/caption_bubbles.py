from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
import lib.qtlib as qtlib
from ui.flow_layout import FlowLayout, ReorderWidget

# TODO: Nested bubbles for expressions like: (blue (starry:0.8) sky:1.2)

class CaptionBubbles(ReorderWidget):
    remove = Signal(int)
    dropped = Signal(str)

    def __init__(self, context, showWeights=True, showRemove=False, editable=True):
        super().__init__()
        self.dataCallback = lambda widget: widget.text
        self.receivedDrop.connect(self._onDrop)

        from .caption_container import CaptionContext
        self.ctx: CaptionContext = context

        self.text = ""
        self.separator = ','
        self.showWeights = showWeights
        self.showRemove = showRemove
        self.editable = editable

        layout = FlowLayout(spacing=5)
        self.setLayout(layout)
        self.updateBubbles()


    def setText(self, text):
        self.text = text
        self.updateBubbles()

    def getCaptions(self) -> list[str]:
        return [bubble.text for bubble in self.getBubbles()]

    def getBubbles(self):
        layout: QtWidgets.QLayout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if (widget := item.widget()) and isinstance(widget, Bubble): # Why is there other stuff in there? -> It's the ReorderWidget's drag target
                yield widget

    def updateBubbles(self):
        oldBubbles: list[Bubble] = [bubble for bubble in self.getBubbles()]

        colors = self.ctx.groups.getCaptionColors()
        i = -1
        for i, caption in enumerate(self.text.split(self.separator)):
            caption = caption.strip()

            if i < len(oldBubbles):
                bubble = oldBubbles[i]
                bubble.index = i
            else:
                bubble = Bubble(i, self.remove, self.showWeights, self.showRemove, self.editable)
                bubble.setFocusProxy(self)
                self.layout().addWidget(bubble)

            color = colors.get(caption)
            if color is None:
                color = qtlib.COLOR_BUBBLE_HOVER if self.ctx.isHovered(caption) else qtlib.COLOR_BUBBLE_BLACK

            bubble.text = caption
            bubble.setColor(color)
            bubble.forceUpdateWidth()

        for i in range(i+1, len(oldBubbles)):
            oldBubbles[i].deleteLater()


    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.

    @Slot()
    def _onDrop(self, text: str):
        self.dropped.emit(text)



# TODO: Change background color according to weight (blue=low, red=high?)
class Bubble(QtWidgets.QFrame):
    def __init__(self, index, removeSignal, showWeights=True, showRemove=False, editable=True):
        super().__init__()

        self.index = index
        self._text = ""
        self.color = ""
        self.weight = 1.0

        if editable:
            self.textField = qtlib.DynamicLineEdit()
        else:
            self.textField = qtlib.EllipsisLabel(80)
            self.textField.setContentsMargins(0, 0, 4, 0)
        qtlib.setMonospace(self.textField)

        self.setContentsMargins(4, 1, 4, 1)
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
            btnRemove = qtlib.BubbleRemoveButton()
            btnRemove.setFocusProxy(self)
            btnRemove.clicked.connect(lambda: removeSignal.emit(self.index))
            layout.addWidget(btnRemove)

        self.setLayout(layout)

        self.setColor(qtlib.COLOR_BUBBLE_BLACK)
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)


    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text
        self.textField.setText(text)


    def setColor(self, color: str):
        if color == self.color:
            return
        self.color = color

        self.setStyleSheet(qtlib.bubbleClass("Bubble", color))
        self.textField.setStyleSheet(qtlib.bubbleStyleAux(color))

        if self.spinWeight:
            #self.spinWeight.setStyleSheet(".QDoubleSpinBox{background-color: " + color + "; border: 0; padding-right: 25px}")
            self.spinWeight.lineEdit().setStyleSheet("color: #fff; background-color: " + color)

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