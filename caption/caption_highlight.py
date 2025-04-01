from __future__ import annotations
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
        self._cachedCombineFormats: dict[str, CombineFormat] | None = None

        self._bannedFormat = QtGui.QTextCharFormat()
        self._bannedFormat.setForeground(QtGui.QColor.fromHsvF(0, 0, 0.5))

        self._focusFormat = QtGui.QTextCharFormat()
        self._focusFormat.setForeground(qtlib.getHighlightColor(COLOR_FOCUS_DEFAULT))


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
    def combineFormats(self) -> dict[str, CombineFormat]:
        if not self._cachedCombineFormats:
            self.updateCombineFormats()
        return self._cachedCombineFormats


    def highlight(self, text: str, separator: str, txtWidget: QtWidgets.QPlainTextEdit):
        separator = separator.strip()

        formats = self.charFormats
        wordFormatMap = self.combineFormats

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
                    format = QtGui.QTextCharFormat()
                    format.setFontUnderline(True)
                    self._highlightPart(cursor, format, start, len(captionStrip))

                # Try highlighting combined words
                else:
                    captionWords = captionStrip.split(" ")
                    lastWord = captionWords[-1]
                    pos = start

                    if (combineFormat := wordFormatMap.get(lastWord)) and (groupFormat := combineFormat.getGroupFormat(captionWords)):
                        for word in captionWords[:-1]:
                            if word in groupFormat.words:
                                self._highlightPart(cursor, groupFormat.format, pos, len(word))
                            pos += len(word) + 1

                        self._highlightPart(cursor, groupFormat.format, pos, len(lastWord))

                    # if (combineFormat := wordFormatMap.get(lastWord)):
                    #     wordSet, wordFormat = combineFormat.getFormat(captionWords)
                    #     if wordSet and wordFormat:
                    #         lastWordFormat = None
                    #         for word in captionWords[:-1]:
                    #             if word in wordSet:
                    #                 self._highlightPart(cursor, wordFormat, pos, len(word))
                    #                 lastWordFormat = wordFormat
                    #             pos += len(word) + 1

                    #         if lastWordFormat:
                    #             self._highlightPart(cursor, lastWordFormat, pos, len(lastWord))

                    # if (combineFormat := wordFormatMap.get(lastWord)) and combineFormat.hasSubset(captionWords):
                    #     lastWordFormat = None
                    #     for word in captionWords[:-1]:
                    #         if wordFormat := combineFormat.wordFormats.get(word):
                    #             self._highlightPart(cursor, wordFormat, pos, len(word))
                    #             lastWordFormat = wordFormat
                    #         pos += len(word) + 1

                    #     if lastWordFormat:
                    #         self._highlightPart(cursor, lastWordFormat, pos, len(lastWord))

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


    def updateCombineFormats(self):
        # Last Word => CombineFormat
        formatMap = dict[str, CombineFormat]()

        for group in self.ctx.groups.groups:
            if not group.combineTags:
                continue

            groupFormat = group.charFormat
            groupWords = set[str]()
            groupLastWords = set[str]()

            for caption in group.captionsExpandWildcards:
                words = [word for word in caption.split(" ") if word]
                if len(words) < 2:
                    continue

                groupWords.update(words)

                lastWord = words[-1]
                groupLastWords.add(lastWord)

                for word in words[:-1]:
                    combineFormat = formatMap.get(lastWord)
                    if not combineFormat:
                        formatMap[lastWord] = combineFormat = CombineFormat(lastWord)

                    combineFormat.wordFormats[word] = groupFormat

                    wordSet = frozenset(words)
                    #combineFormat.tagSets.add(wordSet)
                    #combineFormat.tagFormats[wordSet] = groupFormat

            for lastWord in groupLastWords:
                wordSet = set(groupWords)
                wordSet.discard(lastWord)
                formatMap[lastWord].groupFormats.append(CombineFormat.GroupFormat(wordSet, groupFormat))

        # Remove entries with only one word
        self._cachedCombineFormats = {k: cf for k, cf in formatMap.items() if cf.finalize()}


    @Slot()
    def clearCache(self):
        self._cachedColors = None
        self._cachedCharFormats = None
        self._cachedCombineFormats = None


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



# One CombineFormat is shared by multiple groups.
# Retrieved from dict [ Last Word => CombineFormat ]
# That dict is uses for faster initial lookup, matching the last word.
class CombineFormat:
    class GroupFormat:
        def __init__(self, words: set[str], format: QtGui.QTextCharFormat):
            self.words = frozenset(words)
            self.format = format


    def __init__(self, lastWord: str):
        self.wordFormats = dict[str, QtGui.QTextCharFormat]()
        #self.tagSets = set[frozenset[str]]()

        #self.tagFormats = dict[frozenset[str], QtGui.QTextCharFormat]()
        #self._tagFormatsSorted = list[tuple[frozenset[str], QtGui.QTextCharFormat]]()

        self.lastWord = lastWord
        self.groupFormats = list[self.GroupFormat]()

    def finalize(self) -> bool:
        if len(self.wordFormats) < 2:
            return False

        # print("CombineFormat Tag Order:")
        # for k in self.tagFormats.keys():
        #     print(f"  {k}")

        # self._tagFormatsSorted = sorted(((k, v) for k, v in self.tagFormats.items()), key=lambda item: -len(item[0]))
        # self.tagFormats = None

        # print("CombineFormat Tag Order (sorted):")
        # for k, v in self._tagFormatsSorted:
        #     print(f"  {k}")


        self.groupFormats.sort(key=lambda item: -len(item.words))
        return True

    # def hasSubset(self, captionWords: list[str]) -> bool:
    #     captionWords = [word for word in captionWords if word]
    #     for tagSet in self.tagSets:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return True
    #     return False

    # def hasSubset(self, captionWords: list[str]) -> bool:
    #     captionWords = [word for word in captionWords if word]
    #     for tagSet, format in self._tagFormatsSorted:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return True
    #     return False


    # # Find group with longest match (maximum number of 'captionWords' in group tags)
    # def getFormat(self, captionWords: list[str]):
    #     captionWords = [word for word in captionWords if word]

    #     # TODO: Return set with words in group

    #     for tagSet, format in self._tagFormatsSorted:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return tagSet, format

    #     return None, None


    # Find group with longest match (maximum number of 'captionWords' in group tags)
    def getGroupFormat(self, captionWords: list[str]):
        captionWords = [word for word in captionWords if word and word != self.lastWord]
        if not captionWords:
            return None

        maxWords = 0
        bestFormat = None

        for groupFormat in self.groupFormats:
            intersection = groupFormat.words.intersection(captionWords)
            # Complete match: All caption words are members of the same group
            if len(intersection) == len(captionWords):
                return groupFormat

            if len(intersection) > maxWords:
                maxWords = len(intersection)
                bestFormat = groupFormat

        # if bestFormat:
        #     print(f"for caption: {captionWords}  => best group: {bestFormat.words}")
        return bestFormat
