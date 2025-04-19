from __future__ import annotations
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker, QTimer
from lib.util import stripCountPadding
from .caption_context import CaptionContext


class CaptionTextEdit(QtWidgets.QPlainTextEdit):
    captionReplaced = Signal()
    focusChanged = Signal()

    def __init__(self, context: CaptionContext):
        super().__init__()
        self.ctx = context

        self.separator = self.ctx.settings.separator
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)


    def getCaption(self) -> str:
        return self.toPlainText()

    def setCaption(self, text: str):
        self.captionReplaced.emit()
        self.setPlainText(text)
        self.moveCursor(QtGui.QTextCursor.MoveOperation.End)


    @Slot()
    def appendToCaption(self, text: str):
        caption = self.toPlainText()
        if caption:
            caption += self.separator
        caption += text

        self.setCaption(caption)
        self.ctx.needsRulesApplied.emit()

    def toggleCaption(self, caption: str, removeWords: set[str] | None):
        caption = caption.strip()
        captions = []
        removed = False

        text = self.toPlainText()
        if text:
            for current in text.split(self.separator.strip()):
                current = current.strip()
                if caption == current:
                    removed = True
                    continue

                elif removeWords:
                    currentWords = current.split(" ")
                    currentMatchSplit = self.ctx.highlight.matchNode.split(currentWords)
                    if caption in currentMatchSplit:
                        current = " ".join(word for word in currentWords if (word not in removeWords))
                        removed = True

                captions.append(current)

        if not removed:
            captions.append(caption)

        self.setCaption( self.separator.join(captions) )
        self.ctx.needsRulesApplied.emit()

    @Slot()
    def removeCaption(self, index: int):
        text = self.toPlainText()
        sepStrip = self.separator.strip()
        captions = (c.strip() for i, c in enumerate(text.split(sepStrip)) if i != index)
        self.setCaption( self.separator.join(captions) )


    def getSelectedCaption(self) -> str:
        text = self.toPlainText()
        cursorPos = self.textCursor().position()
        return self.getCaptionAtCharPos(text, self.separator, cursorPos)[0]

    def getSelectedCaptionIndex(self) -> int:
        text = self.toPlainText()
        cursorPos = self.textCursor().position()
        return self.getCaptionAtCharPos(text, self.separator, cursorPos)[1]

    @staticmethod
    def getCaptionAtCharPos(text: str, separator: str, charPos: int) -> tuple[str, int]:
        sepStrip = separator.strip()
        accumulatedLength = 0
        for i, caption in enumerate(text.split(sepStrip)):
            accumulatedLength += len(caption) + len(sepStrip)
            if charPos < accumulatedLength:
                return caption.strip(), i

        return "", -1


    @Slot()
    def selectCaption(self, index: int):
        self.setFocus()
        text = self.toPlainText()
        sepStrip, sepSpaceL, sepSpaceR = stripCountPadding(self.separator)

        splitCaptions = text.split(sepStrip)
        if index < 0 or index >= len(splitCaptions):
            return

        caption = splitCaptions[index]
        capStrip, capSpaceL, capSpaceR = stripCountPadding(caption)
        offsetL = min(capSpaceL, sepSpaceR) if index > 0 else 0
        offsetR = min(capSpaceR, sepSpaceL) if index < len(splitCaptions)-1 else 0

        start = end = sum( len(splitCaptions[i])+len(sepStrip) for i in range(index) )
        start += offsetL
        end   += len(caption) - offsetR

        cursor = self.textCursor()
        cursor.setPosition(end, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(start, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    @Slot()
    def moveCaptionSelection(self, offset: int, offsetLine: int):
        cursor = self.textCursor()
        if offsetLine != 0:
            moveLineDir = QtGui.QTextCursor.MoveOperation.Up if offsetLine < 0 else QtGui.QTextCursor.MoveOperation.Down
            cursor.movePosition(moveLineDir, QtGui.QTextCursor.MoveMode.MoveAnchor)

        index = self.getCaptionAtCharPos(self.toPlainText(), self.separator, cursor.position())[1]
        index = max(0, index+offset)
        self.selectCaption(index)

    @Slot()
    def removeSelectedCaption(self):
        cursor = self.textCursor()
        index = self.getCaptionAtCharPos(self.toPlainText(), self.separator, cursor.position())[1]
        self.removeCaption(index)

        # Set cursor to start of next caption
        self.selectCaption(index)
        cursor = self.textCursor()
        cursor.setPosition(cursor.selectionStart())
        self.setTextCursor(cursor)


    @Slot()
    def _onSeparatorChanged(self, separator: str):
        self.separator = separator


    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            move = None
            match event.key():
                case Qt.Key.Key_Alt:    move = (0, 0)
                case Qt.Key.Key_Left:   move = (-1, 0)
                case Qt.Key.Key_Right:  move = (1, 0)
                case Qt.Key.Key_Up:     move = (0, -1)
                case Qt.Key.Key_Down:   move = (0, 1)

                case Qt.Key.Key_Delete:
                    self.removeSelectedCaption()
                    move = (0, 0)

            if move is not None:
                event.accept()
                self.moveCaptionSelection(move[0], move[1])
                return

        super().keyPressEvent(event)


    def dropEvent(self, event: QtGui.QDropEvent):
        with QSignalBlocker(self):
            super().dropEvent(event)

        # Don't remove buttons from CaptionControlGroup
        event.setDropAction(Qt.DropAction.CopyAction)

        # Postpone updates when dropping so they don't interfere with ongoing drag operations in ReorderWidget.
        # But don't postpone normal updates to prevent flickering.
        QTimer.singleShot(0, self.textChanged.emit)


    def focusInEvent(self, event: QtGui.QFocusEvent):
        super().focusInEvent(event)
        self.focusChanged.emit()

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        super().focusOutEvent(event)
        self.focusChanged.emit()
