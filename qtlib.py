from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QRect, QSize, QMimeData


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

def setMonospace(textWidget, fontSizeFactor=1.0, bold=False):
    font = textWidget.font()
    font.setStyleHint(QtGui.QFont.Monospace)
    font.setFamily("monospace")
    font.setBold(bold)
    if fontSizeFactor != 1.0:
        fontSize = font.pointSizeF() * fontSizeFactor
        font.setPointSizeF(fontSize)
    textWidget.setFont(font)

def setShowWhitespace(textEdit):
    doc = textEdit.document()
    opt = doc.defaultTextOption()
    opt.setFlags(QtGui.QTextOption.ShowTabsAndSpaces)
    doc.setDefaultTextOption(opt)


class EditablePushButton(QtWidgets.QWidget):
    clicked     = Signal(str)
    textChanged = Signal(str)
    textEmpty   = Signal(object)

    def __init__(self, text, stylerFunc=None, parent=None):
        super().__init__(parent)
        self.stylerFunc = stylerFunc
        self.extraWidth = 12

        self.button = QtWidgets.QPushButton(text)
        self.button.clicked.connect(self.click)
        self.button.mouseReleaseEvent = self._button_mouseReleaseEvent
        self.edit = None

        if stylerFunc:
            stylerFunc(self.button)

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

        if self.stylerFunc:
            self.stylerFunc(self.edit)

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

    def insertWidget(self, index, widget):
        existing_index = self.indexOf(widget)
        if existing_index >= 0:
            item = self.items.pop(existing_index)
        else:
            item = QtWidgets.QWidgetItem(widget)

        index = min(index, len(self.items))
        self.items.insert(index, item)
        self.invalidate()

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
            # if not item.widget().isVisible():
            #     continue
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



class ReorderWidget(QtWidgets.QWidget):
    orderChanged = Signal()

    def __init__(self, giveDrop=False):
        super().__init__()
        self.setAcceptDrops(True)
        self._dragWidgetIndex = -1
        self._drag_target = None

        self.dataCallback = None
        self.dropCallback = None # Callback returns true = Remove from source widget (takeDrop)
        self.updateCallback = None
        self.giveDrop = giveDrop

    def _setDragTarget(self, pixmap):
        pixmap = self._adjustBrightness(pixmap, 2, 1.9, 1.6)
        label = QtWidgets.QLabel()
        label.setPixmap(pixmap)
        self.layout().addWidget(label)
        self._drag_target = label

    def _adjustBrightness(self, pixmap, r, g, b):
        image = pixmap.toImage()
        for y in range(image.height()):
            for x in range(image.width()):
                color = QtGui.QColor(image.pixel(x, y))
                color.setRed(min(255, int(color.red() * r)))
                color.setGreen(min(255, int(color.green() * g)))
                color.setBlue(min(255, int(color.blue() * b)))
                image.setPixel(x, y, color.rgb())
        return QtGui.QPixmap.fromImage(image)

    def _removeDragTarget(self):
        self._drag_target.hide()
        self._drag_target.deleteLater()
        self._drag_target = None

    def widgetUnderCursor(self):
        layout = self.layout()
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if widget and widget.underMouse():
                return widget
        return None

    def mouseMoveEvent(self, e):
        if e.buttons() != Qt.MouseButton.LeftButton:
            return
        
        widget = self.widgetUnderCursor() # Only drag direct children
        if not widget:
            return

        pixmap = widget.grab()
        self._setDragTarget(pixmap)

        data = QMimeData()
        if self.dataCallback:
            data.setText( self.dataCallback(widget) )

        drag = QtGui.QDrag(widget)
        drag.setPixmap(pixmap)
        drag.setMimeData(data)

        self._dragWidgetIndex = self.layout().indexOf(widget)
        self.layout().insertWidget(self._dragWidgetIndex, self._drag_target)
        widget.hide()

        actions = Qt.DropAction.CopyAction
        if self.giveDrop:
            actions |= Qt.DropAction.MoveAction
        result = drag.exec(actions) # Blocking call

        print(f"Drag result: {result}")
        if result == Qt.MoveAction:
            self.layout().removeWidget(widget)
            widget.deleteLater()
        else:
            widget.show() # Show this widget again, if it's dropped outside.

        self._removeDragTarget()

        if self.updateCallback:
            self.updateCallback()

    def dragEnterEvent(self, e):
        print("Drag enter")
        if e.mimeData().hasText:
            e.accept()

    def dragLeaveEvent(self, e):
        print("Drag leave")
        if self._drag_target:
            self.layout().insertWidget(self._dragWidgetIndex, self._drag_target)
        e.accept()

    def dragMoveEvent(self, e):
        if not self._drag_target:
            e.accept()
            return

        layout = self.layout()
        index = self._findDropIndex(e)
        if index is not None:
            layout.insertWidget(index, self._drag_target)
        e.accept()

    def dropEvent(self, e):
        print("Drop")
        # Dropped into different widget
        if not self._drag_target:
            if self.dropCallback:
                takeDrop = self.dropCallback(e.mimeData().text())
                action = Qt.DropAction.MoveAction if takeDrop else Qt.DropAction.CopyAction
                e.setDropAction(action)
            e.accept()
            return

        # Dropped into same widget
        print("Drop same")
        layout = self.layout()
        widget = e.source()
        index = layout.indexOf(self._drag_target)
        if index is not None:
            layout.insertWidget(index, widget)
            widget.show()
            layout.activate()
            self.orderChanged.emit()
        
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()

    def _findDropIndex(self, e):
        posX = e.position().x() + e.source().width()
        posY = e.position().y()
        layout = self.layout()
        spacing = layout.spacing() / 2

        i = 0
        for n in range(layout.count()):
            ele = layout.itemAt(n).widget()
            if posY < ele.y() - spacing:
                break
            if posX > ele.x() + ele.width():
                i = n
        return i



class TestWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        import random

        self.setWindowTitle("Test")
        self.setAttribute(Qt.WA_QuitOnClose)

        #layout = QtWidgets.QGridLayout()
        layout = FlowLayout(spacing=10)
        #layout = QtWidgets.QHBoxLayout()
        for x in range(3):
            for y in range(3):
                btn = QtWidgets.QLabel(f"{x} / {y}")
                layout.addWidget(btn)#, x, y)

        widget = ReorderWidget()
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