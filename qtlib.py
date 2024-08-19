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

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self._drag_widget = None
        self._drag_widget_idx = -1
        self._drag_target = None

    def _setDragTarget(self, pixmap):
        label = QtWidgets.QLabel()
        label.setPixmap(pixmap)
        #label.setStyleSheet("QLabel{border: 2px solid #D52020; border-radius: 4px;}")
        self.layout().addWidget(label)
        self._drag_target = label

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

        #widget = self.childAt(e.position().toPoint())
        widget = self.widgetUnderCursor() # Only drag direct children
        if not widget:
            return

        drag = QtGui.QDrag(widget)
        drag.setMimeData(QMimeData())

        pixmap = widget.grab()
        #drag.setPixmap(pixmap)
        self._setDragTarget(pixmap)

        widget.hide()
        self._drag_widget = widget
        self._drag_widget_idx = self.layout().indexOf(widget)

        result = drag.exec(Qt.DropAction.MoveAction) # Blocking call
        print("Drag result:", result)
        widget.show() # Show this widget again, if it's dropped outside.
        if self._drag_target:
            self._removeDragTarget()

    def dragEnterEvent(self, e):
        print("Drag enter")
        e.accept()

    def dragLeaveEvent(self, e):
        print("Drag leave")
        self.layout().insertWidget(self._drag_widget_idx, self._drag_target)

        # if self._drag_target:
        #     self._drag_target.hide()
        #     self._drag_target.deleteLater()
        #     self._drag_target = None
        # self.layout().insertWidget(self._drag_widget_idx, self._drag_widget)
        # self._drag_widget.show()
        e.accept()

    def dragMoveEvent(self, e):
        layout = self.layout()
        # Find the correct location of the drop target, so we can move it there.
        index = self._findDropIndex(e)
        if index is not None:
            # Inserting moves the item if its alreaady in the layout.
            layout.insertWidget(index, self._drag_target)
            # Hide the item being dragged.
            e.source().hide()
            # Show the target.
            #self._drag_target.show()
        e.accept()

    def dropEvent(self, e):
        print("Drop")
        layout = self.layout()
        widget = self._drag_widget #e.source()
        # Use drop target location for destination, then remove it.
        index = layout.indexOf(self._drag_target)
        if index is not None:
            layout.insertWidget(index, widget)
            self.orderChanged.emit()
            widget.show()
            layout.activate()

        self._removeDragTarget()
        e.accept()

    def _findDropIndex(self, e):
        posX = e.position().x() + self._drag_widget.width()
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