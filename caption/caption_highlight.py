from __future__ import annotations
from typing import Iterable, Generic, TypeVar, Optional
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Slot, QSignalBlocker
from lib import qtlib, util, colors
from lib.util import stripCountPadding


COLOR_FOCUS_DEFAULT = "#901313"
COLOR_FOCUS_BAN     = "#686868"


# Adapters for data access
class CaptionGroupData:
    def __init__(self, captions: list[str], charFormat, color):
        self.captions = captions
        self.charFormat = charFormat
        self.color = color


class HighlightDataSource:
    def __init__(self):
        pass

    def connectClearCache(self, slot: Slot):
        raise NotImplementedError()

    def isHovered(self, caption: str) -> bool:
        return False

    def getFocusSet(self) -> set[str]:
        return set[str]()

    def getBanned(self) -> Iterable[str]:
        raise NotImplementedError()

    def getGroups(self) -> Iterable[CaptionGroupData]:
        raise NotImplementedError()


# Payload for MatcherNode
class CaptionFormat:
    def __init__(self, charFormat: QtGui.QTextCharFormat, color: str):
        self.charFormat = charFormat
        self.color = color



class CaptionHighlight:
    def __init__(self, dataSource: HighlightDataSource):
        self.data = dataSource
        self.data.connectClearCache(self.clearCache)

        self._cachedColors: dict[str, str] | None = None
        self._cachedCharFormats: dict[str, QtGui.QTextCharFormat] | None = None
        self._cachedMatcherNode: MatcherNode[CaptionFormat] | None = None

        self._bannedFormat = QtGui.QTextCharFormat()
        self._bannedFormat.setForeground(QtGui.QColor.fromHsvF(0, 0, 0.5))

        self._focusFormat = QtGui.QTextCharFormat()
        self._focusFormat.setForeground(qtlib.getHighlightColor(COLOR_FOCUS_DEFAULT))

        self._hoverFormat = QtGui.QTextCharFormat()
        self._hoverFormat.setFontUnderline(True)


    @property
    def colors(self) -> dict[str, str]:
        if not self._cachedColors:
            self.update()
        return self._cachedColors

    @property
    def charFormats(self) -> dict[str, QtGui.QTextCharFormat]:
        if not self._cachedCharFormats:
            self.update()
        return self._cachedCharFormats

    @property
    def matchNode(self) -> MatcherNode[CaptionFormat]:
        if not self._cachedMatcherNode:
            self.updateMatcherNode()
        return self._cachedMatcherNode


    def highlight(self, text: str, separator: str, txtWidget: QtWidgets.QPlainTextEdit):
        separator = separator.strip()

        formats = self.charFormats
        matchNode = self.matchNode

        with QSignalBlocker(txtWidget):
            cursor = txtWidget.textCursor()
            cursor.setPosition(0)
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())

            start = 0

            for caption in text.split(separator):
                captionStrip, padLeft, padRight = stripCountPadding(caption)
                start += padLeft

                if format := formats.get(captionStrip):
                    self._highlightPart(cursor, format, start, len(captionStrip))
                elif self.data.isHovered(captionStrip):
                    self._highlightPart(cursor, self._hoverFormat, start, len(captionStrip))
                else:
                    # Try highlighting partial matches and combined tags
                    captionWords = captionStrip.split(" ")
                    if matcherFormats := matchNode.match(captionWords):
                        pos = start
                        for i, word in enumerate(captionWords):
                            if format := matcherFormats.get(i):
                                self._highlightPart(cursor, format.charFormat, pos, len(word))
                            pos += len(word) + 1

                start += len(captionStrip) + padRight + len(separator)

    def _highlightPart(self, cursor: QtGui.QTextCursor, format: QtGui.QTextCharFormat, start: int, length: int):
        cursor.setPosition(start)
        cursor.setPosition(start+length, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format)


    def update(self):
        colors: dict[str, str] = dict()
        formats: dict[str, QtGui.QTextCharFormat] = dict()

        # First insert all focus tags. This is the default color if focus tags don't belong to groups.
        focusSet = self.data.getFocusSet()
        for focusTag in focusSet:
            colors[focusTag] = COLOR_FOCUS_DEFAULT
            formats[focusTag] = self._focusFormat

        # Insert group colors
        for group in self.data.getGroups():
            mutedColor, mutedFormat = self._getMuted(group.color) if focusSet else (group.color, group.charFormat)

            for caption in group.captions:
                if caption in focusSet:
                    colors[caption]  = group.color
                    formats[caption] = group.charFormat
                else:
                    colors[caption]  = mutedColor
                    formats[caption] = mutedFormat

        # Insert banned color. This will overwrite group colors.
        bannedColor, bannedFormat = self._getMuted(qtlib.COLOR_BUBBLE_BAN) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self._bannedFormat)
        bannedFocusColor, bannedFocusFormat = self._getMuted(COLOR_FOCUS_BAN, 1, 1) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self._bannedFormat)
        for banned in self.data.getBanned():
            if banned in focusSet:
                colors[banned]  = bannedFocusColor
                formats[banned] = bannedFocusFormat
            else:
                colors[banned]  = bannedColor
                formats[banned] = bannedFormat

        # Hover color
        for caption, color in colors.items():
            if self.data.isHovered(caption):
                colors[caption], formats[caption] = self._getHovered(color)

        self._cachedColors = colors
        self._cachedCharFormats = formats


    def updateMatcherNode(self):
        root = MatcherNode()

        for group in self.data.getGroups():
            payload = CaptionFormat(group.charFormat, group.color)
            for caption in group.captions:
                root.add(caption, payload)

        self._cachedMatcherNode = root


    @Slot()
    def clearCache(self):
        self._cachedColors = None
        self._cachedCharFormats = None
        self._cachedMatcherNode = None


    def _getMuted(self, color: str, mixS=0.22, mixV=0.3):
        mutedColor = colors.mixBubbleColor(color, mixS, mixV)
        mutedFormat = QtGui.QTextCharFormat()
        mutedFormat.setForeground(qtlib.getHighlightColor(mutedColor))
        return mutedColor, mutedFormat

    def _getHovered(self, color: str):
        h, s, v = util.get_hsv(color)
        s = max(0.3, min(1.0, s*0.8))
        v = max(0.2, min(1.0, v*1.6))
        hoveredColor = util.hsv_to_rgb(h, s, v)

        hoveredFormat = QtGui.QTextCharFormat()
        hoveredFormat.setForeground(qtlib.getHighlightColor(hoveredColor))
        hoveredFormat.setFontUnderline(True)

        return hoveredColor, hoveredFormat



TPayload = TypeVar("TPayload")

class MatcherNode(Generic[TPayload]):
    'Matches and splits captions into components as defined in Caption Groups.'

    def __init__(self, name: str = ""):
        self.name = name
        self.children = dict[str, MatcherNode]()

        # The presence of a payload marks end nodes:
        # These are starting words. A match is completed upon reaching them.
        # End nodes can have children.
        self.payload: Optional[TPayload] = None

    def __setitem__(self, key: str, node: MatcherNode):
        self.children[key] = node

    def __getitem__(self, key: str) -> MatcherNode:
        node = self.children.get(key)
        if node is None:
            self.children[key] = node = MatcherNode(key)
        return node

    def addWords(self, words: list[str], payload: TPayload):
        node = self
        for word in reversed(words):
            if word:
                node = node[word]
        node.payload = payload

    def add(self, text: str, payload: TPayload):
        self.addWords(text.split(" "), payload)


    def __str__(self) -> str:
        return f"Node[{self.name}]"

    def printTree(self, level: int = 0):
        indent = "  " * level
        for k, v in self.children.items():
            print(f"{indent}{k}:")
            v.printTree(level+1)


    class MatcherStackEntry:
        def __init__(self, node: MatcherNode, index: int):
            self.node = node
            self.index = index

    def match(self, words: list[str]) -> dict[int, TPayload]:
        node = self
        stack = list[self.MatcherStackEntry]()
        payloads = dict[int, TPayload]()

        def checkMatch(node: MatcherNode, child: MatcherNode, index: int, override=False) -> MatcherNode:
            if child.payload is not None:
                for entry in stack:
                    if override or (entry.index not in payloads):
                        payloads[entry.index] = child.payload
                payloads[index] = child.payload

            if child.children:
                stack.append(self.MatcherStackEntry(child, index))
                return child
            return node

        for i in range(len(words)-1, -1, -1):
            word = words[i]
            if not word:
                continue

            if child := node.children.get(word):
                node = checkMatch(node, child, i, True)

            # Search for a different transition by unwinding stack
            elif len(stack) > 1 and (child := stack[-2].node.children.get(word)):
                stack.pop()
                node = checkMatch(stack[-1].node, child, i)

        return payloads


    def splitWords(self, words: list[str]) -> list[list[str]]:
        node = self
        stack = list[MatcherNode]()
        groups = list[list[str]]()

        def checkMatch(node: MatcherNode, child: MatcherNode) -> MatcherNode:
            if child.payload is not None:
                group = [n.name for n in stack]
                group.append(child.name)
                group.reverse()
                groups.append(group)

            if child.children:
                stack.append(child)
                return child
            return node

        for word in reversed(words):
            if not word:
                continue

            if child := node.children.get(word):
                node = checkMatch(node, child)

            # Search for a different transition by unwinding stack
            elif len(stack) > 1 and (child := stack[-2].children.get(word)):
                stack.pop()
                node = checkMatch(stack[-1], child)

        return groups

    def split(self, words: list[str]) -> list[str]:
        groups = self.splitWords(words)
        return [" ".join(groupWords) for groupWords in groups]

    def matchSplitCaptions(self, captions: Iterable[str]) -> set[str]:
        captionSet = set[str]()
        for cap in captions:
            if matchSplit := self.split(cap.split(" ")):
                captionSet.update(matchSplit)
            else:
                captionSet.add(cap)

        return captionSet
