from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QObject, QEvent
import lib.qtlib as qtlib
from ui.flow_layout import FlowLayout
from ui.tab import ImgTab
from .caption_container import CaptionContainer, CaptionContext

# - As tab in Caption Window
# - Overrides current colors, highlights defined tags

# - Auto select next file after input
# - Move back / restore old caption
# - Skip without change (when edited manually with Caption Window)
# - Keyboard shortcuts for bubbles (display key)
# - Navigate with arrow keys: Left=back&restore, Right=Skip Unchanged
# - Keyboard shortcuts only effective when tab is active

# - Define which tags
# - Only show selected tags (only bubbles)
# - Use colors from groups/bans
# - Select boolean: Enter yes/no if tag should exist
# - Select one of many (+None)
# - Select multiple (forward image with ENTER)

# - Load from cache if it exists
# - Auto save to file and reset cache


class CaptionFocus(QtWidgets.QWidget):
    def __init__(self, container: CaptionContainer, context: CaptionContext):
        super().__init__()
        self.container = container
        self.ctx = context
        self.keyHandler = KeyEventFilter(self)

        self.separator = context.settings.separator
        self.bubbles: list[FocusBubble] = []

        self._build()
        self._updateAutoFeedPossible()

        context.separatorChanged.connect(self._onSeparatorChanged)
        context.controlUpdated.connect(self.updateBubbles)

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setHorizontalSpacing(12)
        layout.setColumnStretch(3, 1)

        row = 0
        self.txtFocusTags = QtWidgets.QLineEdit()
        qtlib.setMonospace(self.txtFocusTags)
        self.txtFocusTags.textChanged.connect(self.updateBubbles)
        layout.addWidget(QtWidgets.QLabel("Focus on:"), row, 0)
        layout.addWidget(self.txtFocusTags, row, 1, 1, 3)

        row += 1
        self.chkMutuallyExclusive = QtWidgets.QCheckBox("Mutually Exclusive")
        self.chkMutuallyExclusive.setChecked(False)
        self.chkMutuallyExclusive.toggled.connect(self._updateAutoFeedPossible)
        layout.addWidget(self.chkMutuallyExclusive, row, 1)

        self.chkAutoSave = QtWidgets.QCheckBox("Auto Save")
        self.chkAutoSave.setChecked(False)
        self.chkAutoSave.toggled.connect(self._updateAutoFeedPossible)
        layout.addWidget(self.chkAutoSave, row, 2)

        self.chkAutoFeed = QtWidgets.QCheckBox("Auto Feed")
        self.chkAutoFeed.setChecked(False)
        layout.addWidget(self.chkAutoFeed, row, 3)

        row += 1
        layout.setRowMinimumHeight(row, 12)

        row += 1
        layout.setRowStretch(row, 1)

        self.bubbleLayout = FlowLayout(spacing=12)
        bubbleWidget = QtWidgets.QWidget()
        bubbleWidget.setLayout(self.bubbleLayout)
        layout.addWidget(bubbleWidget, row, 0, 1, 4)

        row += 1
        layout.setRowMinimumHeight(row, 12)

        row += 1
        self.btnFocusEnable = FocusEnabledButton("Enable Keyboard Shortcuts")
        self.btnFocusEnable.installEventFilter(self.keyHandler)
        layout.addWidget(self.btnFocusEnable, row, 0, 1, 4)

        self.setLayout(layout)


    def setFocusTags(self, tags: list[str]):
        text = self.separator.join(tags)
        self.txtFocusTags.setText(text)


    @Slot()
    def _updateAutoFeedPossible(self):
        autoFeedPossible = self.chkMutuallyExclusive.isChecked() and self.chkAutoSave.isChecked()
        self.chkAutoFeed.setEnabled(autoFeedPossible)
        if self.chkAutoFeed.isChecked() and not autoFeedPossible:
            self.chkAutoFeed.setChecked(False)

    @Slot()
    def _onSeparatorChanged(self, separator: str):
        self.separator = separator
        self.updateBubbles()


    def updateSelectionState(self, captions: set[str]):
        for bubble in self.bubbles:
            if bubble.text in captions:
                bubble.setColor(bubble.groupColor)
            else:
                bubble.setColor("#161616")

    def _updateSelectionState(self):
        captions = self.container.getCaption().split(self.separator.strip())
        captionSet = { cap for c in captions if (cap := c.strip()) }
        self.updateSelectionState(captionSet)


    @Slot()
    def updateBubbles(self):
        self.bubbles.clear()
        self.bubbleLayout.clear()

        text = self.txtFocusTags.text()
        if not text:
            return

        colors = self.ctx.groups.getCaptionColors()

        for i, tag in enumerate(text.split(self.separator.strip())):
            tag = tag.strip()
            if not tag:
                continue

            shortcut = i+1 if i<9 else -1
            groupColor = colors.get(tag, "#161616")

            bubble = FocusBubble(tag, shortcut, groupColor)
            bubble.bubbleClicked.connect(self._onBubbleClicked)
            self.bubbleLayout.addWidget(bubble)
            self.bubbles.append(bubble)

        sep = qtlib.VerticalSeparator()
        sep.setMinimumHeight(26)
        self.bubbleLayout.addWidget(sep)
        bubble = FocusBubble("Remove All", 0, "#454545")
        bubble.setColor("#454545")
        bubble.bubbleClicked.connect(self.removeAllFocusTags)
        self.bubbleLayout.addWidget(bubble)

        self._updateSelectionState()


    @Slot()
    def _onBubbleClicked(self, tag: str):
        self.selectTag(tag, self.chkMutuallyExclusive.isChecked())

    def onNumberPressed(self, index: int):
        if index == 0 and self.bubbles:
            self.removeAllFocusTags()
        elif index-1 < len(self.bubbles):
            tag = self.bubbles[index - 1].text
            self.selectTag(tag, self.chkMutuallyExclusive.isChecked())

    @Slot()
    def removeAllFocusTags(self):
        self.selectTag(None, True)

    def selectTag(self, tag: str | None, exclusive: bool):
        tagsSet = {bubble.text for bubble in self.bubbles}

        captions = []
        exists = False
        text = self.container.getCaption()
        if text:
            for current in text.split(self.separator.strip()):
                current = current.strip()
                if tag == current: # This is always False when removing all tags (tag=None)
                    exists = True
                    captions.append(current)
                elif not exclusive or (current not in tagsSet):
                    captions.append(current)

        if tag and not exists:
            captions.append(tag)

        newText = self.separator.join(captions)
        if newText != text:
            self.container.setCaption(newText)

        # Always save, even when text is unchanged.
        # (text might actually be changed and loaded from cache)
        if self.chkAutoSave.isChecked():
            self.container.saveCaption()
            if self.chkAutoFeed.isChecked():
                self.nextFile()

    def nextFile(self):
        tab: ImgTab = self.ctx.tab
        try:
            tab.imgview.takeFocusOnFilechange = False
            tab.filelist.setNextFile()
        finally:
            tab.imgview.takeFocusOnFilechange = True

    def prevFile(self):
        tab: ImgTab = self.ctx.tab
        try:
            tab.imgview.takeFocusOnFilechange = False
            tab.filelist.setPrevFile()
        finally:
            tab.imgview.takeFocusOnFilechange = True



class FocusBubble(QtWidgets.QFrame):
    bubbleClicked = Signal(str)

    def __init__(self, text: str, shortcut: int, groupColor: str):
        super().__init__()
        self.groupColor = groupColor
        self.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QHBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        if shortcut >= 0:
            lblShortcut = QtWidgets.QLabel(f"[{shortcut}]")
            qtlib.setMonospace(lblShortcut, 1.0)
            layout.addWidget(lblShortcut)

        self.lblText = QtWidgets.QLabel(text)
        qtlib.setMonospace(self.lblText, 1.2)
        layout.addWidget(self.lblText)

        self.setLayout(layout)

        self.setColor("#161616")
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)


    @property
    def text(self):
        return self.lblText.text()

    def setColor(self, color: str):
        self.setStyleSheet(".FocusBubble{background-color: " + color + "; border: 1px solid #161616; border-radius: 8px}")
        self.lblText.setStyleSheet("color: #fff; background-color: " + color + "; border: 0px")


    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        self.bubbleClicked.emit(self.text)
        event.accept()



class FocusEnabledButton(qtlib.GreenButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)
        self.setMinimumHeight(40)
        self.toggled.connect(self._onStateChanged)

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        self.setChecked(False)
        super().focusOutEvent(event)

    def _onStateChanged(self, checked: bool):
        self.setChanged(checked)



class KeyEventFilter(QObject):
    def __init__(self, focus: CaptionFocus):
        super().__init__()
        self.focus = focus

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.focus.btnFocusEnable.isChecked():
            return False

        key: int = event.key()
        match key:
            case Qt.Key.Key_Escape:
                self.focus.btnFocusEnable.setChecked(False)
                return True
            case Qt.Key.Key_Return:
                self.focus.container.saveCaption()
                self.focus.nextFile()
                return True
            case Qt.Key.Key_Left:
                self.focus.prevFile()
                return True
            case Qt.Key.Key_Right:
                self.focus.nextFile()
                return True
            case Qt.Key.Key_Up | Qt.Key.Key_Down:
                return True

        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_0
            self.focus.onNumberPressed(index)
            return True
        return False
