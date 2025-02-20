from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal
import numpy as np
import lib.util as util
from config import Config



COLOR_RED   = "#FF1616" #"#FF3030"
COLOR_GREEN = "#30FF30"

COLOR_BUBBLE_BLACK = "#161616"
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

def setMonospace(textWidget, fontSizeFactor=1.0, bold=False):
    global _fontMonospace
    if not _fontMonospace:
        _fontMonospace = loadFont(Config.fontMonospace, QtGui.QFontDatabase.SystemFont.FixedFont)

    font = QtGui.QFont(_fontMonospace)
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
        self._colorV = max(self._colorV, 0.2)

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

def bubbleStyleAux(color: str) -> str:
    return f"color: #fff; background-color: {color}; border: 0px"

def bubbleClass(className: str, color: str, borderColor=COLOR_BUBBLE_BLACK) -> str:
    return f".{className}{{color: #fff; background-color: {color}; border: 1px solid {borderColor}; border-radius: 8px}}"


class BubbleRemoveButton(QtWidgets.QPushButton):
    STYLE = f".BubbleRemoveButton{{color: #D54040; background-color: {COLOR_BUBBLE_BLACK}; border: 1px solid #401616; border-radius: 4px}}"

    def __init__(self):
        super().__init__("⨯")
        self.setFixedWidth(18)
        self.setFixedHeight(18)
        self.setStyleSheet(self.STYLE)



class ColoredButton(QtWidgets.QPushButton):
    def __init__(self, text: str, colorButton: str, colorText: str):
        super().__init__(text)

        self._originalPalette = self.palette()
        self._changedPalette = self.palette()
        self._changedPalette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor.fromString(colorButton))
        self._changedPalette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor.fromString(colorText))

    def setChanged(self, changed: bool) -> None:
        self.setPalette(self._changedPalette if changed else self._originalPalette)

class SaveButton(ColoredButton):
    def __init__(self, text: str):
        super().__init__(text, "#440A0A", "#FFEEEE")

class GreenButton(ColoredButton):
    def __init__(self, text: str):
        super().__init__(text, "#0A440A", "#EEFFEE")


class ToggleButton(QtWidgets.QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)

        self._originalPalette = self.palette()
        highlight     = self._originalPalette.color(QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.Highlight)
        highlightText = self._originalPalette.color(QtGui.QPalette.ColorGroup.Normal, QtGui.QPalette.ColorRole.HighlightedText)

        self._checkedPalette = self.palette()
        self._checkedPalette.setColor(QtGui.QPalette.ColorRole.Button, highlight)
        self._checkedPalette.setColor(QtGui.QPalette.ColorRole.ButtonText, highlightText)

        self.toggled.connect(self._onToggled)

    @Slot()
    def _onToggled(self, checked: bool):
        self.setPalette(self._checkedPalette if checked else self._originalPalette)



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

    def addMenuAction(self, text) -> QtGui.QAction:
        return self.menu.addAction(text)

    def addSubmenu(self, text):
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
