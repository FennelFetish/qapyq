from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QRect, QSize


class DynamicLineEdit(QtWidgets.QLineEdit):
    def __init__(self):
        super().__init__()
        self.textChanged.connect(self.updateWidth)
        self.extraWidth = 8
    
    @Slot()
    def updateWidth(self):
        width = self.fontMetrics().boundingRect(self.text()).width() + self.extraWidth
        width = max(width, self.minimumSizeHint().width())
        self.setFixedWidth(width)


def setTextEditHeight(textEdit, numRows):
    lineHeight = textEdit.fontMetrics().lineSpacing()
    docMargin = textEdit.document().documentMargin()
    frameWidth = textEdit.frameWidth()
    margins = textEdit.contentsMargins()

    height = lineHeight*numRows + 2*(docMargin + frameWidth) + margins.top() + margins.bottom()
    textEdit.setFixedHeight(height)


class EditablePushButton(QtWidgets.QWidget):
    clicked     = Signal(str)
    textChanged = Signal(str)
    textEmpty   = Signal(object)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.extraWidth = 12

        self.button = QtWidgets.QPushButton(text)
        self.button.clicked.connect(self.click)
        self.button.mouseReleaseEvent = self._button_mouseReleaseEvent
        self.edit = None

        self._updateWidth()
        layout = QtWidgets.QVBoxLayout()
        layout.setSizeConstraint(QtWidgets.QLayout.SetFixedSize)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.button)
        self.setLayout(layout)

    @property
    def text(self) -> str:
        return self.activeWidget().text()

    def activeWidget(self):
        return self.edit if self.edit else self.button

    def sizeHint(self):
        return self.activeWidget().sizeHint()

    # Handles clicks by other means than mouse left button (e.g. keyboard)
    @Slot()
    def click(self):
        self.clicked.emit(self.button.text())
        self.button.setDown(False)

    def _button_mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.click()
        elif event.button() == Qt.RightButton:
            self.setEditMode()
    
    def setEditMode(self):
        self.edit = QtWidgets.QLineEdit()
        self.edit.setText(self.button.text())
        self.edit.setFixedWidth(self.button.width())
        self.edit.textChanged.connect(self._updateWidth)
        self.edit.editingFinished.connect(self._editFinished)

        self.layout().replaceWidget(self.button, self.edit)
        self.button.hide()
        self.edit.setFocus()

    @Slot()
    def _editFinished(self):
        text = self.edit.text()
        self.button.setText(text)
        self.button.setFixedWidth(self.edit.width())
        self.button.show()
        self.layout().replaceWidget(self.edit, self.button)
        self.edit.deleteLater()
        self.edit = None

        if text:
            self.textChanged.emit(text)
        else:
            self.textEmpty.emit(self)

    @Slot()
    def _updateWidth(self):
        widget = self.activeWidget()
        text = widget.text()
        width = widget.fontMetrics().boundingRect(text).width() + self.extraWidth
        widget.setFixedWidth(width)



class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, spacing=0):
        super().__init__(parent)

        if spacing >= 0:
            self.setSpacing(spacing)

        self.setContentsMargins(0, 0, 0, 0)

        self.items = []
        self._size = QSize(0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index):
        if index < 0 or index >= len(self.items):
            return None
        return self.items[index]

    def takeAt(self, index):
        if index < 0 or index >= len(self.items):
            return None
        return self.items.pop(index)

    def expandingDirections(self):
        return Qt.Orientation.Vertical

    def minimumSize(self):
        maxWidth = 0
        for item in self.items:
            maxWidth = max(maxWidth, item.sizeHint().width())
        
        margins = self.contentsMargins()
        maxWidth += margins.left() + margins.right()
        minHeight = margins.top() + margins.bottom()
        return QSize(maxWidth, minHeight)

    def sizeHint(self):
        return self._size

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        margins = self.contentsMargins()
        maxWidth = rect.width() - margins.right()

        left = rect.x() + margins.left()
        top  = rect.y() + margins.top()
        rowHeight = 0
        totalRect = QRect()

        for i, item in enumerate(self.items):
            itemRect = QRect(left, top, item.sizeHint().width(), item.sizeHint().height())
            rowHeight = max(rowHeight, itemRect.height())
            if i==0:
                totalRect = itemRect
            elif itemRect.right() > maxWidth:
                left = rect.x() + margins.left()
                top += rowHeight + self.spacing()
                rowHeight = 0
                itemRect.moveLeft(left)
                itemRect.moveTop(top)

            item.setGeometry(itemRect)
            left += itemRect.width() + self.spacing()
            totalRect = totalRect.united(itemRect)

        self._size.setWidth(totalRect.width())
        self._size.setHeight(totalRect.height() + margins.bottom())



class TestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        import random

        self.setWindowTitle("Test")
        self.setAttribute(Qt.WA_QuitOnClose)

        layout = QtWidgets.QGridLayout()
        #layout = FlowLayout(spacing=1)
        for x in range(3):
            for y in range(3):
                btn = EditablePushButton("Btn " + str(x) + "/" + str(y))
                btn.clicked.connect(self.onClick)
                btn.textChanged.connect(self.onTextChanged)
                layout.addWidget(btn, x, y)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)

        self.setCentralWidget(widget)
    
    @Slot()
    def onClick(self, text):
        print("click:", text)
    
    @Slot()
    def onTextChanged(self, text):
        print("text changed:", text)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication([])

    screenSize = app.primaryScreen().size()

    win = TestWindow()
    win.resize(screenSize.width()//2, screenSize.height()//2)
    win.move(screenSize.width()//4, 300)
    win.show()

    sys.exit(app.exec())