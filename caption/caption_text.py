from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QSignalBlocker, QTimer
from lib.util import stripCountPadding


class NavigationTextEdit(QtWidgets.QPlainTextEdit):
    def __init__(self, separator: str):
        super().__init__()
        #self.setTabChangesFocus(True)
        self.separator = separator

    def getCaption(self) -> str:
        return self.toPlainText()

    def setCaption(self, text: str):
        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(cursor.MoveOperation.Start, cursor.MoveMode.MoveAnchor)
        cursor.movePosition(cursor.MoveOperation.End, cursor.MoveMode.KeepAnchor)
        cursor.insertText(text)

        # Further text input is merged with this edit block. Ctrl+Z would remove the typed text, plus this inserted text.
        # Add and delete a space char to avoid merging the commands in the undo stack.
        cursor.insertText(" ")
        cursor.deletePreviousChar()
        cursor.endEditBlock()


    def appendToCaption(self, text: str):
        caption = self.toPlainText()
        if caption:
            caption += self.separator
        caption += text

        self.setCaption(caption)

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



class CaptionTextEdit(NavigationTextEdit):
    LINE_COLOR = "#B0FF1616"
    LINE_WIDTH = 2.0

    captionReplaced = Signal()
    focusChanged = Signal()

    def __init__(self, context: 'CaptionContext'):
        super().__init__(context.settings.separator)
        from .caption_context import CaptionContext
        self.ctx: CaptionContext = context
        self.ctx.separatorChanged.connect(self._onSeparatorChanged)

        self._verticalLinePos: list[int] | None = None
        self._penLine = QtGui.QPen(self.LINE_COLOR)
        self._penLine.setWidthF(self.LINE_WIDTH)

        # When a character is removed by typing, it will repaint this widget with the shorter text before new line indexes arrive.
        # Clear the lines because their indexes could be out of bounds.
        self.textChanged.connect(self._clearVerticalLines)


    def setCaption(self, text: str):
        self.captionReplaced.emit()
        self._verticalLinePos = None
        super().setCaption(text)


    @Slot()
    def appendToCaption(self, text: str):
        super().appendToCaption(text)
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
    def _onSeparatorChanged(self, separator: str):
        self.separator = separator


    def focusInEvent(self, event: QtGui.QFocusEvent):
        super().focusInEvent(event)
        self.focusChanged.emit()

    def focusOutEvent(self, event: QtGui.QFocusEvent):
        super().focusOutEvent(event)
        self.focusChanged.emit()


    def setVerticalLines(self, linePos: list[int] | None):
        self._verticalLinePos = linePos
        self.viewport().update()

    @Slot()
    def _clearVerticalLines(self):
        self._verticalLinePos = None


    def paintEvent(self, e: QtGui.QPaintEvent):
        if self._verticalLinePos:
            painter = QtGui.QPainter(self.viewport())
            painter.setPen(self._penLine)
            cursor = self.textCursor()

            for pos in self._verticalLinePos:
                cursor.setPosition(pos)
                rect = self.cursorRect(cursor)
                x  = rect.x() + 1
                y0 = rect.y() + 2
                y1 = rect.y() + rect.height() - 2
                painter.drawLine(x, y0, x, y1)

        # Call parent method last: Text cursor must be drawn on top of lines.
        super().paintEvent(e)
