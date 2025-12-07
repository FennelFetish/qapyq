import math
from typing import NamedTuple
from PySide6 import QtGui
from PySide6.QtCore import Qt, QPointF
from lib.captionfile import FileTypeSelector
from lib.util import CaptionSplitter
from caption.caption_highlight import CaptionHighlight, MatcherNode
from caption.caption_filter import CaptionRulesProcessor, CaptionRulesSettings


class LayoutInfo(NamedTuple):
    height: int
    layouts: tuple[QtGui.QTextLayout, ...]

    @staticmethod
    def create(height: float, layouts: list[QtGui.QTextLayout]) -> 'LayoutInfo':
        return LayoutInfo(math.ceil(height), tuple(layouts))



class GalleryCaption:
    def __init__(self, captionSrc: FileTypeSelector):
        self.captionSrc = captionSrc
        self.captionsEnabled: bool = False

        self.captionHighlight: CaptionHighlight | None = None
        self.filterNode: MatcherNode[bool] | None = None
        self.splitter = CaptionSplitter()
        self.separator = ", "

        self.rulesProcessor: CaptionRulesProcessor | None = None
        self.rulesSettings = CaptionRulesSettings()
        self.rulesSettings.prefixSuffix = False

        self.textOpt = QtGui.QTextOption()
        self.textOpt.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.textOpt.setWrapMode(QtGui.QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)


    def loadCaption(self, file: str) -> str:
        caption = self.captionSrc.loadCaption(file)
        if caption is None:
            return ""

        if self.filterNode:
            tags = self.splitter.split(caption)
            caption = self.separator.join(
                tag for tag in tags
                if self.filterNode.match(tag.split(" "))
            )

        if self.rulesProcessor:
            caption = self.rulesProcessor.process(caption, self.rulesSettings)

        return caption


    def layoutCaption(self, text: str, width: int, maxHeight: int) -> LayoutInfo:
        if not text:
            return LayoutInfo(0, ())

        layouts = list[QtGui.QTextLayout]()
        totalHeight = 0.0

        lines = [line for l in text.splitlines() if (line := l.strip())]
        for lineNr, lineText in enumerate(lines, 1):
            textLayout = QtGui.QTextLayout(lineText)
            textLayout.setCacheEnabled(True)
            textLayout.setTextOption(self.textOpt)
            layouts.append(textLayout)

            if self.captionHighlight:
                self.captionHighlight.highlightTextLayout(lineText, self.separator, textLayout)

            textLayout.beginLayout()
            while (line := textLayout.createLine()).isValid():
                line.setLineWidth(width)
                line.setPosition(QPointF(0, totalHeight))

                lineHeight = line.height()
                totalHeight += lineHeight
                if totalHeight + lineHeight >= maxHeight:
                    textLayout.endLayout()

                    # Check if last line
                    if lineNr >= len(lines) and line.textStart() + line.textLength() >= len(lineText):
                        return LayoutInfo.create(totalHeight, layouts)
                    else:
                        return self._addEllipsis(width, totalHeight, layouts)

            textLayout.endLayout()

        return LayoutInfo.create(totalHeight, layouts)

    def _addEllipsis(self, w: int, h: float, layouts: list[QtGui.QTextLayout]) -> LayoutInfo:
        textLayout = QtGui.QTextLayout("…")
        textLayout.setCacheEnabled(True)
        textLayout.setTextOption(self.textOpt)

        textLayout.beginLayout()
        line = textLayout.createLine()
        line.setLineWidth(w)

        lineHeight = line.height()
        h -= lineHeight * 0.4
        line.setPosition(QPointF(0, h))
        h += lineHeight

        textLayout.endLayout()
        layouts.append(textLayout)
        return LayoutInfo.create(h, layouts)
