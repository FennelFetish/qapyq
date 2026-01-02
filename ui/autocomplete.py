from __future__ import annotations
import csv, time, os
from abc import ABC, abstractmethod
from typing import Any, NamedTuple, Iterable, Callable
from typing_extensions import override
from collections import defaultdict, Counter
from itertools import islice, takewhile
from PySide6.QtWidgets import QCompleter, QPlainTextEdit, QTableView
from PySide6.QtGui import QTextCursor, QKeyEvent, QFont, QColor
from PySide6.QtCore import Qt, Signal, Slot, QAbstractTableModel, QModelIndex, QPersistentModelIndex, QTimer, QRunnable, QObject, QThreadPool, QThread
from difflib import SequenceMatcher
#from rapidfuzz import fuzz, distance
from lib import colorlib, qtlib


__CSV_SOURCE: CsvNGramAutoCompleteSource | None = None

def getCsvAutoCompleteSource() -> CsvNGramAutoCompleteSource:
    global __CSV_SOURCE
    if __CSV_SOURCE is None:
        __CSV_SOURCE = CsvNGramAutoCompleteSource()
        __CSV_SOURCE.loadAsync()

    return __CSV_SOURCE



GROUP_CATEGORY = -1000

class Category(NamedTuple):
    name: str
    color: QColor


class AutoCompleteModel(QAbstractTableModel):
    CATEGORY: dict[int, Category] = None
    CATEGORY_DEFAULT: Category = None

    NUM_SUGGESTIONS = 15

    def __init__(self, autoCompleteSources: list[AutoCompleteSource], parent):
        super().__init__(parent)
        self.sources = autoCompleteSources
        self.suggestions: list[Suggestion] = list()

        self.categoryFont = QFont()
        self.categoryFont.setPointSizeF(self.categoryFont.pointSizeF() * 0.75)

        if AutoCompleteModel.CATEGORY is None:
            self._initCategories()

    @classmethod
    def _initCategories(cls):
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


    def updateSuggestions(self, search: str):
        self.beginResetModel()

        suggestions: dict[str, Suggestion] = {}
        for source in self.sources:
            for sug in source.getSuggestions(search):
                if existingSug := suggestions.get(sug.tag):
                    sug = existingSug.max(sug)
                suggestions[sug.tag] = sug

        matcher = SequenceMatcher(a=search, autojunk=False)
        scoredSuggestions = list[tuple[Suggestion, tuple]]()
        for sug in suggestions.values():
            tag = sug.tag

            # TODO: Match last words of current search:
            #       'black swivel cha..' should suggest 'swivel chair'
            # TODO: Allow wildcard that matches all ngrams: '??? chair'
            iTagSearch = tag.find(search)
            if iTagSearch == 0:
                score = 1.0
            elif iTagSearch > 0:
                if tag[iTagSearch-1].isspace():
                    score = 0.75
                else:
                    score = 0.5
            else:
                score = 0.0

            # iSearchTag = search.find(tag)
            # if iSearchTag == 0:
            #     score += 0.5
            # elif iSearchTag > 0:
            #     if search[iSearchTag-1].isspace():
            #         score += 0.375
            #     else:
            #         score += 0.25

            # iSearchTag = search.find(tag)
            # if iSearchTag > 0:
            #     if search[iSearchTag-1].isspace():
            #         score += 0.25
            #     else:
            #         score += 0.1

            #ratio = fuzz.token_set_ratio(search, tag)
            #ratio = fuzz.partial_token_set_ratio(search, tag)
            #ratio = fuzz.token_sort_ratio(search, tag)
            #ratio = fuzz.partial_token_sort_ratio(search, tag)
            #ratio = fuzz.token_ratio(search, tag)
            #ratio = fuzz.partial_token_ratio(search, tag)
            #####ratio = fuzz.partial_ratio(search, tag)
            #ratio = fuzz.WRatio(search, tag)
            #ratio = fuzz.QRatio(search, tag)
            #ratio = fuzz.ratio(search, tag)

            #ratio = distance.Levenshtein.normalized_similarity(search, tag)

            matcher.set_seq2(sug.tag)
            ratio = round(matcher.ratio() * sug.scoreFactor, 2)

            ngramRatio = round(sug.nGramRatio * sug.scoreFactor, 2)
            scoredSuggestions.append((sug, (score, ngramRatio, ratio, sug.freq)))

        scoredSuggestions.sort(key=self._sortKey, reverse=True)

        # print("Scored Suggestions:")
        # for i, sug in enumerate(scoredSuggestions[:50], 1):
        #     print(f"{str(i):2} {sug[0].tag} ({sug[1]})")

        minRatio = 0
        self.suggestions.clear()
        itSug = iter(scoredSuggestions)
        for sug in islice(itSug, self.NUM_SUGGESTIONS):
            self.suggestions.append(sug[0])
            minRatio = sug[1][1]

        minRatio *= 0.99
        self.suggestions.extend(sug[0] for sug in takewhile(lambda sug: sug[1][1] > minRatio, itSug))
        self.endResetModel()


    @staticmethod
    def _sortKey(entry: tuple[Suggestion, tuple]) -> tuple:
        return (entry[1], entry[0].tag)

    @override
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self.suggestions)

    @override
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex) -> int:
        return 2

    @override
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        row, col = index.row(), index.column()
        sug = self.suggestions[row]

        # Tag Column
        if col == 0:
            match role:
                case Qt.ItemDataRole.DisplayRole:
                    return f"{sug.tag} → {sug.aliasFor}" if sug.aliasFor else sug.tag

                case Qt.ItemDataRole.EditRole:
                    return sug.aliasFor or sug.tag

        # Category Column
        else:
            match role:
                case Qt.ItemDataRole.DisplayRole:
                    return self.CATEGORY.get(sug.category, self.CATEGORY_DEFAULT).name

                case Qt.ItemDataRole.ForegroundRole:
                    return self.CATEGORY.get(sug.category, self.CATEGORY_DEFAULT).color

                case Qt.ItemDataRole.FontRole:
                    return self.categoryFont

                case Qt.ItemDataRole.TextAlignmentRole:
                    return Qt.AlignmentFlag.AlignVCenter

        return None



class AutoCompletePopup(QTableView):
    def __init__(self):
        super().__init__()
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        qtlib.setMonospace(self)

        self.setSelectionBehavior(self.SelectionBehavior.SelectRows)
        self.setSelectionMode(self.SelectionMode.SingleSelection)
        self.setEditTriggers(self.EditTrigger.NoEditTriggers)

        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(1)

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def updateWidth(self):
        self.resizeColumnsToContents()
        col0w = self.columnWidth(0) + 12
        self.setColumnWidth(0, col0w)
        return col0w + self.columnWidth(1) + self.verticalScrollBar().sizeHint().width() + 2

    def changeSelection(self, offset: int):
        index = self.currentIndex()
        row = (index.row() + offset) % self.model().rowCount()
        self.selectRow(row)



class TextEditCompleter:
    MIN_PREFIX_LEN = 2
    IGNORE_KEYS = (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, Qt.Key.Key_Shift)

    PUNCTUATION = ",.:;!?()[]"
    PUNCTUATION_STRIP = PUNCTUATION + " \t\n"

    COMPLETE_INTERVAL = 30 # ms
    COMPLETE_INTERVAL_NS = COMPLETE_INTERVAL * 1_000_000

    def __init__(self, textEdit: QPlainTextEdit, autoCompleteSources: list[AutoCompleteSource], separator: str = ", "):
        self.textEdit = textEdit
        self.separator = separator

        self.model = AutoCompleteModel(autoCompleteSources, parent=textEdit)

        self.completer = QCompleter(self.model, parent=textEdit)
        self.completer.setPopup(AutoCompletePopup())
        self.completer.setMaxVisibleItems(10)
        self.completer.setWidget(textEdit)
        self.completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self._insertCompletion)

        self._timer = QTimer(textEdit, singleShot=True, interval=self.COMPLETE_INTERVAL)
        self._timer.timeout.connect(self._updateComplete)
        self._tLastComplete = 0


    def isActive(self) -> bool:
        return self.completer.popup().isVisible()

    def hide(self):
        self.completer.popup().hide()


    @Slot(str)
    def _insertCompletion(self, text: str):
        numWords = len(text.replace("-", " ").split(" "))

        cursor = self.textEdit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Left)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.MoveAnchor)
        cursorPos = cursor.position()

        for _ in range(100):
            if cursor.atBlockEnd():
                text += self.separator
                break

            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor)
            selectedText = cursor.selectedText().strip()
            if selectedText:
                if selectedText[-1] not in self.PUNCTUATION:
                    text += " "

                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor)
                break

        cursor.clearSelection()
        cursor.setPosition(cursorPos, QTextCursor.MoveMode.KeepAnchor)

        for _ in range(numWords):
            cursor.movePosition(QTextCursor.MoveOperation.WordLeft, QTextCursor.MoveMode.KeepAnchor)
            selectedText = cursor.selectedText().strip()
            if not selectedText:
                break

            if selectedText[0] in self.PUNCTUATION or cursor.atBlockStart():
                selectionLen = len(selectedText)
                selectedText = selectedText.lstrip(self.PUNCTUATION_STRIP) # Remove separator and whitespace after
                diffLen = selectionLen - len(selectedText)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, n=diffLen)
                break

        cursor.beginEditBlock()
        cursor.insertText(text)

        # Split ops in undo stack
        cursor.insertText(" ")
        cursor.deletePreviousChar()

        cursor.endEditBlock()
        self.textEdit.setTextCursor(cursor)


    def complete(self, ignoreMinimum: bool = False):
        popup: AutoCompletePopup = self.completer.popup()

        prefix = self.textUnderCursor()
        if not prefix or (not ignoreMinimum and len(prefix) < self.MIN_PREFIX_LEN):
            popup.hide()
            self._timer.stop()
            return

        if ignoreMinimum or prefix != self.completer.completionPrefix():
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
        width = popup.updateWidth()
        rect = self.textEdit.cursorRect()
        rect.setWidth(width)
        self.completer.complete(rect)

        self._tLastComplete = time.monotonic_ns()


    def textUnderCursor(self):
        cursor = self.textEdit.textCursor()
        #cursor.movePosition(QTextCursor.MoveOperation.EndOfWord, QTextCursor.MoveMode.MoveAnchor)

        for _ in range(100):
            cursor.movePosition(QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor)
            text = cursor.selectedText().lstrip()
            if not text or text[0] in self.PUNCTUATION or cursor.position() <= 0:
                break

        return text.lstrip(self.PUNCTUATION_STRIP) # Remove separator and whitespace after

    @Slot()
    def _resetSelection(self):
        popup: AutoCompletePopup = self.completer.popup()
        popup.setCurrentIndex(self.model.index(0, 0))
        popup.scrollToTop()


    def handleKeyPress(self, event: QKeyEvent) -> bool:
        if not self.isActive():
            return False

        key = event.key()
        if key in self.IGNORE_KEYS:
            event.ignore()
            return True

        match event.key():
            case Qt.Key.Key_Tab:     change = 1
            case Qt.Key.Key_Backtab: change = -1
            case _:
                return False

        popup: AutoCompletePopup = self.completer.popup()
        popup.changeSelection(change)
        event.accept()
        return True



class Suggestion(NamedTuple):
    tag: str
    category: int
    freq: int
    aliasFor: str
    scoreFactor: float
    nGramRatio: float

    def max(self, other: Suggestion) -> Suggestion:
        return Suggestion(
            self.tag,
            max(self.category, other.category),
            max(self.freq, other.freq),
            self.aliasFor or other.aliasFor,
            max(self.scoreFactor, other.scoreFactor),
            max(self.nGramRatio, other.nGramRatio)
        )


class TagData(NamedTuple):
    tag: str
    category: int
    freq: int
    aliasFor: str

    def toSuggestion(self, scoreFactor: float, nGramRatio: float):
        return Suggestion(self.tag, self.category, self.freq, self.aliasFor, scoreFactor, nGramRatio)

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, value: object) -> bool:
        return self is value


class AutoCompleteSource(ABC):
    # https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
    KAOMOJIS = {
        "0_0", "(o)_(o)", "+_+", "+_-", "._.", "<o>_<o>", "<|>_<|>", "=_=", ">_<", "3_3", "6_9", ">_o", "@_@", "^_^", "o_o", "u_u", "x_x", "|_|", "||_||"
    }

    @abstractmethod
    def getSuggestions(self, search: str) -> list[Suggestion]:
        ...



class NGramAutoCompleteSource(AutoCompleteSource):
    MIN_RATIO = 0.2
    MAX_RESULTS = 100

    def __init__(self, scoreFactor: float):
        super().__init__()
        self.scoreFactor = scoreFactor
        self.n = 3
        self.reset()

    def reset(self):
        self.ngrams = defaultdict[str, set[TagData]](set)

    def getNgrams(self, text: str) -> Iterable[str]:
        if len(text) < self.n:
            text = text.rjust(self.n, " ")

        for i in range(len(text) - self.n + 1):
            yield text[i:i+self.n]

    def addTag(self, tag: str, category: int, freq: int, aliasFor: str = ""):
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

        candidates = list[tuple[TagData, float]]()
        for tagData in candidateTags:
            tagNgrams = set(self.getNgrams(tagData.tag))

            intersect = len(searchNgrams & tagNgrams)
            union     = len(searchNgrams | tagNgrams)
            jaccardIndex = intersect/union

            if jaccardIndex >= self.MIN_RATIO:
                candidates.append((tagData, jaccardIndex))

        candidates.sort(key=lambda x: x[1], reverse=True)

        if len(candidates) > self.MAX_RESULTS:
            candidates = candidates[:self.MAX_RESULTS]

        #print(f"NUM N-GRAM CANDIDATES: {len(candidates)}, minRatio={candidates[-1][1] if candidates else 'N/A'})")
        # print("Candidate Tags:")
        # for i, (tag, ratio) in enumerate(candidateData, 1):
        #     print(f"{str(i):3} {tag} ({ratio:.4f})")

        return [tagData.toSuggestion(self.scoreFactor, ratio) for tagData, ratio in candidates]



class GroupNgramAutoCompleteSource(NGramAutoCompleteSource):
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
    INVALID_CHAR_TRANS = str.maketrans("", "", "[](){}")
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

                t = time.monotonic_ns()
                numTags, numAliases = self._loadCsv(path, existingTags)
                t = (time.monotonic_ns() - t) / 1_000_000
                print(f"AutoComplete: Loaded {numTags} tags ({numAliases} aliases) in {t:.2f} ms from '{path}'")

    def _loadCsv(self, path: str, existingTags: set[str]) -> tuple[int, int]:
        numTags = 0
        numAliases = 0

        with open(path, 'r', newline='') as csvFile:
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
                if not tag or tag in existingTags:
                    continue
                existingTags.add(tag)

                category = self.toInt(catGetter(row))
                freq     = self.toInt(freqGetter(row))

                self.addTag(tag, category, freq)
                numTags += 1

                for alias in aliasGetter(row).split(self.ALIAS_SEP):
                    if (alias := self.prepareTag(alias)) and alias not in existingTags:
                        existingTags.add(alias)
                        self.addTag(alias, category, 0, aliasFor=tag)
                        numAliases += 1

                if not (i % 500):
                    QThread.msleep(1)

        return numTags, numAliases

    def _detectColumns(self, csvFile) -> tuple[int, int, int, int, bool]:
        singleTag = Counter[int]()
        multiTag  = Counter[int]()
        smallNr   = Counter[int]()
        largeNr   = Counter[int]()

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
                elif val.translate(self.INVALID_CHAR_TRANS):
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
        QThread.msleep(100)
        csvSource = CsvNGramAutoCompleteSource()

        try:
            csvSource.load(self.FOLDER)
        finally:
            self.signals.done.emit((csvSource.ngrams,))
