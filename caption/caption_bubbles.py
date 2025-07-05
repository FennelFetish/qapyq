from __future__ import annotations
from typing import NamedTuple
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot
import lib.qtlib as qtlib
import lib.util as util
from ui.flow_layout import FlowLayout, ReorderWidget
from .caption_context import CaptionContext

# TODO: Nested bubbles for expressions like: (blue (starry:0.8) sky:1.2)


class CaptionBubbles(ReorderWidget):
    remove = Signal(int)
    dropped = Signal(str)
    clicked = Signal(int)
    ctrlClicked = Signal(int)
    doubleClicked = Signal(int)
    hovered = Signal(int)  # -1 as argument when unhovered

    def __init__(self, context: CaptionContext, showWeights=True, showRemove=False, editable=True):
        super().__init__()
        self.dataCallback = lambda widget: widget.text
        self.receivedDrop.connect(self._onDrop)
        self.dragStartMinDistance = 6

        self.ctx = context

        self.text = ""
        self.separator = ','
        self.showWeights = showWeights
        self.showRemove = showRemove
        self.editable = editable

        layout = FlowLayout(spacing=5)
        self.setLayout(layout)
        self.updateBubbles()


    def setText(self, text):
        self.text = text
        self.updateBubbles()

    def getCaptions(self) -> list[str]:
        return [bubble.text for bubble in self.getBubbles()]

    def getBubbles(self):
        layout: QtWidgets.QLayout = self.layout()
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if (widget := item.widget()) and isinstance(widget, Bubble): # Why is there other stuff in there? -> It's the ReorderWidget's drag target
                yield widget

    def getBubbleAt(self, index: int) -> Bubble | None:
        layout: FlowLayout = self.layout()
        item = layout.itemAt(index)
        if item and (bubble := item.widget()) and isinstance(bubble, Bubble):
            return bubble
        return None

    def updateBubbles(self):
        oldBubbles = list[Bubble](self.getBubbles())
        colorMap = BubbleColorMap(self.ctx)

        i = -1
        for i, caption in enumerate(self.text.split(self.separator)):
            caption = caption.strip()

            if i < len(oldBubbles):
                bubble = oldBubbles[i]
                bubble.index = i
            else:
                bubble = Bubble(self, i, self.showWeights, self.showRemove, self.editable)
                bubble.setFocusProxy(self)
                self.layout().addWidget(bubble)

            bubble.text = caption
            bubble.setColor( colorMap.getBubbleColor(i, caption) )
            bubble.forceUpdateWidth()

        for i in range(i+1, len(oldBubbles)):
            oldBubbles[i].deleteLater()


    def moveBubble(self, srcIndex: int, destIndex: int) -> int:
        if srcIndex < destIndex:
            destIndex -= 1

        if bubble := self.getBubbleAt(srcIndex):
            layout: FlowLayout = self.layout()
            layout.insertWidget(destIndex, bubble)
            self.orderChanged.emit()
            return destIndex

        return -1

    def showBubbleMenu(self, index: int):
        if not self.ctx.tab.filelist.selectedFiles:
            return

        bubble = self.getBubbleAt(index)
        if not bubble:
            return

        # Select tag to highlight images
        self.clicked.emit(index)

        menu = BubbleMenu(bubble, self.ctx)
        menu.exec( bubble.mapToGlobal(bubble.rect().bottomLeft()) )


    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.

    @Slot()
    def _onDrop(self, text: str):
        self.dropped.emit(text)



class BubbleColor(NamedTuple):
    bg: str     = qtlib.COLOR_BUBBLE_BLACK
    border: str = qtlib.COLOR_BUBBLE_BLACK
    text: str   = "#fff"


class Bubble(QtWidgets.QFrame):
    def __init__(self, bubbles: CaptionBubbles, index, showWeights=True, showRemove=False, editable=True):
        super().__init__()

        self.bubbles = bubbles
        self.index = index
        self._text = ""
        self.colors = BubbleColor("", "", "")
        self.weight = 1.0

        if editable:
            self.textField = qtlib.DynamicLineEdit()
        else:
            self.textField = qtlib.EllipsisLabel(80)
            self.textField.setContentsMargins(0, 0, 4, 0)
        qtlib.setMonospace(self.textField)

        self.setContentsMargins(4, 1, 4, 1)
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.textField)

        if showWeights:
            self.spinWeight = QtWidgets.QDoubleSpinBox()
            self.spinWeight.setRange(-10.0, 10.0)
            self.spinWeight.setValue(1.0)
            self.spinWeight.setSingleStep(0.05)
            self.spinWeight.setFixedWidth(55)
            layout.addWidget(self.spinWeight)
        else:
            self.spinWeight = None

        if showRemove:
            btnRemove = qtlib.BubbleRemoveButton()
            btnRemove.setFocusProxy(self)
            btnRemove.clicked.connect(lambda: self.bubbles.remove.emit(self.index))
            layout.addWidget(btnRemove)

        self.setLayout(layout)

        self.setColor(BubbleColor())
        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)


    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, text):
        self._text = text
        self.textField.setText(text)


    def setColor(self, colors: BubbleColor):
        if colors == self.colors:
            return
        self.colors = colors

        # TODO: Display presence (with border height? full height with top border -> full presence)
        self.setStyleSheet(qtlib.bubbleClassAux("Bubble", "EllipsisLabel", colors.bg, colors.border, colors.text))

        if self.spinWeight:
            #self.spinWeight.setStyleSheet(".QDoubleSpinBox{background-color: " + color + "; border: 0; padding-right: 25px}")
            self.spinWeight.lineEdit().setStyleSheet("color: #fff; background-color: " + colors.bg)

    def forceUpdateWidth(self):
        if isinstance(self.textField, qtlib.DynamicLineEdit):
            self.textField.updateWidth()

    def wheelEvent(self, event: QtGui.QWheelEvent):
        if self.spinWeight:
            self.spinWeight.wheelEvent(event)
            self.spinWeight.lineEdit().setCursorPosition(0) # Clear text selection
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        match event.button():
            case Qt.MouseButton.LeftButton:
                if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    self.bubbles.ctrlClicked.emit(self.index)
                else:
                    self.bubbles.clicked.emit(self.index)

                event.accept()
                return

            case Qt.MouseButton.RightButton:
                self.bubbles.showBubbleMenu(self.index)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            self.bubbles.doubleClicked.emit(self.index)

    def enterEvent(self, event):
        self.bubbles.hovered.emit(self.index)

    def leaveEvent(self, event):
        self.bubbles.hovered.emit(-1)



class BubbleColorMap:
    def __init__(self, context: CaptionContext):
        self.ctx = context
        self.highlight = context.highlight
        self.presence = context.container.multiEdit.getTagPresence()
        self.mutedColors: dict[str, str] = dict()

    def getBubbleColor(self, index: int, caption: str) -> BubbleColor:
        bg = self._getBubbleColor(caption)
        if bg is None:
            bg = qtlib.COLOR_BUBBLE_HOVER if self.ctx.container.isHovered(caption) else qtlib.COLOR_BUBBLE_BLACK

        if not self.presence:
            return BubbleColor(bg)

        mutedColor = self.getMutedColor(bg)
        if self.presence[index] == 1.0:
            return BubbleColor(bg, border=mutedColor)
        else:
            return BubbleColor(bg, text=mutedColor)

    def _getBubbleColor(self, caption: str) -> str | None:
        if color := self.highlight.colors.get(caption):
            return color

        captionWords = [word for word in caption.split(" ") if word]
        matchFormats = self.highlight.matchNode.match(captionWords)
        if len(matchFormats) != len(captionWords):
            return None

        colors = set(format.color for format in matchFormats.values())
        return next(iter(colors)) if len(colors) == 1 else None

    def getMutedColor(self, color: str) -> str:
        mutedColor = self.mutedColors.get(color)
        if mutedColor is None:
            h, s, v = util.get_hsv(color)
            v = min(v*1.8, 1.0)
            v = max(v, 0.7)
            self.mutedColors[color] = mutedColor = util.hsv_to_rgb(h, s*0.7, v)

        return mutedColor



class BubbleMenu(QtWidgets.QMenu):
    def __init__(self, bubble: Bubble, ctx: CaptionContext):
        super().__init__("Bubble Menu")
        self.bubble = bubble
        self.ctx = ctx

        multiEdit = self.ctx.container.multiEdit
        if not multiEdit.active:
            return

        self.tagFiles = multiEdit.getTagFiles(self.bubble.index)
        if not self.tagFiles:
            return

        self._build()

    def _build(self):
        numWithout = len(self.ctx.tab.filelist.selectedFiles) - len(self.tagFiles)
        enabled = numWithout > 0

        actSelect = self.addAction("Select Files with Tag")
        actSelect.setEnabled(enabled)
        actSelect.triggered.connect(self._selectFilesWith)

        actSelectOthers = self.addAction("Select Files without Tag")
        actSelectOthers.setEnabled(enabled)
        actSelectOthers.triggered.connect(self._selectFilesWithout)

    @Slot()
    def _selectFilesWith(self):
        self.ctx.tab.filelist.setSelection(self.tagFiles, updateCurrent=True)

    @Slot()
    def _selectFilesWithout(self):
        filelist = self.ctx.tab.filelist
        files = filelist.selectedFiles.difference(self.tagFiles)
        filelist.setSelection(files, updateCurrent=True)
