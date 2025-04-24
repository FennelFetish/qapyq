from typing import Iterable, Callable
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, QSize, QRect, QMimeData, QTimer
import numpy as np
import lib.qtlib as qtlib


class FlowLayout(QtWidgets.QLayout):
    def __init__(self, parent=None, spacing=0):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)

        if spacing >= 0:
            self.setSpacing(spacing)

        self.items: list[QtWidgets.QLayoutItem] = []
        self._size = QSize(0, 0)

    def addItem(self, item: QtWidgets.QLayoutItem):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, index: int):
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def takeAt(self, index: int):
        return self.items.pop(index)

    def insertWidget(self, index: int, widget: QtWidgets.QWidget):
        existing_index = self.indexOf(widget)
        if existing_index >= 0:
            item = self.items.pop(existing_index)
        else:
            item = QtWidgets.QWidgetItem(widget)

        index = min(index, len(self.items))
        self.items.insert(index, item)
        self.invalidate()

    def clear(self):
        for i in reversed(range(self.count())):
            item = self.takeAt(i)
            if not item:
                continue

            widget = item.widget()
            if widget := item.widget():
                widget.deleteLater()
            elif layout := item.layout():
                layout.deleteLater()

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

        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        rowHeight = 0
        totalRect = QRect()

        for i, item in enumerate(self.items):
            if (widget := item.widget()) and widget.isHidden():
                continue

            itemRect = QRect(x, y, item.sizeHint().width(), item.sizeHint().height())
            rowHeight = max(rowHeight, itemRect.height())

            if i == 0:
                totalRect = itemRect
            elif itemRect.right() > maxWidth:
                x = rect.x() + margins.left()
                y += rowHeight + self.spacing()
                rowHeight = 0
                itemRect.moveLeft(x)
                itemRect.moveTop(y)

            item.setGeometry(itemRect)
            x += itemRect.width() + self.spacing()
            totalRect = totalRect.united(itemRect)

        self._size.setWidth(totalRect.width())
        self._size.setHeight(totalRect.height() + margins.bottom())



# Layout must provide insertWidget() method.
# All places that use dropEvent() must postpone the action using QTimer.singleShot
class ReorderWidget(QtWidgets.QWidget):
    COLOR_FACTORS = [1.6, 1.9, 2.0, 1.0] # BGRA

    orderChanged = Signal()
    receivedDrop = Signal(str)

    def __init__(self, giveDrop=False, takeDrop=False):
        super().__init__()
        self.setAcceptDrops(True)
        self._startDragPos = None
        self._dragWidgetIndex = -1
        self._dragTarget = None

        self.dataCallback: Callable[[QtWidgets.QWidget], str] | None = None # Returns the dropped text for a child widget

        self.giveDrop = giveDrop # Remove from self widget if another widget is drop target
        self.takeDrop = takeDrop # Remove from source widget if self is drop target

        self.dragStartMinDistance: int = 0
        self.showCursorPicture = True


    def _createDragTarget(self, pixmap: QtGui.QPixmap, index: int):
        pixmap = self._adjustColor(pixmap)
        self._dragTarget = QtWidgets.QLabel()
        self._dragTarget.setPixmap(pixmap)
        self.layout().addWidget(self._dragTarget)
        self.layout().insertWidget(index, self._dragTarget)

    def _adjustColor(self, pixmap: QtGui.QPixmap):
        image = pixmap.toImage()
        pixelRatio = image.devicePixelRatioF()

        mat = qtlib.qimageToNumpy(image)
        matF = mat.astype(np.float32)
        matF *= self.COLOR_FACTORS
        matF.clip(0.0, 255.0, mat, casting="unsafe")

        # Add border
        # col = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Highlight)
        # borderColor = [float(col.blue()), float(col.green()), float(col.red()), 255.0]
        # h, w = mat.shape[:2]
        # mat[0, :, ...]   = borderColor # Top
        # mat[h-1, :, ...] = borderColor # Bottom
        # mat[:, 0, ...]   = borderColor # Left
        # mat[:, w-1, ...] = borderColor # Right

        image = qtlib.numpyToQImage(mat)
        image.setDevicePixelRatio(pixelRatio)
        return pixmap.fromImageInPlace(image)

    def _removeDragTarget(self):
        self.layout().removeWidget(self._dragTarget)
        self._dragTarget.hide()
        self._dragTarget.deleteLater()
        self._dragTarget = None


    def _startDrag(self, widget: QtWidgets.QWidget):
        data = QMimeData()
        if self.dataCallback:
            data.setText( self.dataCallback(widget) )

        pixmap = widget.grab()

        drag = QtGui.QDrag(widget)
        drag.setMimeData(data)
        if self.showCursorPicture:
            drag.setPixmap(pixmap)

        layout: FlowLayout = self.layout()
        self._dragWidgetIndex = layout.indexOf(widget)
        self._createDragTarget(pixmap, self._dragWidgetIndex)
        widget.hide()

        actions = Qt.DropAction.CopyAction
        if self.giveDrop:
            actions |= Qt.DropAction.MoveAction

        result = drag.exec(actions) # Blocking call

        # Moved: Remove the dragged widget.
        # Ignore MoveAction when dragged into another application.
        if result == Qt.DropAction.MoveAction and self.cursorInsideApp():
            layout.removeWidget(widget)
            widget.deleteLater()

        # Copied: Show the previously hidden dragged widget.
        else:
            # If index is invalid, dragTarget was removed because of outside events that updated this ReorderWidget's content.
            # This mustn't happen: Events need to be postponed until the drag operation is completed.
            idx = layout.indexOf(self._dragTarget)
            if idx >= 0:
                layout.insertWidget(idx, widget)
            else:
                print(">>>>>>>>>>>>>>>>>>>>>>>>> Warning: ReorderWidget updated from outside!")

            widget.show()

        self._removeDragTarget()
        layout.activate()
        QTimer.singleShot(0, self.orderChanged.emit)


    def widgetUnderCursor(self, pos) -> QtWidgets.QWidget | None:
        layout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.geometry().contains(pos):
                return item.widget()
        return None

    def cursorInsideApp(self) -> bool:
        pos = QtGui.QCursor.pos()
        for win in QtWidgets.QApplication.topLevelWindows():
            if win.geometry().contains(pos):
                return True
        return False


    def mouseMoveEvent(self, event):
        if event.buttons() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        pos = event.position().toPoint()
        if self.dragStartMinDistance > 0:
            if not self._startDragPos:
                self._startDragPos = pos
                event.ignore()
                return
            else:
                dx, dy = abs(pos.x() - self._startDragPos.x()), abs(pos.y() - self._startDragPos.y())
                if max(dx, dy) < self.dragStartMinDistance:
                    event.ignore()
                    return
                self._startDragPos = None

        if widget := self.widgetUnderCursor(pos): # Only drag direct children
            self._startDrag(widget)
            event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.accept()

    def dragLeaveEvent(self, event):
        if self._dragTarget:
            self.layout().insertWidget(self._dragWidgetIndex, self._dragTarget)
        event.accept()

    def dragMoveEvent(self, event):
        if self._dragTarget:
            index = self._findDropIndex(event)
            self.layout().insertWidget(index, self._dragTarget)
        event.accept()

    def dropEvent(self, event):
        if self._dragTarget:
            # Dropped into same widget
            action = Qt.DropAction.CopyAction
        else:
            # Dropped into different widget (only the source widget contains dragTarget)
            action = Qt.DropAction.MoveAction if self.takeDrop else Qt.DropAction.CopyAction

            text = event.mimeData().text()
            QTimer.singleShot(0, lambda text=text: self.receivedDrop.emit(text))

        event.setDropAction(action)
        event.accept()


    def _findDropIndex(self, e: QtGui.QDragMoveEvent) -> int:
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



class ManualStartReorderWidget(ReorderWidget):
    def __init__(self):
        super().__init__(False)
        self.showCursorPicture = False

    def dragEnterEvent(self, e):
        if not e.mimeData().hasText():
            e.accept()

    def mouseMoveEvent(self, e):
        pass


class ReorderDragHandle(qtlib.VerticalSeparator):
    def __init__(self, widget: QtWidgets.QWidget):
        super().__init__()
        self.setCursor(Qt.CursorShape.DragMoveCursor)
        self.widget = widget

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            reorderWidget: ReorderWidget = self.widget.parentWidget()
            reorderWidget._startDrag(self.widget)



class StringFlowBubble(QtWidgets.QFrame):
    COLOR_TEXT = "#fff"
    COLOR_TEXT_DISABLED = "#777"

    removeClicked = Signal(object)

    def __init__(self, text: str):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)

        self.button = qtlib.EditablePushButton(text, self._buttonStyleFunc)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(1, 0, 2, 0)
        layout.setSpacing(1)
        layout.addWidget(self.button)

        btnRemove = qtlib.BubbleRemoveButton()
        btnRemove.clicked.connect(lambda: self.removeClicked.emit(self))
        layout.addWidget(btnRemove)

        self.setLayout(layout)

        self.setColor(qtlib.COLOR_BUBBLE_BLACK, self.COLOR_TEXT)
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)

    @staticmethod
    def _buttonStyleFunc(button: qtlib.EditablePushButton):
        qtlib.setMonospace(button, 0.9)

    @property
    def text(self):
        return self.button.text

    @text.setter
    def text(self, text: str):
        self.button.text = text

    def setColor(self, colorBg: str, colorText: str):
        self.setStyleSheet(qtlib.bubbleClass("StringFlowBubble", colorBg))
        self.button.setStyleSheet(qtlib.bubbleStyleAux(colorBg, colorText))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        textColor = self.COLOR_TEXT if enabled else self.COLOR_TEXT_DISABLED
        self.setColor(qtlib.COLOR_BUBBLE_BLACK, textColor)



class SortedStringFlowWidget(QtWidgets.QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.MinimumExpanding)

        self.flowLayout = FlowLayout(spacing=1)
        self.flowLayout.setContentsMargins(4, 4, 4, 4)
        self.setLayout(self.flowLayout)

    def bubbles(self) -> Iterable[StringFlowBubble]:
        for i in range(self.flowLayout.count()):
            item = self.flowLayout.itemAt(i)
            if item and (widget := item.widget()) and isinstance(widget, StringFlowBubble):
                yield widget

    def addItem(self, label: str) -> bool:
        if self.hasItem(label):
            return False

        self.flowLayout.addWidget(self._createBubble(label))
        self.flowLayout.items.sort(key=lambda item: item.widget().text)
        self.flowLayout.invalidate()
        self.changed.emit()
        return True

    def hasItem(self, label: str) -> bool:
        return any(bubble.text == label for bubble in self.bubbles())

    def _createBubble(self, label: str):
        bubble = StringFlowBubble(label)
        if not self.isEnabled():
            bubble.setEnabled(False)

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
        return [bubble.text for bubble in self.bubbles()]

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
        QTimer.singleShot(0, lambda text=text: self.addItem(text))

        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()


    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        for bubble in self.bubbles():
            bubble.setEnabled(enabled)
