from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QRect, QSize, QMimeData
import lib.util as util


def setTextEditHeight(textEdit, numRows, mode=None):
    lineHeight = textEdit.fontMetrics().lineSpacing()
    docMargin = textEdit.document().documentMargin()
    frameWidth = textEdit.frameWidth()
    margins = textEdit.contentsMargins()

    height = lineHeight*numRows + 2*(docMargin + frameWidth) + margins.top() + margins.bottom()
    if mode == "max":
        textEdit.setMaximumHeight(height)
    elif mode == "min":
        textEdit.setMinimumHeight(height)
    else:
        textEdit.setFixedHeight(height)

def setMonospace(textWidget, fontSizeFactor=1.0, bold=False):
    font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
    font.setBold(bold)
    if fontSizeFactor != 1.0:
        font.setPointSizeF(font.pointSizeF() * fontSizeFactor)
    textWidget.setFont(font)

def setShowWhitespace(textEdit):
    doc = textEdit.document()
    opt = doc.defaultTextOption()
    opt.setFlags(QtGui.QTextOption.ShowTabsAndSpaces)
    doc.setDefaultTextOption(opt)

def setBoldFormat(charFormat: QtGui.QTextCharFormat, bold=True) -> None:
    charFormat.setFontWeight(700 if bold else 400)


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



class EllipsisLabel(QtWidgets.QLabel):
    _ellipsis = "…"
    _ellipsisLength = len(_ellipsis) + 2

    def __init__(self, maxLength: int):
        super().__init__()
        self.maxLength = maxLength

    def setText(self, text):
        text = text.strip().replace("\n", "↩")
        if len(text) > self.maxLength:
            partLength = max((self.maxLength - EllipsisLabel._ellipsisLength) // 2, 10)
            wordsLeft  = text[:partLength].split(" ")
            wordsRight = text[-partLength:].split(" ")

            left = ""
            lenLeft = 0
            for word in wordsLeft:
                lenWord = len(word)
                if lenLeft + 1 + lenWord > partLength:
                    break
                left += word + " "
                lenLeft += lenWord + 1

            right = ""
            lenRight = 0
            for word in reversed(wordsRight):
                lenWord = len(word)
                if lenRight + 1 + lenWord > partLength:
                    break
                right = " " + word + right
                lenRight += lenWord + 1

            text = left + EllipsisLabel._ellipsis + right
        super().setText(text)



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
        self._drag_target = QtWidgets.QLabel()
        self._drag_target.setPixmap(pixmap)
        self.layout().addWidget(self._drag_target)

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

        # TODO: Prevent removal of elements when dragged into another application
        #print(f"Drag result: {result}")
        if result == Qt.MoveAction:
            self.layout().removeWidget(widget)
            widget.deleteLater()
        else:
            widget.show() # Show this widget again, if it's dropped outside.

        self._removeDragTarget()

        if self.updateCallback:
            self.updateCallback()

    def dragEnterEvent(self, e):
        if e.mimeData().hasText:
            e.accept()

    def dragLeaveEvent(self, e):
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
        # Dropped into different widget
        if not self._drag_target:
            if self.dropCallback:
                takeDrop = self.dropCallback(e.mimeData().text())
                action = Qt.DropAction.MoveAction if takeDrop else Qt.DropAction.CopyAction
                e.setDropAction(action)
            e.accept()
            return

        # Dropped into same widget
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



class ColoredMessageStatusBar(QtWidgets.QStatusBar):
    def __init__(self, additionalStyleSheet=""):
        super().__init__()
        self.additionalStyleSheet = additionalStyleSheet + ";"
        self.updateStyleSheet()

    def showMessage(self, text, timeout=0):
        self.updateStyleSheet()
        super().showMessage(text, timeout)

    def showColoredMessage(self, text, success=True, timeout=4000):
        if success:
            self.updateStyleSheet("#00ff00")
        else:
            self.updateStyleSheet("#ff0000")
        super().showMessage(text, timeout)

    def updateStyleSheet(self, color=None):
        colorStr = f"color: {color}" if color else ""
        self.setStyleSheet("QStatusBar{" + self.additionalStyleSheet + colorStr + "}")



class SpacerWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        policy = QtWidgets.QSizePolicy.Expanding
        self.setSizePolicy(policy, policy)



class ColorCharFormats:
    def __init__(self):
        self.defaultFormat = QtGui.QTextCharFormat()
        self.saturation = 0.35

        self._formats = []
        self._nextHue = util.rnd01()
        self._colorV = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Text).valueF()
        self._colorV = max(self._colorV, 0.2)

    def getFormat(self, index: int) -> QtGui.QTextCharFormat:
        while index >= len(self._formats):
            color= util.hsv_to_rgb(self._nextHue, self.saturation, self._colorV)
            self._nextHue += 0.3819444

            charFormat = QtGui.QTextCharFormat()
            charFormat.setForeground(QtGui.QColor(color))
            self._formats.append(charFormat)
        
        return self._formats[index]

    def addFormat(self, format: QtGui.QTextCharFormat) -> None:
        self._formats.append(format)



def getHighlightColor(colorHex: str) -> QtGui.QColor:
    vPalette = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Text).valueF()
    vPalette = max(vPalette, 0.70) # min/max prevents div/0 when calculating vMix below
    vPalette = min(vPalette, 0.99)

    h, s, v = util.get_hsv(colorHex)

    # Try to keep saturation at around 0.38 for bright text (dark themes)
    # and around 0.76 for dark text (bright themes), but allow extreme values.
    # Smooth curve with start/end at 0 and 1, with plateau in the middle.
    # https://www.desmos.com/calculator/y4dgc8uz0b
    plateauLower = 1.4 if vPalette>0.71 else 0.4
    plateauWidth = 1.5
    plateau = ((2*s - 1) ** 5) * 0.5 + 0.5
    smoothstep = 3*s*s - 2*s*s*s
    sMix = (2*abs(s-0.5)) ** plateauWidth
    s = (1-sMix)*plateau + sMix*smoothstep
    s = s ** plateauLower

    # Try to keep 'v' at 'vPalette', but mix towards 'v' for extreme values.
    # Smooth curve goes through (0,1), (vPalette,0), (1,1), sample at 'v'.
    # https://www.desmos.com/calculator/obmyhuqy37
    vMix = (vPalette-v)/vPalette if v<vPalette else (v-vPalette)/(1-vPalette)
    vMix = vMix ** 8.0
    v = (1.0-vMix)*vPalette + vMix*v

    return QtGui.QColor.fromHsvF(h, s, v)



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