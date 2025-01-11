from typing import Iterable
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal
from lib.qtlib import FlowLayout, EditablePushButton, setMonospace


class StringFlowBubble(QtWidgets.QFrame):
    removeClicked = Signal(object)

    def __init__(self, text: str):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        
        self.button = EditablePushButton(text, self._buttonStyleFunc)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(1, 0, 2, 0)
        layout.setSpacing(1)
        layout.addWidget(self.button)

        btnRemove = QtWidgets.QPushButton("⨯")
        btnRemove.setStyleSheet(".QPushButton{color: #D54040; background-color: #161616; border: 1px solid #401616; border-radius: 4px}")
        btnRemove.setFixedWidth(18)
        btnRemove.setFixedHeight(18)
        btnRemove.clicked.connect(lambda: self.removeClicked.emit(self))
        layout.addWidget(btnRemove)

        self.setLayout(layout)

        self.setColor("#161616")
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)

    @staticmethod
    def _buttonStyleFunc(button: EditablePushButton):
        setMonospace(button, 0.9)

    @property
    def text(self):
        return self.button.text

    @text.setter
    def text(self, text: str):
        self.button.text = text

    def setColor(self, color):
        self.setStyleSheet(".StringFlowBubble{background-color: " + color + "; border: 1px solid #161616; border-radius: 8px}")
        self.button.setStyleSheet("color: #fff; background-color: " + color + "; border: 0px")



class SortedStringFlowWidget(QtWidgets.QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)

        self.flowLayout = FlowLayout(spacing=1)
        self.flowLayout.setContentsMargins(4, 4, 4, 4)
        self.setLayout(self.flowLayout)

    
    def addItem(self, label: str) -> bool:
        if self.hasItem(label):
            return False

        self.flowLayout.addWidget(self._createBubble(label))
        self.flowLayout.items.sort(key=lambda item: item.widget().text)
        self.flowLayout.invalidate()
        self.changed.emit()
        return True

    def hasItem(self, label: str) -> bool:
        for i in range(self.flowLayout.count()):
            if label == self.flowLayout.itemAt(i).widget().text:
                return True
        return False

    def _createBubble(self, label: str):
        bubble = StringFlowBubble(label)
        bubble.removeClicked.connect(self._onRemoveClicked)
        return bubble

    def setItems(self, labels: Iterable[str]) -> None:
        self.flowLayout.clear()

        existing: set[str] = set()
        for label in sorted(labels):
            if label not in existing:
                existing.add(label)
                self.flowLayout.addWidget(self._createBubble(label))

        self.changed.emit()

    def getItems(self) -> list[str]:
        values = list()
        for i in range(self.flowLayout.count()):
            widget: StringFlowBubble = self.flowLayout.itemAt(i).widget()
            values.append(widget.text)
        return values

    def _onRemoveClicked(self, bubble: StringFlowBubble):
        index = self.flowLayout.indexOf(bubble)
        if index < 0:
            return

        item = self.flowLayout.takeAt(index)
        item.widget().deleteLater()
        self.flowLayout.invalidate()
        self.changed.emit()


    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()

    def dragLeaveEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event: QtGui.QDropEvent):
        if not event.mimeData().hasText():
            return
        
        text = event.mimeData().text()
        self.addItem(text)

        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
