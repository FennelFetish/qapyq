from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QRect, QSize, QEvent


class PrecisionSpinBox(QtWidgets.QSpinBox):
    def __init__(self, digits=2):
        super().__init__()
        digits = max(int(digits), 1) - 1
        self._precision = 10 ** digits
        self._format = f".{digits}f"

    def textFromValue(self, val: int) -> str:
        val /= self._precision
        #print(f"textFromValue: {val} -> {val:{self._format}}")
        return f"{val:{self._format}}"
    
    def valueFromText(self, text: str) -> int:
        val = float(text) * self._precision
        #print(f"valueFromText: {text} -> {val}")
        return round(val)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Period:
            text = self.lineEdit().text()
            self.lineEdit().setText(text + ".")
            #self.lineEdit().insert('.')
        else:
            super().keyPressEvent(event)

    # def setRange(self, min, max):
    #     min *= self._precision
    #     max *= self._precision
    #     super().setRange(min, max)



class DynamicLineEdit(QtWidgets.QLineEdit):
    def __init__(self):
        super().__init__()
        self.textChanged.connect(self.updateWidth)
    
    @Slot()
    def updateWidth(self):
        width = self.fontMetrics().boundingRect(self.text()).width() + 8
        width = max(width, self.minimumSizeHint().width())
        self.setFixedWidth(width)


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, spacing=0):
        super().__init__(parent)

        if spacing >= 0:
            self.setSpacing(spacing)

        self.setContentsMargins(5, 5, 5, 5)

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
            if itemRect.right() > maxWidth and i>0:
                left = rect.x() + margins.left()
                top += rowHeight + self.spacing()
                rowHeight = itemRect.height()
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

        self.setWindowTitle("Caption Bubbles Test")
        self.setAttribute(Qt.WA_QuitOnClose)

        layout = FlowLayout(spacing=5)
        for i in range(20):
            btn = QtWidgets.QPushButton("Button-" + str(i))
            btn.setMinimumWidth(random.randint(80,400))
            layout.addWidget(btn)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)

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