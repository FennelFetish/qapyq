from __future__ import annotations
import csv, time, os, enum, heapq
from abc import ABC, abstractmethod
from typing import Any, NamedTuple, Iterable, Callable
from typing_extensions import override
from collections import defaultdict, Counter
from itertools import islice, takewhile
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTableView
from PySide6.QtGui import QTextCursor, QGuiApplication, QKeyEvent, QFont, QColor, QPalette
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QRunnable, QObject, QThreadPool, QThread
from difflib import SequenceMatcher
#from rapidfuzz import fuzz, distance
from lib import colorlib, qtlib
from config import Config


class AutoCompleteSourceType(enum.IntEnum):
    Csv             = 1
    Template        = 2
    PathTemplate    = 3

__GLOBAL_AUTOCOMPLETE_SOURCES: dict[AutoCompleteSourceType, AutoCompleteSource] = {}

def getAutoCompleteSource(type: AutoCompleteSourceType):
    if source := __GLOBAL_AUTOCOMPLETE_SOURCES.get(type):
        return source

    match type:
        case AutoCompleteSourceType.Csv:
            source = CsvNGramAutoCompleteSource()
            source.loadAsync()

        case AutoCompleteSourceType.Template:
            source = TemplateAutoCompleteSource()
            source.setupTemplate()

            from lib.captionfile import KeySettingsWindow
            KeySettingsWindow.signals.keysUpdated.connect(lambda: source.setupTemplate())

        case AutoCompleteSourceType.PathTemplate:
            source = TemplateAutoCompleteSource()
            source.setupPathTemplate()

    __GLOBAL_AUTOCOMPLETE_SOURCES[type] = source
    return source



GROUP_CATEGORY = -1000

class Category(NamedTuple):
    name: str
    color: QColor



class SuggestionScore:
    class Context(NamedTuple):
        search: str
        searchParts: list[str]
        matcher: SequenceMatcher

    __slots__ = ('ctx', 'suggestion', 'prefixScore', '_matchRatio')

    def __init__(self, ctx: Context, suggestion: Suggestion):
        self.ctx = ctx
        self.suggestion = suggestion

        self.prefixScore: float = 0.0
        self._matchRatio: float = -1.0

        numParts = len(ctx.searchParts)
        for i, part in enumerate(ctx.searchParts):
            weight = (numParts-i) / numParts

            iSearchInTag = suggestion.tag.find(part)
            if iSearchInTag == 0:
                self.prefixScore += 1.0 * weight
                break
            elif iSearchInTag > 0:
                if suggestion.tag[iSearchInTag-1].isspace():
                    self.prefixScore += 0.75 * weight
                    break
                else:
                    self.prefixScore += 0.5 * weight
                    break

        # iSearchInTag = suggestion.tag.find(ctx.search)
        # if iSearchInTag == 0:
        #     self.prefixScore += 1.0
        # elif iSearchInTag > 0:
        #     if suggestion.tag[iSearchInTag-1].isspace():
        #         self.prefixScore += 0.75
        #     else:
        #         self.prefixScore += 0.5

        # iTagInSearch = ctx.search.find(tag)
        # if iTagInSearch == 0:
        #     self.prefixScore += 0.1
        # elif iTagInSearch > 0:
        #     if ctx.search[iTagInSearch-1].isspace():
        #         self.prefixScore += 0.075
        #     else:
        #         self.prefixScore += 0.05

    @property
    def matchRatio(self) -> float:
        if self._matchRatio < 0:
            # search = self.ctx.search
            # tag = self.suggestion.tag

            #self._matchRatio = fuzz.token_set_ratio(search, tag)
            #self._matchRatio = fuzz.partial_token_set_ratio(search, tag)
            #self._matchRatio = fuzz.token_sort_ratio(search, tag)
            #self._matchRatio = fuzz.partial_token_sort_ratio(search, tag)
            #self._matchRatio = fuzz.token_ratio(search, tag)
            #self._matchRatio = fuzz.partial_token_ratio(search, tag)
            ####self._matchRatio = fuzz.partial_ratio(search, tag)
            #self._matchRatio = fuzz.WRatio(search, tag)
            #self._matchRatio = fuzz.QRatio(search, tag)
            #self._matchRatio = fuzz.ratio(search, tag)

            #self._matchRatio = distance.Levenshtein.normalized_similarity(search, tag)

            self.ctx.matcher.set_seq1(self.suggestion.tag)
            self._matchRatio = self.ctx.matcher.ratio()

        return self._matchRatio

    def __lt__(self, other: SuggestionScore) -> bool:
        prefixDiff = self.prefixScore - other.prefixScore
        if abs(prefixDiff) > 0.2:
            return prefixDiff < 0

        f0 = self.suggestion.scoreFactor
        f1 = other.suggestion.scoreFactor

        ngramDiff = (self.suggestion.nGramRatio * f0) - (other.suggestion.nGramRatio * f1)
        if abs(ngramDiff) > 0.02:
            return ngramDiff < 0

        matchDiff = (self.matchRatio * f0) - (other.matchRatio * f1)
        if abs(matchDiff) > 0.05:
            return matchDiff < 0

        if self.suggestion.freq != other.suggestion.freq:
            return self.suggestion.freq < other.suggestion.freq

        return self.suggestion.tag < other.suggestion.tag

    def __eq__(self, other: object) -> bool:
        return self is other

    def getScores(self) -> tuple:
        f = self.suggestion.scoreFactor
        return (
            self.prefixScore,
            self.suggestion.nGramRatio * f,
            self._matchRatio * f,
            self.suggestion.freq
        )



class AutoCompleteModel(QAbstractTableModel):
    CATEGORY: dict[int, Category] = None
    CATEGORY_DEFAULT: Category = None

    NUM_SUGGESTIONS = 15

    ROLE_KEEP_ALIAS = Qt.ItemDataRole.UserRole

    def __init__(self, autoCompleteSources: list[AutoCompleteSource], parent):
        super().__init__(parent)
        self.sources = autoCompleteSources
        self.suggestions: list[Suggestion] = list()

        self.categoryFont = QFont()
        self.categoryFont.setPointSizeF(self.categoryFont.pointSizeF() * 0.75)

        if AutoCompleteModel.CATEGORY is None:
            self._initStatic()

    @classmethod
    def _initStatic(cls):
        s = 0.8
        v = colorlib.TEXT_HIGHLIGHT_V
        a = 0.65 if colorlib.DARK_THEME else 0.8

        cls.CATEGORY = {
            GROUP_CATEGORY: Category("Group",       QColor.fromHsvF(0.083, s, v, a)),
            0:              Category("General",     QColor.fromHsvF(0.166, s, v, a)),
            1:              Category("Artist",      QColor.fromHsvF(0.333, s, v, a)),
            3:              Category("Copyright",   QColor.fromHsvF(0.010, s, v, a)),
            4:              Category("Character",   QColor.fromHsvF(0.583, s, v, a)),
        }

        cls.CATEGORY_DEFAULT = Category("Other", QColor.fromHsvF(0.0, 0.0, v, a))

        try:
            cls.NUM_SUGGESTIONS = int(Config.autocomplete["suggestion_count"])
        except: pass


    def updateSuggestions(self, search: str):
        searchWords = list(filter(None, search.split()))
        search = " ".join(searchWords)

        searchParts = [search]
        for i in range(1, len(searchWords)):
            part = " ".join(searchWords[i:])
            if len(part) >= 2:
                searchParts.append(part)
            else:
                break

        suggestions: dict[str, Suggestion] = {}
        for source in self.sources:
            for sug in source.getSuggestions(search):
                if existingSug := suggestions.get(sug.tag):
                    sug = existingSug.max(sug)
                suggestions[sug.tag] = sug

        ctx = SuggestionScore.Context(search, searchParts, SequenceMatcher(b=search, autojunk=False))
        scores = sorted((SuggestionScore(ctx, sug) for sug in suggestions.values()), reverse=True)

        # print("Scored Suggestions:")
        # for i, score in enumerate(scores[:20], 1):
        #     print(f"{str(i):2} {score.suggestion.tag} {score.getScores()}")

        self.beginResetModel()
        self.suggestions.clear()

        minRatio = 0
        itScores = iter(scores)
        for score in islice(itScores, self.NUM_SUGGESTIONS):
            self.suggestions.append(score.suggestion)
            minRatio = score.suggestion.nGramRatio

        minRatio *= 0.99
        self.suggestions.extend(score.suggestion for score in takewhile(lambda score: score.suggestion.nGramRatio > minRatio, itScores))
        self.endResetModel()


    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self.suggestions)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 2

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        sug = self.suggestions[index.row()]

        # Column 0: Tag
        if index.column() == 0:
            match role:
                case Qt.ItemDataRole.DisplayRole:
                    return f"{sug.tag} → {sug.aliasFor}" if sug.aliasFor else sug.tag

                case Qt.ItemDataRole.EditRole:
                    return sug.aliasFor or sug.tag

                case self.ROLE_KEEP_ALIAS:
                    return sug.tag

        # Column 1: Category / Info
        else:
            match role:
                case Qt.ItemDataRole.DisplayRole:
                    if sug.info is not None:
                        return sug.info
                    return self.CATEGORY.get(sug.category, self.CATEGORY_DEFAULT).name

                case Qt.ItemDataRole.ForegroundRole:
                    return self.CATEGORY.get(sug.category, self.CATEGORY_DEFAULT).color

                case Qt.ItemDataRole.FontRole:
                    return self.categoryFont

                case Qt.ItemDataRole.TextAlignmentRole:
                    return Qt.AlignmentFlag.AlignVCenter

        return None



class AutoCompletePopup(QTableView):
    SCROLLBAR_STYLESHEET = None

    @staticmethod
    def _getScrollbarStylesheet(palette: QPalette) -> str:
        color = palette.color(palette.ColorRole.Highlight)
        color = f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.4)"

        return "\n".join((
            "QScrollBar:vertical {width: 6px; background: transparent; margin: 0}",
            "QScrollBar::handle:vertical {background: " + color + "; min-height: 20px; border-radius: 3px}",
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {height: 0px}",
            "QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {background: none}"
        ))


    def __init__(self):
        super().__init__()
        self.setShowGrid(False)
        qtlib.setMonospace(self)
        #self.setAlternatingRowColors(True)
        #self.setWindowOpacity(0.9)

        self.setSelectionBehavior(self.SelectionBehavior.SelectRows)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.setEditTriggers(self.EditTrigger.NoEditTriggers)

        headerH = self.horizontalHeader()
        headerH.hide()
        headerH.setSectionResizeMode(headerH.ResizeMode.Fixed)

        headerV = self.verticalHeader()
        headerV.hide()
        headerV.setSectionResizeMode(headerV.ResizeMode.ResizeToContents)
        # headerV.setDefaultSectionSize(16)
        self._rowHeight = -1

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        if AutoCompletePopup.SCROLLBAR_STYLESHEET is None:
            AutoCompletePopup.SCROLLBAR_STYLESHEET = self._getScrollbarStylesheet(self.palette())
        self.verticalScrollBar().setStyleSheet(AutoCompletePopup.SCROLLBAR_STYLESHEET)


    @Slot()
    def _initRowHeight(self):
        self._rowHeight = max(self.rowHeight(0), 16)

    def updateSize(self, numRows: int) -> int:
        # Set height
        numRows = min(numRows, self.verticalHeader().count())
        rowHeight = self._rowHeight
        if rowHeight < 0:
            rowHeight = 20
            if numRows > 0:
                QTimer.singleShot(0, self._initRowHeight)

        self.setFixedHeight(numRows * rowHeight + 2)

        # Calc width
        self.resizeColumnsToContents()
        col0w = self.columnWidth(0) + 12
        self.setColumnWidth(0, col0w)
        return col0w + self.columnWidth(1) + self.verticalScrollBar().sizeHint().width() + 2

    def changeSelection(self, offset: int):
        index = self.currentIndex()
        row = (index.row() + offset) % self.model().rowCount()
        self.selectRow(row)



class TextEditCompleter:
    @staticmethod
    def createPunctuationTrans(punctuation: str) -> tuple[dict, str]:
        punct = punctuation[0]

        table = {char: punct for char in punctuation[1:]}
        table["\n"] = punct
        table["-"]  = " "  # treat dashes as word boundaries

        return str.maketrans(table), punct

    PUNCTUATION_TRANS = createPunctuationTrans(",.:;")
    SKIP_WORD_PUNCT  = "!?()[]"


    MIN_PREFIX_LEN = 2
    MAX_PREFIX_WORDS = 4

    SKIP_WORD_MAX_SIMILARITY = 0.75
    SKIP_WORD_MAX_LENDIFF    = 2

    IGNORE_KEYS    = (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Shift)
    TAB_NAVIGATION = {Qt.Key.Key_Tab.value: 1, Qt.Key.Key_Backtab.value: -1}

    COMPLETE_INTERVAL = 30 # ms
    COMPLETE_INTERVAL_NS = COMPLETE_INTERVAL * 1_000_000


    def __init__(self, textEdit: QPlainTextEdit, autoCompleteSources: list[AutoCompleteSource], separator: str = ", "):
        self.textEdit = textEdit
        self.separator = separator

        self.model = AutoCompleteModel(autoCompleteSources, parent=textEdit)

        self.completer = QCompleter(self.model, parent=textEdit)
        self.completer.setPopup(AutoCompletePopup())
        self.completer.setWidget(textEdit)
        self.completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated[QModelIndex].connect(self._insertCompletion)

        try:
            visibleItems = max(int(Config.autocomplete["popup_size"]), 1)
        except:
            visibleItems = 10
        self.completer.setMaxVisibleItems(visibleItems)

        self._timer = QTimer(textEdit, singleShot=True, interval=self.COMPLETE_INTERVAL)
        self._timer.timeout.connect(self._updateComplete)
        self._tLastComplete = 0


    def isActive(self) -> bool:
        return self.completer.popup().isVisible()

    def hide(self):
        self.completer.popup().hide()


    @Slot(QModelIndex)
    def _insertCompletion(self, index: QModelIndex):
        keyMod = QGuiApplication.keyboardModifiers()

        matchText: str  = index.data(AutoCompleteModel.ROLE_KEEP_ALIAS)
        insertText: str = matchText if keyMod & Qt.KeyboardModifier.ShiftModifier else index.data(Qt.ItemDataRole.EditRole)

        matchText, insertText = self.transformInsertText(matchText, insertText)

        cursor = self.textEdit.textCursor()
        if not cursor.hasSelection():
            insertText = self._selectInsertRegion(cursor, matchText, insertText)

        cursor.beginEditBlock()
        cursor.insertText(insertText)

        if not keyMod & Qt.KeyboardModifier.ControlModifier and cursor.atBlockEnd():
            cursor.insertText(self.separator)

        # Split ops in undo stack
        cursor.insertText(" ")
        cursor.deletePreviousChar()

        cursor.endEditBlock()
        self.textEdit.setTextCursor(cursor)


    def _selectInsertRegion(self, cursor: QTextCursor, matchText: str, insertText: str) -> str:
        firstMatchWord = self.splitWords(matchText, 1)[0]
        matcher = SequenceMatcher(autojunk=False)

        trans, punct = self.PUNCTUATION_TRANS
        text = self.textEdit.toPlainText().translate(trans)

        # Init cursorPos to the first non-whitespace char to the left of text cursor
        cursorPos = max(cursor.position()-1, 0)
        while cursorPos > 0 and text[cursorPos].isspace():
            cursorPos -= 1

        # ==== FIND SELECTION START ====
        start = cursorPos + 1
        leftBound = text.rfind(punct, 0, start) + 1

        # Skip words to the left of cursor.
        bestStart = -1
        remainingSkipWords = max(self._numReplaceWordsLeft(matchText), self._numReplaceWordsLeft(insertText))
        remainingSkipWords += 1  # Try skipping one more word to handle typos with space like: 'arm chair' => 'armchair'

        while remainingSkipWords > 0 and start > leftBound:
            remainingSkipWords -= 1

            p = text.rfind(" ", leftBound, start)
            if p < 0:
                p = leftBound # No more words, abort loop
                skippedWord = text[p : start]
            else:
                skippedWord = text[p+1 : start]

                # Skip additional spaces
                while p > 0 and text[p-1].isspace():
                    p -= 1

            start = p

            # Since we're checking one extra word to handle typos:
            # If no similar words were found until the second word (= originally the first word), mark it as the best start.
            if remainingSkipWords == 1 and bestStart < 0:
                bestStart = start
            else:
                # Check if skipped word is similar to first word of matchText
                matcher.set_seqs(skippedWord, firstMatchWord[:len(skippedWord) + self.SKIP_WORD_MAX_LENDIFF])
                if matcher.ratio() >= self.SKIP_WORD_MAX_SIMILARITY:
                    bestStart = start

        # Set start to the leftmost similar word, if there were any
        if bestStart >= 0:
            start = bestStart

        # Add whitespace to the left
        cursor.setPosition(start)
        if not cursor.atBlockStart():
            if start > leftBound:
                # Add space between words
                numSpaces = 1
            else:
                # Add space according to separator
                numSpaces = len(self.separator) - len(self.separator.rstrip())

            for p in range(start, min(start+numSpaces, len(text))):
                if text[p].isspace():
                    start += 1
                else:
                    insertText = " " + insertText

        # ==== FIND SELECTION END ====
        # Skip to end of word
        end = cursorPos
        for p in range(end+1, len(text)):
            char = text[p]
            if not (char.isalnum() or char in self.SKIP_WORD_PUNCT):
                break
            end = p

        end += 1

        # Skip whitespace to the right of cursor
        for p in range(end, len(text)):
            char = text[p]
            if char.isspace():
                end = p+1
            else:
                if char.isalnum():
                    end = p-1  # Leave space between words
                break

        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        return insertText


    @staticmethod
    def transformInsertText(matchText: str, insertText: str) -> tuple[str, str]:
        return matchText, insertText

    @staticmethod
    def splitWords(text: str, maxSplit: int = -1) -> list[str]:
        return text.replace("-", " ").split(" ", maxSplit)

    @staticmethod
    def _numReplaceWordsLeft(text: str) -> int:
        return len(TextEditCompleter.splitWords(text))


    def textUnderCursor(self) -> str:
        cursor = self.textEdit.textCursor()
        trans, punct = self.PUNCTUATION_TRANS

        for _ in range(self.MAX_PREFIX_WORDS):
            cursor.movePosition(QTextCursor.MoveOperation.WordLeft, QTextCursor.MoveMode.KeepAnchor)
            text = cursor.selectedText()

            p = text.translate(trans).rfind(punct) + 1
            if p > 0:
                text = text[p:]
                break

            if cursor.atBlockStart():
                break

        return text.lstrip().lower()

    def complete(self, force: bool = False):
        popup: AutoCompletePopup = self.completer.popup()

        prefix = self.textUnderCursor()
        if not prefix or (not force and len(prefix) < self.MIN_PREFIX_LEN):
            self.completer.setCompletionPrefix("")
            popup.hide()
            self._timer.stop()
            return

        if force or prefix != self.completer.completionPrefix():
            self.completer.setCompletionPrefix(prefix)

            if self._tLastComplete > time.monotonic_ns() - self.COMPLETE_INTERVAL_NS:
                self._timer.start()
            else:
                self._updateComplete()

    @Slot()
    def _updateComplete(self):
        self.model.updateSuggestions( self.completer.completionPrefix() )
        QTimer.singleShot(0, self._resetSelection)

        popup: AutoCompletePopup = self.completer.popup()
        width = popup.updateSize(self.completer.maxVisibleItems())
        rect = self.textEdit.cursorRect()
        rect.setWidth(width)
        self.completer.complete(rect)

        self._tLastComplete = time.monotonic_ns()


    @Slot()
    def _resetSelection(self):
        popup: AutoCompletePopup = self.completer.popup()
        popup.setCurrentIndex(self.model.index(0, 0))
        popup.scrollToTop()


    def handleKeyPress(self, event: QKeyEvent, textEditEventHandler: Callable[[QKeyEvent], None]):
        key = event.key()
        ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if ctrl and key == Qt.Key.Key_Space:
            self.complete(force=True)
            return

        if active := self.isActive():
            if key in self.IGNORE_KEYS:
                event.ignore()
                return

            if change := self.TAB_NAVIGATION.get(key):
                popup: AutoCompletePopup = self.completer.popup()
                popup.changeSelection(change)
                event.accept()
                return

        textEditEventHandler(event)

        # When typing, open the popup only after the key was inserted into the TextEdit by textEditEventHandler.
        # Qt's keycodes above 0xff are invisible control keys.
        if (active or (not ctrl and key <= 0xff)) and Config.autocomplete.get("auto_popup"):
            self.complete()



class TemplateTextEditCompleter(TextEditCompleter):
    MIN_PREFIX_LEN = 1

    PUNCTUATION_TRANS = TextEditCompleter.createPunctuationTrans("#:{}")

    def __init__(self, textEdit: QPlainTextEdit, autoCompleteSources: list[AutoCompleteSource]):
        super().__init__(textEdit, autoCompleteSources, "}}")

    @override
    @staticmethod
    def transformInsertText(matchText: str, insertText: str) -> tuple[str, str]:
        return matchText.lstrip("#"), insertText.lstrip("#")

    @override
    @staticmethod
    def _numReplaceWordsLeft(text: str) -> int:
        return 1000

    @override
    def textUnderCursor(self) -> str:
        text   = self.textEdit.toPlainText()
        cursor = self.textEdit.textCursor()

        pos = cursor.position()
        start = text.rfind("{{", 0, pos)
        if start < 0:
            return ""  # No block

        if text.rfind("}}", start+2, pos) >= 0:
            return ""  # Not inside block

        for char in "#:":
            start = max(start, text.rfind(char, start+1, pos))

        cursor.setPosition(start, QTextCursor.MoveMode.KeepAnchor)
        return cursor.selectedText()


class TemplateTextEdit(QPlainTextEdit):
    def __init__(self, autoCompleteSources: list[AutoCompleteSource] = []):
        super().__init__()
        self.completer = TemplateTextEditCompleter(self, autoCompleteSources) if autoCompleteSources else None

    @override
    def keyPressEvent(self, event: QKeyEvent):
        if self.completer:
            self.completer.handleKeyPress(event, super().keyPressEvent)
        else:
            super().keyPressEvent(event)



# ========== AutoComplete Data Structures ==========

class Suggestion(NamedTuple):
    tag: str
    category: int
    freq: int
    aliasFor: str | None
    scoreFactor: float
    nGramRatio: float
    info: str | None = None

    def max(self, other: Suggestion) -> Suggestion:
        return Suggestion(
            self.tag,
            max(self.category, other.category),
            self.freq + other.freq,
            self.aliasFor or other.aliasFor,
            max(self.scoreFactor, other.scoreFactor),
            max(self.nGramRatio, other.nGramRatio),
            self.info or other.info
        )


class TagData(NamedTuple):
    tag: str
    category: int
    freq: int
    aliasFor: str | None

    def toSuggestion(self, scoreFactor: float, nGramRatio: float):
        return Suggestion(self.tag, self.category, self.freq, self.aliasFor, scoreFactor, nGramRatio)

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, value: object) -> bool:
        return self is value


class AutoCompleteSource(ABC):
    Type = AutoCompleteSourceType

    # https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
    KAOMOJIS = {
        "0_0", "(o)_(o)", "+_+", "+_-", "._.", "<o>_<o>", "<|>_<|>", "=_=", ">_<", "3_3", "6_9", ">_o", "@_@", "^_^", "o_o", "u_u", "x_x", "|_|", "||_||"
    }

    @abstractmethod
    def getSuggestions(self, search: str) -> list[Suggestion]:
        ...



class NGramAutoCompleteSource(AutoCompleteSource):
    MIN_RATIO = 0.1
    MAX_RESULTS = 300

    def __init__(self, scoreFactor: float):
        super().__init__()
        self.scoreFactor = scoreFactor
        self.n = 3
        self.reset()

    def reset(self):
        self.ngrams = defaultdict[str, set[TagData]](set)

    def getNgrams(self, text: str) -> Iterable[str]:
        if len(text) < self.n:
            text = text.center(self.n, " ") # 'ab' => ' ab' (right-justified)

        for i in range(len(text) - self.n + 1):
            yield text[i:i+self.n]

    def addTag(self, tag: str, category: int, freq: int, aliasFor: str | None = None):
        tagData = TagData(tag, category, freq, aliasFor)
        for ngram in self.getNgrams(" " + tag):
            self.ngrams[ngram].add(tagData)

    @classmethod
    def prepareTag(cls, tag: str) -> str:
        return tag if (tag in cls.KAOMOJIS) else tag.replace("_", " ").strip().lower()

    @override
    def getSuggestions(self, search: str) -> list[Suggestion]:
        candidateTags = set[TagData]()
        searchNgrams = set(self.getNgrams(search))
        for ngram in searchNgrams:
            if tags := self.ngrams.get(ngram):
                candidateTags.update(tags)

        candidates = list[tuple[float, TagData]]()
        for tagData in candidateTags:
            tagNgrams = set(self.getNgrams(tagData.tag))

            intersect = len(searchNgrams & tagNgrams)
            union     = len(searchNgrams) + len(tagNgrams) - intersect
            jaccardIndex = intersect / union

            if jaccardIndex >= self.MIN_RATIO:
                # Use min-heap to remember top results
                if len(candidates) < self.MAX_RESULTS:
                    heapq.heappush(candidates, (jaccardIndex, tagData))
                elif jaccardIndex > candidates[0][0]:
                    heapq.heapreplace(candidates, (jaccardIndex, tagData))

        # print(f"NUM N-GRAM CANDIDATES: {len(candidates)}")
        # print(f"  Minimum: {min(candidates) if candidates else 'N/A'}")
        # print(f"  Maximum: {max(candidates) if candidates else 'N/A'}")
        # print("Candidate Tags:")
        # for i, (ratio, tag) in enumerate(candidates, 1):
        #     print(f"{str(i):3} {tag} ({ratio:.4f})")

        return [tagData.toSuggestion(self.scoreFactor, ratio) for ratio, tagData in candidates]



class GroupNGramAutoCompleteSource(NGramAutoCompleteSource):
    FREQ = 10_000_000

    def __init__(self):
        super().__init__(1.25)

    def update(self, groups: Iterable[list[str]]):
        self.reset()
        existingTags = set[str]()

        for group in groups:
            for tag in group:
                tag = self.prepareTag(tag)
                if tag not in existingTags:
                    existingTags.add(tag)
                    self.addTag(tag, GROUP_CATEGORY, self.FREQ)



class CsvNGramAutoCompleteSource(NGramAutoCompleteSource):
    ALIAS_SEP = ","

    def __init__(self):
        super().__init__(1.0)


    def loadAsync(self):
        task = LoadCsvTask()
        task.signals.done.connect(self._setNgrams, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot(tuple)
    def _setNgrams(self, wrappedNgrams: tuple[defaultdict]):
        self.ngrams = wrappedNgrams[0]


    def load(self, folder: str):
        def fileFilter(file: str):
            return file.endswith(".csv")

        existingTags = set[str]()
        for (root, dirs, files) in os.walk(folder, topdown=True, followlinks=True):
            for file in filter(fileFilter, files):
                path = os.path.join(root, file)

                try:
                    t = time.monotonic_ns()
                    numTags, numAliases = self._loadCsv(path, existingTags)
                    t = (time.monotonic_ns() - t) / 1_000_000
                    print(f"AutoComplete: Loaded {numTags} tags (+{numAliases} aliases) in {t:.2f} ms from '{path}'")
                except:
                    print(f"AutoComplete: Failed to load tags from '{path}'")
                    import traceback
                    traceback.print_exc()


    def _loadCsv(self, path: str, existingTags: set[str]) -> tuple[int, int]:
        numTags = 0
        numAliases = 0

        excludeCategories = Config.autocomplete["exclude_categories"]

        bufferSize = 1048576 # 1MB
        with open(path, 'r', newline='', encoding='utf-8', errors='replace', buffering=bufferSize) as csvFile:
            colTag, colAlias, colCat, colFreq, skipHeaderRow = self._detectColumns(csvFile)

            if colTag < 0:
                print(f"WARNING: Couldn't find tag column in CSV file '{path}'")
                return 0, 0

            aliasGetter = self._createColumnGetter(colAlias, "")
            catGetter   = self._createColumnGetter(colCat, -1)
            freqGetter  = self._createColumnGetter(colFreq, 0)

            csvFile.seek(0)
            reader = csv.reader(csvFile)
            if skipHeaderRow:
                next(reader)

            for i, row in enumerate(reader):
                tag = self.prepareTag(row[colTag])
                if not tag:
                    continue

                category = self.toInt(catGetter(row))
                if category in excludeCategories:
                    continue

                freq = self.toInt(freqGetter(row))

                if tag not in existingTags:
                    existingTags.add(tag)
                    self.addTag(tag, category, freq)
                    numTags += 1

                if aliases := aliasGetter(row):
                    for alias in aliases.split(self.ALIAS_SEP):
                        if (alias := self.prepareTag(alias)) and alias not in existingTags:
                            existingTags.add(alias)
                            self.addTag(alias, category, 0, aliasFor=tag)
                            numAliases += 1

                # Throttle to keep UI responsive
                if not (i % 500):
                    QThread.msleep(1)

        return numTags, numAliases

    def _detectColumns(self, csvFile) -> tuple[int, int, int, int, bool]:
        singleTag = Counter[int]()
        multiTag  = Counter[int]()
        smallNr   = Counter[int]()
        largeNr   = Counter[int]()

        invalidCharTrans = str.maketrans("", "", "[](){}")

        reader = csv.reader(csvFile)
        row = next(reader)
        skipHeaderRow = len(row) > 1 and not any(val.isnumeric() for val in row)

        for row in islice(csv.reader(csvFile), 50):
            for col, val in enumerate(row):
                nr = self.toInt(val)
                if nr > 20:
                    largeNr[col] += 1
                elif nr >= 0:
                    smallNr[col] += 1
                elif self.ALIAS_SEP in val:
                    multiTag[col] += 1
                elif val.translate(invalidCharTrans):
                    singleTag[col] += 1

        return (
            self._counterMax(singleTag), # tag
            self._counterMax(multiTag),  # aliases
            self._counterMax(smallNr),   # category
            self._counterMax(largeNr),   # frequency (count)
            skipHeaderRow
        )

    @staticmethod
    def _counterMax(counter: Counter[int]) -> int:
        if most := counter.most_common(): # [(key, count), ...]
            # Return highest key if tied
            key, maxCount = most[0]
            for key, _ in takewhile(lambda item: item[1] == maxCount, most): pass
            return key
        return -1

    @staticmethod
    def _createColumnGetter(col: int, default: Any) -> Callable[[list[str]], str | Any]:
        if col >= 0:
            return lambda row: row[col]
        else:
            return lambda row: default

    @staticmethod
    def toInt(value: Any) -> int:
        try:
            return int(value)
        except ValueError:
            return -1


class LoadCsvTask(QRunnable):
    FOLDER = "./user/autocomplete/"

    class Signals(QObject):
        done = Signal(tuple)


    def __init__(self):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = self.Signals()

    def run(self):
        # Don't block at app start. Let other stuff initialize first.
        timeSinceStart = time.monotonic_ns() - Config.startTime
        delay = 1500 if timeSinceStart < 1_000_000_000 else 200
        QThread.msleep(delay)

        csvSource = CsvNGramAutoCompleteSource()

        try:
            csvSource.load(self.FOLDER)
        finally:
            self.signals.done.emit((csvSource.ngrams,))



class TemplateAutoCompleteSource(NGramAutoCompleteSource):
    MIN_RATIO = 0.01

    VAR_INFO = {
        "{{text":           "",
        "{{current":        "",
        "{{refined":        "",
        "{{path":           "",
        "{{path.ext":       "",
        "{{name":           "",
        "{{name.ext":       "",
        "{{ext":            "",
        "{{folder":         "",
        "{{date":           "",
        "{{time":           "",
        "{{load":           ":Name",
        "{{static":         ":Text",
        "{{coinflip":       ":TrueText:FalseText:Chance",
    }

    FUNC_INFO = {
        "#store":           ":Name",
        "#lower":           "",
        "#upper":           "",
        "#strip":           "",
        "#oneline":         "",
        "#default":         ":Text",
        "#defaultvar":      ":Var",
        "#first":           ":Count:Separator",
        "#drop":            ":Count:Separator",
        "#replace":         ":Search:Replace:Count",
        "#replacevar":      ":Search:Var:Count",
        "#shuffle":         ":Separator",
        "#shufflekeep":     ":Count:Separator",
        "#reverse":         ":Separator",
        "#join":            ":Var:Separator",
        "#noprefix":        ":Prefixes",
        "#nosubsets":       ":Var:Sep:VarSep:WordSeps",
        "#nodup":           ":Separator",
        "#ifcontains":      ":Search:TrueText:FalseText"
    }

    ALL_INFO = VAR_INFO | FUNC_INFO


    def __init__(self, scoreFactor: float = 1.0, jsonKeys: bool = False):
        super().__init__(scoreFactor)
        self.n = 2
        self.jsonKeys = jsonKeys


    @override
    def getSuggestions(self, search: str) -> list[Suggestion]:
        defaultInfo = "Key Exists" if self.jsonKeys else ""  # Empty string disables category
        suggestions = super().getSuggestions(search)
        return [
            Suggestion(sug.tag.lstrip("{"), sug.category, sug.freq, "", sug.scoreFactor, sug.nGramRatio, self.ALL_INFO.get(sug.tag, defaultInfo))
            for sug in suggestions
        ]


    def addVar(self, var: str, freq: int = 0):
        self.addTag("{{" + var, -1, freq)


    def setupTemplate(self):
        assert not self.jsonKeys
        self.reset()

        for tag in Config.keysTags:
            self.addVar(f"tags.{tag}")
        for cap in Config.keysCaption:
            self.addVar(f"captions.{cap}")

        for var in self.VAR_INFO:
            self.addTag(var, -1, 0)

        for func in self.FUNC_INFO:
            self.addTag(func, -1, 0)

    def setupPathTemplate(self):
        assert not self.jsonKeys
        self.reset()

        for var in ("w", "h", "region", "rotation"):
            self.addVar(var)

    def updateJsonKeys(self, keys: Iterable[str]):
        for key in keys:
            self.addVar(key, 1)
