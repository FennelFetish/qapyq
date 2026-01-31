from typing import Iterable, Callable
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QSize, QRect, QPoint, QMimeData, QTimer
import numpy as np
from lib import colorlib, qtlib


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
    COLOR_FACTORS_BRIGHTER = [1.60, 1.90, 2.00, 1.0] # BGRA
    COLOR_FACTORS_DARKER   = [0.75, 0.82, 0.85, 1.0]

    orderChanged = Signal()
    receivedDrop = Signal(str)

    def __init__(self, giveDrop=False, takeDrop=False):
        super().__init__()
        self.setAcceptDrops(True)

        self._dragStartPos: QPoint | None = None
        self._dragTarget: QtWidgets.QWidget | None = None
        self._dragOrigIndex: int = -1
        self._dragCurrentIndex: int = -1

        self.dataCallback: Callable[[QtWidgets.QWidget], str] | None = None # Returns the dropped text for a child widget

        self.giveDrop = giveDrop # Remove from self widget if another widget is drop target
        self.takeDrop = takeDrop # Remove from source widget if self is drop target

        self.dragStartMinDistance: int = 0
        self.showCursorPicture = True

        self._scrollArea: QtWidgets.QScrollArea | None = None
        self.scrollBorderSize = 40
        self.scrollBorderSpeed = 12

        self._postDragCallback: Callable | None = None


    def enableBorderScroll(self, scrollArea: QtWidgets.QScrollArea):
        self._scrollArea = scrollArea

    def isDragActive(self) -> bool:
        return self._dragTarget != None

    def setPostDragCallback(self, callback: Callable):
        self._postDragCallback = callback


    def _createDragTarget(self, pixmap: QtGui.QPixmap, index: int):
        pixmap = self._adjustColor(pixmap)
        self._dragTarget = QtWidgets.QLabel()
        self._dragTarget.setPixmap(pixmap)
        self.layout().addWidget(self._dragTarget)
        self.layout().insertWidget(index, self._dragTarget)
        self._dragCurrentIndex = index

    def _adjustColor(self, pixmap: QtGui.QPixmap):
        image = pixmap.toImage()
        pixelRatio = image.devicePixelRatioF()

        mat = qtlib.qimageToNumpy(image)
        matF = mat.astype(np.float32)
        matF *= self.COLOR_FACTORS_BRIGHTER if colorlib.DARK_THEME else self.COLOR_FACTORS_DARKER
        matF.clip(0.0, 255.0, mat, casting="unsafe")

        image = qtlib.numpyToQImage(mat)
        image.setDevicePixelRatio(pixelRatio)
        return pixmap.fromImageInPlace(image)

    def _removeDragTarget(self):
        self.layout().removeWidget(self._dragTarget)
        self._dragTarget.hide()
        self._dragTarget.deleteLater()
        self._dragTarget = None
        self._dragCurrentIndex = -1


    def _startDrag(self, widget: QtWidgets.QWidget):
        data = QMimeData()
        if self.dataCallback:
            data.setText( self.dataCallback(widget) )

        pixmap = widget.grab()

        drag = QtGui.QDrag(widget)
        drag.setMimeData(data)
        if self.showCursorPicture:
            drag.setPixmap(pixmap)

        layout = self.layout()
        self._dragOrigIndex = layout.indexOf(widget)
        self._createDragTarget(pixmap, self._dragOrigIndex)
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
        QTimer.singleShot(0, self._onDragFinished)

    @Slot()
    def _onDragFinished(self):
        if self._postDragCallback:
            self._postDragCallback()
            self._postDragCallback = None

        self.orderChanged.emit()


    def widgetUnderCursor(self, pos: QPoint) -> QtWidgets.QWidget | None:
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


    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        if event.buttons() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        pos = event.position().toPoint()
        if self.dragStartMinDistance > 0:
            if not self._dragStartPos:
                self._dragStartPos = pos
                event.ignore()
                return
            else:
                dx, dy = abs(pos.x() - self._dragStartPos.x()), abs(pos.y() - self._dragStartPos.y())
                if max(dx, dy) < self.dragStartMinDistance:
                    event.ignore()
                    return

                pos = self._dragStartPos
                self._dragStartPos = None

        if widget := self.widgetUnderCursor(pos): # Only drag direct children
            self._startDrag(widget)
            event.accept()

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasText():
            event.accept()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent):
        if self._dragTarget:
            # DragLeaveEvents can also arrive if the cursor enters grandchild widgets with acceptDrops enabled.
            # This can cause jitter. Only reset drag target if the cursor left the widget.
            cursorPos = self.mapFromGlobal(QtGui.QCursor.pos())
            if not self.rect().contains(cursorPos):
                self._dragCurrentIndex = self._dragOrigIndex
                self.layout().insertWidget(self._dragOrigIndex, self._dragTarget)

        event.accept()


    def dragMoveEvent(self, event: QtGui.QDragMoveEvent):
        if self._dragTarget:
            if not self._dragTarget.geometry().contains(event.pos()):
                index = self._findDropIndex(event)
                if index >= 0 and index != self._dragCurrentIndex:
                    self._dragCurrentIndex = index
                    self.layout().insertWidget(index, self._dragTarget)

            if self._scrollArea:
                self._dragScroll(event.pos())

        event.accept()

    def _dragScroll(self, mousePos: QPoint):
        vScrollBar = self._scrollArea.verticalScrollBar()
        scrollPos = vScrollBar.value()
        y = mousePos.y() - scrollPos

        if y < self.scrollBorderSize:
            vScrollBar.setValue(scrollPos - self.scrollBorderSpeed)
        elif y > self._scrollArea.rect().bottom() - self.scrollBorderSize:
            vScrollBar.setValue(scrollPos + self.scrollBorderSpeed)


    def dropEvent(self, event: QtGui.QDropEvent):
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
        layout = self.layout()
        source: QtWidgets.QWidget = e.source()
        x, y = e.position().toTuple()

        def nextVisibleIndex(index: int, offset: int, max: int) -> int:
            for k in range(index, max+offset, offset):
                widget = layout.itemAt(k).widget()
                if (not widget.isHidden()) or (widget is source) or (widget is self._dragTarget):
                    return k
            raise IndexError()

        # Binary search
        lo = 0
        hi = max(layout.count()-1, 0)

        # I think Drag&Drop grabs the inputs from the OS. Check max iteration count, just in case, to prevent freezing the OS.
        maxIt = 1000
        while lo < hi and maxIt > 0:
            maxIt -= 1

            try:
                lo = nextVisibleIndex(lo, 1, hi)
                hi = nextVisibleIndex(hi, -1, lo)
                if lo == hi:
                    break

                i = (lo+hi) // 2

                try:
                    i = nextVisibleIndex(i, -1, lo)
                except IndexError:
                    lo = i+1
                    i = nextVisibleIndex(lo, 1, hi)
            except IndexError:
                return -1

            rect = layout.itemAt(i).geometry()
            if rect.bottom() < y:
                lo = i+1 # Continue in upper half
            elif rect.top() > y:
                hi = i   # Continue in lower half
            else:
                if rect.right() < x:
                    lo = i+1 # Continue in upper half
                else:
                    hi = i   # Continue in lower half

        assert(lo == hi)
        i = lo

        # Prevent moving to start of line when aiming between lines
        rect = layout.itemAt(i).geometry()
        if y < rect.top() or y > rect.bottom():
            return -1

        # Additional checks to prevent jitter when neighboring elements have different sizes.
        # For filtered layouts with sparse visible indexes, this may jitter once before the elements are made neighbors.
        move = i - self._dragCurrentIndex
        if abs(move) == 1:
            srcRect = self._dragTarget.geometry()
            dw = (rect.width()  - srcRect.width())  // 2
            dh = (rect.height() - srcRect.height()) // 2

            if move > 0:
                if dw > 0:
                    # Prevent jitter with short element at end of previous row
                    if rect.top() > srcRect.bottom():
                        dw = rect.width()
                    if x <= rect.left() + dw:
                        return -1

                if dh > 0 and y <= rect.top() + dh:
                    return -1
            else:
                if dw > 0 and x > rect.right() - dw:
                    return -1
                if dh > 0 and y > rect.bottom() - dh:
                    return -1

        return i



class ManualStartReorderWidget(ReorderWidget):
    def __init__(self):
        super().__init__(False)
        self.showCursorPicture = False

    def dragEnterEvent(self, e):
        if not e.mimeData().hasText():
            e.accept()

    def mouseMoveEvent(self, e):
        # Disable parent method
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
    removeClicked = Signal(object)

    def __init__(self, text: str):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)

        self.button = qtlib.EditablePushButton(text, self._buttonStyleFunc)

        btnRemove = qtlib.BubbleRemoveButton()
        btnRemove.clicked.connect(lambda: self.removeClicked.emit(self))

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(1, 0, 2, 0)
        layout.setSpacing(1)
        layout.addWidget(self.button)
        layout.addWidget(btnRemove)
        self.setLayout(layout)

        self.setColor(colorlib.BUBBLE_BG, colorlib.BUBBLE_TEXT)

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
        self.setStyleSheet(colorlib.bubbleClass("StringFlowBubble", colorBg))
        self.button.setStyleSheet(colorlib.bubbleStyleNoBorder(colorBg, colorText))

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        textColor = colorlib.BUBBLE_TEXT if enabled else colorlib.BUBBLE_TEXT_DISABLED
        self.setColor(colorlib.BUBBLE_BG, textColor)



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
