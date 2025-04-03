from __future__ import annotations
from typing import Iterable
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Slot, QSignalBlocker
from lib import qtlib, util, colors
from lib.util import stripCountPadding


COLOR_FOCUS_DEFAULT = "#901313"
COLOR_FOCUS_BAN     = "#686868"


class CaptionHighlight:
    def __init__(self, context):
        from .caption_container import CaptionContext
        self.ctx: CaptionContext = context
        self.ctx.controlUpdated.connect(self.clearCache)

        self._cachedColors: dict[str, str] | None = None
        self._cachedCharFormats: dict[str, QtGui.QTextCharFormat] | None = None
        self._cachedMatcherNode: MatcherNode | None = None

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
    def matchNode(self) -> MatcherNode:
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
                elif self.ctx.container.isHovered(captionStrip):
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
        focusSet = self.ctx.focus.getFocusSet()
        for focusTag in focusSet:
            colors[focusTag] = COLOR_FOCUS_DEFAULT
            formats[focusTag] = self._focusFormat

        # Insert group colors
        for group in self.ctx.groups.groups:
            mutedColor, mutedFormat = self._getMuted(group.color) if focusSet else (group.color, group.charFormat)

            for caption in group.captionsExpandWildcards:
                if caption in focusSet:
                    colors[caption]  = group.color
                    formats[caption] = group.charFormat
                else:
                    colors[caption]  = mutedColor
                    formats[caption] = mutedFormat

        # Insert banned color. This will overwrite group colors.
        bannedColor, bannedFormat = self._getMuted(qtlib.COLOR_BUBBLE_BAN) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self._bannedFormat)
        bannedFocusColor, bannedFocusFormat = self._getMuted(COLOR_FOCUS_BAN, 1, 1) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self._bannedFormat)
        for banned in self.ctx.settings.bannedCaptions:
            if banned in focusSet:
                colors[banned]  = bannedFocusColor
                formats[banned] = bannedFocusFormat
            else:
                colors[banned]  = bannedColor
                formats[banned] = bannedFormat

        # Hover color
        for caption, color in colors.items():
            if self.ctx.container.isHovered(caption):
                colors[caption], formats[caption] = self._getHovered(color)

        self._cachedColors = colors
        self._cachedCharFormats = formats


    def updateMatcherNode(self):
        root = MatcherNode("")

        for group in self.ctx.groups.groups:
            groupFormat = group.charFormat
            groupColor = group.color
            for caption in group.captionsExpandWildcards:
                root.add(caption.split(" "), groupFormat, groupColor)

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



class MatcherNode:
    class Format:
        def __init__(self, charFormat: QtGui.QTextCharFormat, color: str):
            self.charFormat = charFormat
            self.color = color


    def __init__(self, name: str):
        self.name = name
        self.children = dict[str, MatcherNode]()
        self.format: MatcherNode.Format | None = None  # The presence of 'self.format' marks leaf nodes.

    def __setitem__(self, key: str, node: MatcherNode):
        self.children[key] = node

    def __getitem__(self, key: str) -> MatcherNode:
        node = self.children.get(key)
        if node is None:
            self.children[key] = node = MatcherNode(key)
        return node

    def add(self, words: list[str], charFormat: QtGui.QTextCharFormat, color: str):
        node = self
        for word in reversed(words):
            if word:
                node = node[word]
        node.format = MatcherNode.Format(charFormat, color)


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

    def match(self, words: list[str]) -> dict[int, MatcherNode.Format]:
        node = self
        stack = list[self.MatcherStackEntry]()
        formats = dict[int, MatcherNode.Format]()

        def handleLeaf(node: MatcherNode, child: MatcherNode, index: int, override=False) -> MatcherNode:
            if child.format:
                for entry in stack:
                    if override or (entry.index not in formats):
                        formats[entry.index] = child.format
                formats[index] = child.format

            if child.children:
                stack.append(self.MatcherStackEntry(child, index))
                return child
            return node


        for i in range(len(words)-1, -1, -1):
            word = words[i]
            if not word:
                continue

            if child := node.children.get(word):
                node = handleLeaf(node, child, i, True)

            # Search for a different transition by unwinding stack
            elif len(stack) > 1 and (child := stack[-2].node.children.get(word)):
                stack.pop()
                node = handleLeaf(stack[-1].node, child, i)

        return formats


    def splitWords(self, words: list[str]) -> list[list[str]]:
        node = self
        stack = list[MatcherNode]()
        groups = list[list[str]]()

        def handleLeaf(node: MatcherNode, child: MatcherNode) -> MatcherNode:
            if child.format:
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
                node = handleLeaf(node, child)

            # Search for a different transition by unwinding stack
            elif len(stack) > 1 and (child := stack[-2].children.get(word)):
                stack.pop()
                node = handleLeaf(stack[-1], child)

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
