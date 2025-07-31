from typing import Any, Callable, Iterable
from contextlib import contextmanager
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QRect
import numpy as np
import lib.util as util
from config import Config



COLOR_RED   = "#FF1616" #"#FF3030"
COLOR_GREEN = "#30FF30"

COLOR_BUBBLE_BLACK = "#161616"
COLOR_BUBBLE_HOVER = "#808070"
COLOR_BUBBLE_BAN   = "#454545"



_fontMonospace: QtGui.QFont | None = None

def loadFont(path: str, fallback: QtGui.QFontDatabase.SystemFont) -> QtGui.QFont:
    font = QtGui.QFontDatabase.systemFont(fallback)
    if not path:
        return font

    fontId = QtGui.QFontDatabase.addApplicationFont(path)
    if fontId < 0:
        print(f"Failed to load font from {path}")
        return font

    fontFamily = QtGui.QFontDatabase.applicationFontFamilies(fontId)[0]
    font.setFamily(fontFamily)
    return font

def getMonospaceFont():
    global _fontMonospace
    if not _fontMonospace:
        _fontMonospace = loadFont(Config.fontMonospace, QtGui.QFontDatabase.SystemFont.FixedFont)

    return QtGui.QFont(_fontMonospace)

def setMonospace(textWidget, fontSizeFactor=1.0, bold=False):
    font = getMonospaceFont()
    font.setBold(bold)
    if fontSizeFactor != 1.0:
        font.setPointSizeF(font.pointSizeF() * fontSizeFactor)
    textWidget.setFont(font)



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

def setShowWhitespace(textEdit):
    doc = textEdit.document()
    opt = doc.defaultTextOption()
    opt.setFlags(QtGui.QTextOption.ShowTabsAndSpaces)
    doc.setDefaultTextOption(opt)



def numpyToQImageMask(mat: np.ndarray) -> QtGui.QImage:
    # QImage needs alignment to 32bit/4bytes. Add padding.
    height, width = mat.shape
    bytesPerLine = ((width+3) // 4) * 4
    if width != bytesPerLine:
        padded = np.zeros((height, bytesPerLine), dtype=np.uint8)
        padded[:, :width] = mat
        mat = padded

    return QtGui.QImage(mat, width, height, QtGui.QImage.Format.Format_Grayscale8)

def numpyToQImage(mat: np.ndarray) -> QtGui.QImage:
    if len(mat.shape) < 3:
        return numpyToQImageMask(mat)

    # QImage needs alignment to 32bit/4bytes. Add padding.
    height, width, channels = mat.shape
    lineLen = width * channels
    bytesPerLine = ((lineLen+3) // 4) * 4
    if lineLen != bytesPerLine:
        padded = np.zeros((height, bytesPerLine//channels, channels), dtype=np.uint8)
        padded[:, :width, :] = mat
        mat = padded

    format = QtGui.QImage.Format.Format_ARGB32 if channels == 4 else QtGui.QImage.Format.Format_RGB32
    return QtGui.QImage(mat, width, height, format)


def qimageToNumpyMask(image: QtGui.QImage) -> np.ndarray:
    buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
    buffer.shape = (image.height(), image.bytesPerLine())
    return np.copy( buffer[:, :image.width()] ) # Remove padding

def qimageToNumpy(image: QtGui.QImage) -> np.ndarray:
    buffer = np.frombuffer(image.constBits(), dtype=np.uint8)
    channels = image.depth() // 8
    width = image.bytesPerLine() // channels
    buffer.shape = (image.height(), width, channels)
    return np.copy( buffer[:, :image.width(), :] ).squeeze() # Remove padding



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

    def setText(self, text: str):
        text = text.strip().replace("\n", "↩")
        if len(text) > self.maxLength:
            partLength = max((self.maxLength - self._ellipsisLength) // 2, 10)
            wordsLeft  = text[:partLength].split(" ")
            wordsRight = text[-partLength:].split(" ")

            chosenWords = []
            lenLeft = 0
            for word in wordsLeft:
                if lenLeft + len(word) + 1 > partLength:
                    break
                lenLeft += len(word) + 1
                chosenWords.append(word)

            chosenWordsRight = []
            lenRight = 0
            for word in reversed(wordsRight):
                if lenRight + len(word) + 1 > partLength:
                    break
                lenRight += len(word) + 1
                chosenWordsRight.append(word)

            chosenWords.append(self._ellipsis)
            chosenWords.extend(reversed(chosenWordsRight))
            text = " ".join(chosenWords)

        super().setText(text)



class EditablePushButton(QtWidgets.QWidget):
    clicked     = Signal(str)
    textChanged = Signal(str)
    textEmpty   = Signal(object)

    def __init__(self, text, stylerFunc=None, parent=None, extraWidth=0):
        super().__init__(parent)
        self.stylerFunc = stylerFunc
        self.extraWidth = 12 + extraWidth

        self.button = QtWidgets.QPushButton(text)
        self.button.clicked.connect(self.click)
        self.button.mousePressEvent = self._button_mousePressEvent
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

    @text.setter
    def text(self, text: str) -> None:
        self.activeWidget().setText(text)
        self._updateWidth()

    def activeWidget(self):
        return self.edit if self.edit else self.button

    def sizeHint(self):
        return self.activeWidget().sizeHint()

    # Handles clicks by other means than mouse left button (e.g. keyboard)
    @Slot()
    def click(self):
        self.clicked.emit(self.button.text())
        self.button.setDown(False)

    def _button_mousePressEvent(self, event):
        # This fixes dragging of CaptionControlGroup elements:
        # To start the drag, ReorderWidget must receive mouse events, which would be swallowed without this.
        # (mouse tracking is off, so events are only reeived when holding a mouse button)
        event.ignore()

    def _button_mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click()
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.setEditMode()
            event.accept()

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
            self.updateStyleSheet(COLOR_GREEN)
        else:
            self.updateStyleSheet(COLOR_RED)
        super().showMessage(text, timeout)

    def updateStyleSheet(self, color=None):
        colorStr = f"color: {color}" if color else ""
        self.setStyleSheet("QStatusBar{" + self.additionalStyleSheet + colorStr + "}")



class SpacerWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        policy = QtWidgets.QSizePolicy.Expanding
        self.setSizePolicy(policy, policy)



class VerticalSeparator(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._buildFrame())
        layout.addWidget(self._buildFrame())
        self.setLayout(layout)

    def _buildFrame(self):
        frame = QtWidgets.QFrame()
        frame.setFixedWidth(2)
        frame.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        frame.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        frame.setLineWidth(1)
        frame.setMidLineWidth(1)
        return frame



class ColorCharFormats:
    def __init__(self):
        self.defaultFormat = QtGui.QTextCharFormat()
        self.saturation = 0.35

        self._formats = []
        self._nextHue = util.rnd01()
        self._colorV = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Text).valueF()
        self._colorV = max(self._colorV, 0.7)

    def getFormat(self, index: int) -> QtGui.QTextCharFormat:
        while index >= len(self._formats):
            color = util.hsv_to_rgb(self._nextHue, self.saturation, self._colorV)
            self._nextHue += 0.3819444

            charFormat = QtGui.QTextCharFormat()
            charFormat.setForeground(QtGui.QColor(color))
            self._formats.append(charFormat)

        return self._formats[index]

    def addFormat(self, format: QtGui.QTextCharFormat) -> None:
        self._formats.append(format)


def setBoldFormat(charFormat: QtGui.QTextCharFormat, bold=True) -> None:
    charFormat.setFontWeight(700 if bold else 400)

def toDisabledFormat(charFormat: QtGui.QTextCharFormat) -> QtGui.QTextCharFormat:
    color = charFormat.foreground().color()
    h, s, v, a = color.getHsvF()
    color.setHsvF(h, 0.25, 0.5, a)
    charFormat = QtGui.QTextCharFormat()
    charFormat.setForeground(color)
    return charFormat



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



def htmlRed(text: str) -> str:
    return f"<font color='{COLOR_RED}'>{text}</font>"


def bubbleStyle(color: str, borderColor=COLOR_BUBBLE_BLACK) -> str:
    return f"color: #fff; background-color: {color}; border: 1px solid {borderColor}; border-radius: 8px"

def bubbleStylePad(color: str, padding=2, borderColor=COLOR_BUBBLE_BLACK) -> str:
    return f"color: #fff; background-color: {color}; border: 1px solid {borderColor}; border-radius: 8px; padding: {padding}px"

def bubbleStyleAux(color: str, textColor="#fff") -> str:
    return f"color: {textColor}; background-color: {color}; border: 0px"

def bubbleClass(className: str, color: str, borderColor=COLOR_BUBBLE_BLACK) -> str:
    return f".{className}{{color: #fff; background-color: {color}; border: 1px solid {borderColor}; border-radius: 8px}}"

def bubbleClassAux(className: str, auxClassName: str, colorBg: str, borderColor=COLOR_BUBBLE_BLACK, textColor="#fff") -> str:
    return f".{className}{{background-color: {colorBg}; border: 1px solid {borderColor}; border-radius: 8px}}" \
           f".{auxClassName}{{color: {textColor}}}"



class BubbleRemoveButton(QtWidgets.QPushButton):
    STYLE = f".BubbleRemoveButton{{color: #D54040; background-color: {COLOR_BUBBLE_BLACK}; border: 1px solid #401616; border-radius: 4px}}"

    def __init__(self):
        super().__init__("⨯")
        self.setFixedWidth(18)
        self.setFixedHeight(18)
        self.setStyleSheet(self.STYLE)



class ColoredButton(QtWidgets.QPushButton):
    PALETTE_ORIG: QtGui.QPalette = None
    PALETTES_CHANGED: dict[tuple[str, str], QtGui.QPalette] = dict()

    def __init__(self, text: str, colorButton: str, colorText: str):
        super().__init__(text)

        if not ColoredButton.PALETTE_ORIG:
            ColoredButton.PALETTE_ORIG = self.palette()

        self._changedPalette = self._getChangedPalette(colorButton, colorText)

    def _getChangedPalette(self, colorButton: str, colorText: str) -> QtGui.QPalette:
        key = (colorButton, colorText)
        if palette := ColoredButton.PALETTES_CHANGED.get(key):
            return palette

        changedPalette = self.palette()
        changedPalette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor.fromString(colorButton))
        changedPalette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor.fromString(colorText))

        ColoredButton.PALETTES_CHANGED[key] = changedPalette
        return changedPalette

    def setChanged(self, changed: bool) -> None:
        self.setPalette(self._changedPalette if changed else ColoredButton.PALETTE_ORIG)


class SaveButton(ColoredButton):
    def __init__(self, text: str):
        super().__init__(text, "#440A0A", "#FFEEEE")

class GreenButton(ColoredButton):
    def __init__(self, text: str):
        super().__init__(text, "#0A440A", "#EEFFEE")



class ToggleButton(QtWidgets.QPushButton):
    PALETTE_ORIG:    QtGui.QPalette = None
    PALETTE_CHECKED: QtGui.QPalette = None

    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)

        if not ToggleButton.PALETTE_ORIG:
            self._initPalettes()
        self.setPalette(ToggleButton.PALETTE_ORIG)

        self.toggled.connect(self._onToggled)

    def _initPalettes(self):
        palette  = self.palette()
        colorBtn = palette.color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Button)
        palette.setBrush(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Button, colorBtn.darker(125))
        ToggleButton.PALETTE_ORIG = palette

        palette   = self.palette()
        colorBtn  = palette.color(QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.Highlight)
        colorText = palette.color(QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.HighlightedText)
        palette.setBrush(QtGui.QPalette.ColorGroup.All, QtGui.QPalette.ColorRole.Button, colorBtn)
        palette.setBrush(QtGui.QPalette.ColorGroup.All, QtGui.QPalette.ColorRole.ButtonText, colorText)
        palette.setBrush(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Button, colorBtn.darker())
        palette.setBrush(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.ButtonText, colorText.darker())
        ToggleButton.PALETTE_CHECKED = palette

    @Slot()
    def _onToggled(self, checked: bool):
        self.setPalette(ToggleButton.PALETTE_CHECKED if checked else ToggleButton.PALETTE_ORIG)



class MenuComboBox(QtWidgets.QComboBox):
    def __init__(self, title: str = None):
        super().__init__()
        self.menu = QtWidgets.QMenu(title)
        self._nextIndex = 0

    def showPopup(self):
        self.menu.setMinimumWidth(self.width())
        point = self.mapToGlobal(self.rect().topLeft())
        self.menu.exec_(point)
        self.hidePopup()


    def addItem(self, text: str, userData=None):
        super().addItem(text, userData)

        index = self._nextIndex
        self._nextIndex += 1

        act = self.menu.addAction(text)
        act.triggered.connect(lambda checked, i=index: self.setCurrentIndex(i))

    def addItems(self, items: list[str]):
        for item in items:
            self.addItem(item)

    def addItemWithoutMenuAction(self, text: str, userData=None):
        super().addItem(text, userData)
        self._nextIndex += 1

    def addMenuAction(self, text: str) -> QtGui.QAction:
        return self.menu.addAction(text)

    def addSubmenu(self, text: str):
        submenu = QtWidgets.QMenu(text)
        self.menu.addMenu(submenu)
        return submenu

    def addSubmenuItem(self, submenu: QtWidgets.QMenu, text: str, prefix: str, userData=None):
        super().addItem(prefix + text, userData)

        index = self._nextIndex
        self._nextIndex += 1

        act = submenu.addAction(text)
        act.triggered.connect(lambda checked, i=index: self.setCurrentIndex(i))

    def addSeparator(self):
        self.menu.addSeparator()

    def clear(self):
        super().clear()
        self.menu.clear()
        self._nextIndex = 0



class NonScrollComboBox(QtWidgets.QComboBox):
    def __init__(self):
        super().__init__()

    def wheelEvent(self, e: QtGui.QWheelEvent) -> None:
        e.ignore()



class PercentageSpinBox(QtWidgets.QSpinBox):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(0, 100)
        self.setValue(100)
        self.setSingleStep(5)
        self.setSuffix(" %")



class BaseColorScrollArea(QtWidgets.QScrollArea):
    def __init__(self, widget: QtWidgets.QWidget, colorRole=QtGui.QPalette.ColorRole.Base):
        super().__init__()
        self.setWidget(widget)
        self.setWidgetResizable(True)

        palette = self.palette()
        bgColor = palette.color(colorRole)
        palette.setColor(QtGui.QPalette.ColorRole.Window, bgColor)
        self.setPalette(palette)



class RowScrollArea(BaseColorScrollArea):
    def __init__(self, widget: QtWidgets.QWidget, canHaveInvisible: bool = False):
        super().__init__(widget)
        self.hasInvisible = canHaveInvisible

    def _getItemIndexAtY(self, y: int, compareBottom: bool) -> int:
        'Does not handle invisible items.'

        layout: QtWidgets.QLayout = self.widget().layout()
        rowY = QRect.bottom if compareBottom else QRect.top

        # Binary search
        lo = 0
        hi = max(layout.count()-1, 0)

        while lo < hi:
            row = (lo+hi) // 2
            rect = layout.itemAt(row).geometry()
            if y > rowY(rect):
                lo = row+1 # Continue in upper half
            else:
                hi = row   # Continue in lower half

        #assert(lo == hi)
        return lo

    def _getNextItemIndex(self, y: int, scrollDown: bool) -> int:
        layout: QtWidgets.QLayout = self.widget().layout()
        rowY = QRect.bottom if scrollDown else QRect.top

        row = lastRow = -1
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget().isVisible():
                lastRow = row
                row = i

                if rowY(item.geometry()) >= y:
                    break

        if scrollDown:
            return next((
                i for i in range(row+1, layout.count())
                if (item := layout.itemAt(i)) and item.widget().isVisible()
            ),
            layout.count())
        else:
            return lastRow


    def wheelEvent(self, event: QtGui.QWheelEvent):
        scrollBar = self.verticalScrollBar()
        scrollDown = event.angleDelta().y() < 0

        if self.hasInvisible:
            row = self._getNextItemIndex(scrollBar.value(), scrollDown)
        else:
            row = self._getItemIndexAtY(scrollBar.value(), scrollDown)
            row += 1 if scrollDown else -1

        if row <= 0:
            y = 0
        elif item := self.widget().layout().itemAt(row):
            y = item.geometry().top()
        else:
            y = scrollBar.maximum()

        scrollBar.setValue(y)

    def ensureWidgetVisible(self, childWidget: QtWidgets.QWidget, xmargin: int = 0, ymargin: int = 0) -> None:
        index = self.widget().layout().indexOf(childWidget)
        if item := self.widget().layout().itemAt(index):
            rect = item.geometry()
            scrollBar = self.verticalScrollBar()
            scrollVal = scrollBar.value()

            if rect.top() < scrollVal:
                scrollBar.setValue(rect.top())
            elif rect.bottom() > scrollVal + self.height():
                scrollBar.setValue(rect.bottom() - self.height())



class CheckboxItemWidget(QtWidgets.QWidget):
    def __init__(self, text: str):
        super().__init__()
        self.checkbox = QtWidgets.QCheckBox()
        self.label = QtWidgets.QLabel(text)

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.checkbox)
        layout.addWidget(self.label)
        self.setLayout(layout)

    @property
    def checked(self) -> bool:
        return self.checkbox.isChecked()

    @checked.setter
    def checked(self, state: bool):
        self.checkbox.setChecked(state)

    @property
    def text(self) -> str:
        return self.label.text()

    @text.setter
    def text(self, text: str):
        self.label.setText(text)


class CheckableListWidget(QtWidgets.QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

    def addCheckboxItem(self, text: str, checked=False) -> CheckboxItemWidget:
        widget = CheckboxItemWidget(text)
        widget.checked = checked
        item = QtWidgets.QListWidgetItem()
        self.addItem(item)
        self.setItemWidget(item, widget)
        return widget

    def getCheckboxItem(self, item: QtWidgets.QListWidgetItem) -> CheckboxItemWidget:
        return self.itemWidget(item)



class LayoutFilter(QtWidgets.QHBoxLayout):
    class FilterTextEdit(QtWidgets.QLineEdit):
        def __init__(self):
            super().__init__()
            self.setPlaceholderText("Filter")
            setMonospace(self)

        def keyPressEvent(self, event: QtGui.QKeyEvent):
            match event.key():
                case Qt.Key.Key_Escape:
                    self.clear()
                    event.accept()
                    return

            super().keyPressEvent(event)


    def __init__(self, layout: QtWidgets.QLayout, textGetter: Callable[[Any], Iterable[str]]):
        super().__init__()
        self._filterLayout = layout
        self._textGetter: Callable[[QtWidgets.QWidget], Iterable[str]] = textGetter

        import re
        self._filterPattern: re.Pattern | None = None

        self._numVisible: int = -1
        self._statusName: str = "Rows"
        self._lblStatus: QtWidgets.QLabel | None = None
        self._updatesDisabled: bool = False

        self.txtFilter = LayoutFilter.FilterTextEdit()
        self.txtFilter.textChanged.connect(self.setFilterText)

        btnClearFilter = BubbleRemoveButton()
        btnClearFilter.setToolTip("Clear Filter")
        btnClearFilter.clicked.connect(self.txtFilter.clear)

        self.addWidget(btnClearFilter)
        self.addSpacing(2)
        self.addWidget(self.txtFilter)


    @property
    def numVisible(self) -> int:
        if self._filterPattern is None:
            return self._filterLayout.count()
        return self._numVisible


    @Slot()
    def setFilterText(self, filterText: str):
        if filterText:
            import re
            self._filterPattern = re.compile(filterText, re.IGNORECASE)
        else:
            self._filterPattern = None

        self.update()

    @Slot()
    def clearFilterText(self):
        self.txtFilter.clear()

    def setStatusLabel(self, name: str, label: QtWidgets.QLabel):
        self._statusName = name
        self._lblStatus = label
        self.updateStatus()


    def _checkTexts(self, widget: QtWidgets.QWidget) -> bool:
        return any(
            self._filterPattern.search(text) is not None
            for text in self._textGetter(widget)
        )

    def update(self):
        filterFunc = self._checkTexts if self._filterPattern is not None else bool
        self._numVisible = 0

        for i in range(self._filterLayout.count()):
            item = self._filterLayout.itemAt(i)
            if item and (widget := item.widget()):
                visible = filterFunc(widget)
                widget.setVisible(visible)
                if visible:
                    self._numVisible += 1

        self.updateStatus()

    def updateStatus(self):
        if self._updatesDisabled or self._lblStatus is None:
            return

        numTotal = self._filterLayout.count()
        numVisible = self.numVisible

        text = f"{numTotal} {self._statusName}"
        if numTotal == 1:
            text = text.rstrip("s")

        if numVisible < numTotal:
            text = f"Showing {numVisible} / " + text
            color = COLOR_GREEN if numVisible > 0 else COLOR_RED
            self._lblStatus.setStyleSheet(f"color: {color}")
        else:
            self._lblStatus.setStyleSheet("")

        self._lblStatus.setText(text)

    @contextmanager
    def postponeUpdates(self):
        try:
            self._updatesDisabled = True
            yield self
        finally:
            self._updatesDisabled = False
            self.updateStatus()
