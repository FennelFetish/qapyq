from __future__ import annotations
from typing import Iterable, Generator, Generic, TypeVar, Optional
from itertools import zip_longest
from PySide6 import QtWidgets
from PySide6.QtCore import Slot
from PySide6.QtGui import QColor, QTextCursor, QTextCharFormat
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

    def getPresence(self) -> list[float] | None:
        return None

    def getTotalPresence(self, tags: list[str]) -> list[float] | None:
        return None

    def getFocusSet(self) -> set[str]:
        return set[str]()

    def getBanned(self) -> Iterable[str]:
        raise NotImplementedError()

    def getGroups(self) -> Iterable[CaptionGroupData]:
        raise NotImplementedError()


# Payload for MatcherNode
class CaptionFormat:
    def __init__(self, charFormat: QTextCharFormat, color: str):
        self.charFormat = charFormat
        self.color = color



class HighlightState:
    def __init__(self):
        self.lastCaptions: list[str] = list()
        self.lastPresence: list[float] = list()

    @Slot()
    def clearState(self):
        self.lastCaptions.clear()
        self.lastPresence.clear()

    def getAndUpdate(self, captions: list[str], presence: list[float] | None) -> list[bool]:
        if presence is None:
            presence = list()

        sameCaptions = [
            (presNew == presOld) and (capNew == capOld)
            for capNew, capOld, presNew, presOld in zip_longest(captions, self.lastCaptions, presence, self.lastPresence)
        ]

        self.lastCaptions = captions
        self.lastPresence = presence
        return sameCaptions



class CaptionHighlight:
    def __init__(self, dataSource: HighlightDataSource):
        self.data = dataSource
        self.data.connectClearCache(self.clearCache)

        self._cachedColors: dict[str, str] | None = None
        self._cachedCharFormats: dict[str, QTextCharFormat] | None = None
        self._cachedMatcherNode: MatcherNode[CaptionFormat] | None = None

        self._bannedFormat = QTextCharFormat()
        self._bannedFormat.setForeground(QColor.fromHsvF(0, 0, 0.5))

        self._focusFormat = QTextCharFormat()
        self._focusFormat.setForeground(qtlib.getHighlightColor(COLOR_FOCUS_DEFAULT))


    @property
    def colors(self) -> dict[str, str]:
        if not self._cachedColors:
            self.update()
        return self._cachedColors

    @property
    def charFormats(self) -> dict[str, QTextCharFormat]:
        if not self._cachedCharFormats:
            self.update()
        return self._cachedCharFormats

    @property
    def matchNode(self) -> MatcherNode[CaptionFormat]:
        if not self._cachedMatcherNode:
            self.updateMatcherNode()
        return self._cachedMatcherNode


    def highlight(self, text: str, separator: str, txtWidget: QtWidgets.QPlainTextEdit, state: HighlightState | None = None):
        separator = separator.strip()
        splitCaptions = text.split(separator)

        formats = self.charFormats
        matchNode = self.matchNode

        if state:
            presenceList = self.data.getPresence()
            sameCaptions = state.getAndUpdate(splitCaptions, presenceList)
        else:
            presenceList = self.data.getTotalPresence(splitCaptions)
            sameCaptions = None

        with HighlightContext(txtWidget) as HL:
            start = 0

            for i, caption in enumerate(splitCaptions):
                if sameCaptions and sameCaptions[i]:
                    start += len(caption) + len(separator)
                    continue

                presence = presenceList[i] if presenceList else 1.0
                captionStrip, padLeft, padRight = stripCountPadding(caption)

                # Format left padding including left separator
                sepStart = max(start - len(separator), 0)
                HL.highlight(HL.clearFormat, sepStart, start-sepStart+padLeft)
                start += padLeft

                if format := formats.get(captionStrip):
                    format = HL.checkPresence(format, presence)
                    HL.highlight(format, start, len(captionStrip))

                elif self.data.isHovered(captionStrip):
                    format = HL.checkPresence(HL.hoverFormat, presence)
                    HL.highlight(format, start, len(captionStrip))

                else:
                    # Try highlighting partial matches and combined tags
                    captionWords = captionStrip.split(" ")
                    if matcherFormats := matchNode.match(captionWords):
                        pos = start
                        for i, word in enumerate(captionWords):
                            if matchFormat := matcherFormats.get(i):
                                format = HL.checkPresence(matchFormat.charFormat, presence)
                            else:
                                format = HL.checkPresence(HL.clearFormat, presence)

                            # Format word
                            HL.highlight(format, pos, len(word))
                            pos += len(word)

                            # Format space
                            if i < len(captionWords) - 1:
                                HL.highlight(HL.clearFormat, pos, 1)
                                pos += 1

                    # No color specified
                    else:
                        format = HL.checkPresence(HL.clearFormat, presence)
                        HL.highlight(format, start, len(captionStrip))

                start += len(captionStrip)

                # Format right padding
                rightLen = min(padRight, len(text)-start)
                HL.highlight(HL.clearFormat, start, rightLen)

                start += padRight + len(separator)


    def update(self):
        colors: dict[str, str] = dict()
        formats: dict[str, QTextCharFormat] = dict()

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
        if focusSet:
            bannedColor, bannedFormat = self._getMuted(qtlib.COLOR_BUBBLE_BAN)
            bannedFocusColor, bannedFocusFormat = self._getMuted(COLOR_FOCUS_BAN, 1, 1)
        else:
            bannedColor = bannedFocusColor = qtlib.COLOR_BUBBLE_BAN
            bannedFormat = bannedFocusFormat = self._bannedFormat

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

        colors = self.colors
        formats = self.charFormats

        for group in self.data.getGroups():
            for caption in group.captions:
                payload = CaptionFormat(formats[caption], colors[caption])
                root.add(caption, payload)

        self._cachedMatcherNode = root


    @Slot()
    def clearCache(self):
        self._cachedColors = None
        self._cachedCharFormats = None
        self._cachedMatcherNode = None


    def _getMuted(self, color: str, mixS=0.22, mixV=0.3):
        mutedColor = colors.mixBubbleColor(color, mixS, mixV)
        mutedFormat = QTextCharFormat()
        mutedFormat.setForeground(qtlib.getHighlightColor(mutedColor))
        return mutedColor, mutedFormat

    def _getHovered(self, color: str):
        h, s, v = util.get_hsv(color)
        s = max(0.3, min(1.0, s*0.8))
        v = max(0.2, min(1.0, v*1.6))
        hoveredColor = util.hsv_to_rgb(h, s, v)

        hoveredFormat = QTextCharFormat()
        hoveredFormat.setForeground(qtlib.getHighlightColor(hoveredColor))
        hoveredFormat.setFontUnderline(True)

        return hoveredColor, hoveredFormat



class HighlightContext:
    def __init__(self, txtWidget: QtWidgets.QPlainTextEdit):
        self.txtWidget = txtWidget
        self.cursor = self.txtWidget.textCursor()
        self.partialPresenceColors: dict[tuple[int, int, int, bool], QTextCharFormat] = dict()

        textBrush = txtWidget.palette().text()

        self.clearFormat = QTextCharFormat()
        self.clearFormat.setForeground(textBrush)

        self.hoverFormat = QTextCharFormat()
        self.hoverFormat.setForeground(textBrush)
        self.hoverFormat.setFontUnderline(True)

    def __enter__(self):
        self.txtWidget.blockSignals(True)
        self.cursor.beginEditBlock()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.cursor.endEditBlock()
        self.txtWidget.blockSignals(False)
        return False


    def checkPresence(self, format: QTextCharFormat, presence: float) -> QTextCharFormat:
        if presence >= 1.0:
            return format

        color = format.foreground().color()
        key = (color.red(), color.green(), color.blue(), format.fontUnderline())

        mutedFormat = self.partialPresenceColors.get(key)
        if not mutedFormat:
            color.setAlphaF(0.5)
            mutedFormat = QTextCharFormat(format)
            mutedFormat.setForeground(color)
            self.partialPresenceColors[key] = mutedFormat

        return mutedFormat

    def highlight(self, format: QTextCharFormat, start: int, length: int):
        if length <= 0:
            return

        self.cursor.setPosition(start)
        self.cursor.setPosition(start+length, QTextCursor.MoveMode.KeepAnchor)
        self.cursor.setCharFormat(format)



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

    def splitAll(self, captions: Iterable[str]) -> Generator[str]:
        for cap in captions:
            if matchSplit := self.split(cap.split(" ")):
                yield from matchSplit
            else:
                yield cap

    def splitAllPreserveExtra(self, captions: Iterable[str]) -> Generator[str]:
        'Splits captions but only if no extra words are present. No subsets.'

        splitCaptionWords = list[list[str]]()
        usedWords = set[str]()

        for cap in captions:
            captionWords = cap.split(" ")

            if matchSplitWords := self.splitWords(captionWords):
                splitCaptionWords.clear()
                usedWords.clear()

                # Don't split into subsets: Start with longest and only add captions if they have new words.
                matchSplitWords.sort(key=len, reverse=True)
                for matchWords in matchSplitWords:
                    if not usedWords.issuperset(matchWords):
                        usedWords.update(matchWords)
                        splitCaptionWords.append(matchWords)

                # Only use the split captions if all words are allowed to be combined (no extra words).
                if usedWords.issuperset(word for word in captionWords if word):
                    yield from (" ".join(matchWords) for matchWords in splitCaptionWords)
                    continue

            # Preserve original caption if extra words are present.
            yield cap
