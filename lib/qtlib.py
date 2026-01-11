import weakref
from typing import Any, Callable, Iterable, cast
from contextlib import contextmanager
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QRect
import numpy as np
from lib import colorlib
from config import Config


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

def setFontBold(widget, bold: bool = True):
    font = widget.font()
    font.setBold(bold)
    widget.setFont(font)


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

def setTextPreserveUndo(cursor: QtGui.QTextCursor, text: str):
    cursor.beginEditBlock()
    cursor.select(QtGui.QTextCursor.SelectionType.Document)
    cursor.insertText(text)

    # Further text input is merged with this edit block. Ctrl+Z would remove the typed text, plus this inserted text.
    # Add and delete a space char to avoid merging the commands in the undo stack.
    cursor.insertText(" ")
    cursor.deletePreviousChar()
    cursor.endEditBlock()


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
    'Returns BGR(A) format.'
    # Assume little-endian, where Qt's Format_ARGB32 data is read in BGRA order
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
        color = colorlib.GREEN if success else colorlib.RED
        self.updateStyleSheet(color)
        super().showMessage(text, timeout)

    def updateStyleSheet(self, color=None):
        colorStr = f"color: {color}" if color else ""
        self.setStyleSheet("QStatusBar{" + self.additionalStyleSheet + colorStr + "}")


class ProgressBar(QtWidgets.QProgressBar):
    def __init__(self):
        super().__init__()

        # Fix white on white text in bright theme
        if not colorlib.DARK_THEME:
            palette = self.palette()
            textColor = palette.color(QtGui.QPalette.ColorRole.Text)
            palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, textColor)
            highlight = palette.color(QtGui.QPalette.ColorRole.Highlight)
            palette.setColor(QtGui.QPalette.ColorRole.Highlight, highlight.lighter())
            self.setPalette(palette)



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



class BubbleRemoveButton(QtWidgets.QPushButton):
    STYLE = None

    def __init__(self):
        super().__init__("⨯")
        self.setFixedWidth(18)
        self.setFixedHeight(18)

        if BubbleRemoveButton.STYLE is None:
            BubbleRemoveButton.STYLE = colorlib.removeButtonStyle("BubbleRemoveButton")
        self.setStyleSheet(BubbleRemoveButton.STYLE)



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
        color = "#440A0A" if colorlib.DARK_THEME else "#8A0A0A"
        super().__init__(text, color, "#FFEEEE")

class GreenButton(ColoredButton):
    def __init__(self, text: str):
        color = "#0A440A" if colorlib.DARK_THEME else "#2A8A2A"
        super().__init__(text, color, "#EEFFEE")



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

    @Slot(bool)
    def _onToggled(self, checked: bool):
        self.setPalette(ToggleButton.PALETTE_CHECKED if checked else ToggleButton.PALETTE_ORIG)



class MenuComboBox(QtWidgets.QComboBox):
    def __init__(self, title: str = None, menuClass=QtWidgets.QMenu):
        super().__init__()
        self.menuClass = menuClass
        self.menu = self.menuClass(title, self)

        self._activeActions: list[QtGui.QAction] = list()
        self._actions: dict[int, tuple[str, QtGui.QAction]] = dict()
        self._nextIndex = 0

    def _updateActiveActions(self):
        for act in self._activeActions:
            setFontBold(act, False)
        self._activeActions.clear()

        currentEntry = self._actions.get(self.currentIndex())
        if currentEntry is None:
            return

        text, action = currentEntry
        if text == self.currentText():
            try:
                self.menu.setActiveAction(action)
            except Exception as ex:
                # Why does this happen? RuntimeError: Internal C++ object (PySide6.QtGui.QAction) already deleted.
                print(f"Failed to set active action in MenuComboBox: {ex} ({type(ex).__name__})")
                return

            setFontBold(action)
            self._activeActions.append(action)

            # Set bold text to all parent submenus.
            # But don't activate submenus: That would open them and they could swallow mouse hover events.
            item = action
            while (item := item.parent()) and item is not self.menu and isinstance(item, QtWidgets.QMenu):
                action = item.menuAction()
                setFontBold(action)
                self._activeActions.append(action)


    def showPopup(self):
        self._updateActiveActions()
        self.menu.setMinimumWidth(self.width())
        point = self.mapToGlobal(self.rect().topLeft())
        self.menu.exec_(point)
        self.hidePopup()


    def addItem(self, text: str, userData=None):
        self.addSubmenuItem(self.menu, text, "", userData)

    def addItems(self, items: list[str]):
        for item in items:
            self.addItem(item)

    def addItemWithoutMenuAction(self, text: str, userData=None):
        super().addItem(text, userData)
        self._nextIndex += 1

    def addMenuAction(self, text: str) -> QtGui.QAction:
        return self.menu.addAction(text)

    def addSubmenu(self, text: str, parentMenu: QtWidgets.QMenu | None = None):
        if parentMenu is None:
            parentMenu = self.menu

        submenu = self.menuClass(text, parentMenu)
        parentMenu.addMenu(submenu)
        return submenu

    def addSubmenuItem(self, submenu: QtWidgets.QMenu, text: str, prefix: str, userData=None, actionText: str | None = None):
        itemText = prefix + text
        super().addItem(itemText, userData)

        index = self._nextIndex
        self._nextIndex += 1

        act = submenu.addAction(actionText or text)
        act.triggered.connect(lambda checked, i=index: self.setCurrentIndex(i))
        self._actions[index] = (itemText, act)

    def addSeparator(self):
        self.menu.addSeparator()

    def clear(self):
        super().clear()
        self._activeActions.clear()
        self._actions.clear()
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
        def __init__(self, filter: 'LayoutFilter'):
            super().__init__()
            self.setPlaceholderText("Filter")
            setMonospace(self)
            self.filter = weakref.ref(filter)

        def keyPressEvent(self, event: QtGui.QKeyEvent):
            match event.key():
                case Qt.Key.Key_Escape:
                    self.clear()
                    if (filter := self.filter()):
                        filter.updated.emit()

                    event.accept()
                    return

            super().keyPressEvent(event)


    updated = Signal()

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

        self.txtFilter = LayoutFilter.FilterTextEdit(self)
        self.txtFilter.textChanged.connect(self.setFilterText)
        self.txtFilter.editingFinished.connect(self.updated.emit)

        btnClearFilter = BubbleRemoveButton()
        btnClearFilter.setToolTip("Clear Filter")
        btnClearFilter.clicked.connect(self.txtFilter.clear)
        btnClearFilter.clicked.connect(self.updated.emit)

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

    @Slot()
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
            color = colorlib.GREEN if numVisible > 0 else colorlib.RED
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



class SingletonWindow(QtWidgets.QMainWindow):
    _instances = dict[type, 'SingletonWindow']()

    def __new__(cls, *args, **kwargs):
        win = cls._instances.get(cls)
        if win is None:
            cls._instances[cls] = win = super(SingletonWindow, cls).__new__(cls)
        return cast(cls, win)

    def __init__(self, parent=None):
        if getattr(self, '_singleton_initialized', False):
            return

        super().__init__(parent)
        self._singleton_initialized = True
        self._init_singleton()

        self.move(self.screen().geometry().center() - self.frameGeometry().center())

    def _init_singleton(self):
        raise NotImplementedError()

    def closeEvent(self, event):
        SingletonWindow._instances.pop(type(self), None)
        super().closeEvent(event)

    @classmethod
    def closeAllWindows(cls):
        for win in list(cls._instances.values()):
            win.close()

    @classmethod
    def isWindowOpen(cls) -> bool:
        return cls in cls._instances
