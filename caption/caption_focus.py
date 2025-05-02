from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QObject, QEvent, QTimer
import lib.qtlib as qtlib
from ui.flow_layout import FlowLayout
from .caption_tab import CaptionTab
from .caption_context import CaptionContext
from .caption_container import CaptionContainer


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


HELP = [
    "[1-9]: Select tag",
    "[0]: Unselect all tags",
    "[Enter]: Save and skip to next image",
    "[Arrow Left/Right]: Navigate to previous/next image",
    "[Esc]: Disable shortcuts"
]


class CaptionFocus(CaptionTab):
    def __init__(self, container: CaptionContainer, context: CaptionContext):
        super().__init__(context)
        self.setAcceptDrops(True)
        self._tabActive = False

        self.container = container
        self.keyHandler = KeyEventFilter(self)

        self.separator = context.settings.separator
        self.bubbles: list[FocusBubble] = []

        self._build()

        context.separatorChanged.connect(self._onSeparatorChanged)
        context.controlUpdated.connect(self.updateBubbles)

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setHorizontalSpacing(12)
        layout.setColumnStretch(2, 1)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Focus on:"), row, 0)

        self.txtFocusTags = QtWidgets.QLineEdit()
        qtlib.setMonospace(self.txtFocusTags)
        self.txtFocusTags.textChanged.connect(lambda: self.ctx.controlUpdated.emit())
        self.txtFocusTags.textChanged.connect(self.updateBubbles)
        layout.addWidget(self.txtFocusTags, row, 1, 1, 2)

        btnClear = QtWidgets.QPushButton("Clear")
        btnClear.clicked.connect(lambda: self.txtFocusTags.setText(""))
        layout.addWidget(btnClear, row, 3)

        row += 1
        self.chkMutuallyExclusive = QtWidgets.QCheckBox("Mutually Exclusive")
        self.chkMutuallyExclusive.setChecked(False)
        layout.addWidget(self.chkMutuallyExclusive, row, 1)

        self.chkAutoSave = QtWidgets.QCheckBox("Auto Save (and skip)")
        self.chkAutoSave.setChecked(False)
        layout.addWidget(self.chkAutoSave, row, 2)

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

        lblHelp = QtWidgets.QLabel("        ".join(HELP))
        lblHelp.setEnabled(False)
        layout.addWidget(lblHelp, row, 0, 1, 4, Qt.AlignmentFlag.AlignCenter)

        row += 1
        self.btnFocusEnable = FocusEnabledButton("Enable Keyboard Shortcuts")
        self.btnFocusEnable.installEventFilter(self.keyHandler)
        layout.addWidget(self.btnFocusEnable, row, 0, 1, 4)

        self.setLayout(layout)


    def onTabEnabled(self):
        self._tabActive = True
        self.ctx.controlUpdated.emit()

    def onTabDisabled(self):
        self._tabActive = False
        self.ctx.controlUpdated.emit()


    def getFocusSet(self) -> set[str]:
        if not self._tabActive:
            return set()
        return {tag for t in self.txtFocusTags.text().split(self.separator.strip()) if (tag := t.strip())}

    def setFocusTags(self, tags: list[str]):
        text = self.separator.join(tags)
        self.txtFocusTags.setText(text)

    def appendFocusTag(self, newTag: str):
        focusTags = [tag for t in self.txtFocusTags.text().split(self.separator.strip()) if (tag := t.strip())]
        if newTag not in focusTags:
            focusTags.append(newTag)
            text = self.separator.join(focusTags)
            self.txtFocusTags.setText(text)


    @Slot()
    def _onSeparatorChanged(self, separator: str):
        self.separator = separator
        self.updateBubbles()


    def updateSelectionState(self, captions: set[str]):
        for bubble in self.bubbles:
            exists = bubble.text in captions
            bubble.setColor(bubble.groupColor if exists else qtlib.COLOR_BUBBLE_BLACK)

    def _updateSelectionState(self):
        captions = self.ctx.text.getCaption().split(self.separator.strip())
        captionSet = { cap for c in captions if (cap := c.strip()) }
        self.updateSelectionState(captionSet)


    @Slot()
    def updateBubbles(self):
        self.bubbles.clear()
        self.bubbleLayout.clear()

        text = self.txtFocusTags.text()
        if not text:
            return

        colors = self.ctx.highlight.colors

        for i, tag in enumerate(text.split(self.separator.strip())):
            tag = tag.strip()
            if not tag:
                continue

            shortcut = i+1 if i<9 else -1
            groupColor = colors.get(tag, qtlib.COLOR_BUBBLE_BLACK)

            bubble = FocusBubble(tag, shortcut, groupColor)
            bubble.bubbleClicked.connect(self._onBubbleClicked)
            self.bubbleLayout.addWidget(bubble)
            self.bubbles.append(bubble)

        sep = qtlib.VerticalSeparator()
        sep.setMinimumHeight(26)
        self.bubbleLayout.addWidget(sep)
        bubble = FocusBubble("Unselect All", 0, qtlib.COLOR_BUBBLE_BAN)
        bubble.setColor(qtlib.COLOR_BUBBLE_BAN)
        bubble.bubbleClicked.connect(self.unselectAllTags)
        self.bubbleLayout.addWidget(bubble)

        self._updateSelectionState()


    @Slot()
    def _onBubbleClicked(self, tag: str):
        self.selectTag(tag, self.chkMutuallyExclusive.isChecked())

    def onNumberPressed(self, index: int):
        if index == 0 and self.bubbles:
            self.unselectAllTags()
        elif index-1 < len(self.bubbles):
            tag = self.bubbles[index - 1].text
            self.selectTag(tag, self.chkMutuallyExclusive.isChecked())

    @Slot()
    def unselectAllTags(self):
        self.selectTag(None, True)

    def selectTag(self, tag: str | None, exclusive: bool):
        tagsSet = {bubble.text for bubble in self.bubbles}

        captions = []
        exists = False
        text = self.ctx.text.getCaption()
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
            self.ctx.text.setCaption(newText)
            self.ctx.needsRulesApplied.emit()

        # Always save, even when text is unchanged.
        # (text might actually be changed and loaded from cache)
        if self.chkAutoSave.isChecked():
            self.container.saveCaption()


    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasText():
            event.accept()

    def dropEvent(self, event: QtGui.QDropEvent):
        text = event.mimeData().text()
        if text:
            QTimer.singleShot(0, lambda text=text: self.appendFocusTag(text))

        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()


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

        self.setColor(qtlib.COLOR_BUBBLE_BLACK)
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)


    @property
    def text(self):
        return self.lblText.text()

    def setColor(self, color: str):
        self.setStyleSheet(qtlib.bubbleClassAux("FocusBubble", "QLabel", color))


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

        filelist = self.focus.ctx.tab.filelist
        key: int = event.key()
        match key:
            case Qt.Key.Key_Escape:
                self.focus.btnFocusEnable.setChecked(False)
                return True
            case Qt.Key.Key_Return:
                # Don't loop
                if self.focus.container.saveCaptionNoSkip() and not filelist.isLastFile():
                    filelist.setNextFile()
                return True
            case Qt.Key.Key_Left:
                filelist.setPrevFile()
                return True
            case Qt.Key.Key_Right:
                filelist.setNextFile()
                return True
            case Qt.Key.Key_Up | Qt.Key.Key_Down:
                return True

        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            index = key - Qt.Key.Key_0
            self.focus.onNumberPressed(index)
            return True
        return False
