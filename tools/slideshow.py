import random
from typing import NamedTuple
from collections import deque
from itertools import islice
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QTimer, QRect
from config import Config
from lib.qtlib import GreenButton
from ui.imgview import ImgItem, MediaItemType
from .view import ViewTool


class HistoryEntry(NamedTuple):
    idx: int
    lcgState: int

    @staticmethod
    def initState(idx: int) -> 'HistoryEntry':
        return HistoryEntry(idx, idx)



# Linear congruential generator for random sequences without repeats
class LCG:
    # PCG Parameters
    A = 6364136223846793005  # 'a' must be (5 mod 8) and coprime to 'm' for full period
    #C = 1442695040888963407

    PERIODS = 1  # Increased periods adds randomness but also more repeats

    def __init__(self, count: int):
        self.count = max(count, 1)

        self.m = 1 << (self.count * self.PERIODS - 1).bit_length()
        self.a = self.A % self.m
        self.aInv = pow(self.a, -1, self.m)

        self.q = self.m // self.count
        self.bound = self.count * self.q

        # Randomizing c changes the order of the cycle. Must be odd.
        minC = (self.count // 8) | 1 if self.count >= 16 else 1
        self.c = random.randrange(minC, max(self.count, 2), 2)

        #print(f"m={self.m}, c={self.c}, a={self.a}, aInv={self.aInv}, q={self.q}, bound={self.bound}")

    def next(self, state: int) -> HistoryEntry:
        while True:
            state = (self.a * state + self.c) % self.m
            if state < self.bound:
                index = state // self.q
                return HistoryEntry(index, state)

    def prev(self, state: int) -> HistoryEntry:
        while True:
            state = (self.aInv * (state - self.c)) % self.m
            if state < self.bound:
                index = state // self.q
                return HistoryEntry(index, state)



class SlideshowTool(ViewTool):
    HISTORY_MAX_LENGTH = 300
    HISTORY_SEARCH_LENGTH = 30
    HISTORY_SEARCH_MIN_ATTEMPTS = 5

    HIDE_TIMEOUT = 600  # ms

    def __init__(self, tab):
        super().__init__(tab)
        self._lcg: LCG | None = None
        self._shuffle = Config.slideshowShuffle

        self._history: deque[HistoryEntry] = deque(maxlen=self.HISTORY_MAX_LENGTH)
        self._historyIndex = 0
        self._rememberHistory = True

        self._playTimer = QTimer(parent=self.tab.imgview)
        self._playTimer.timeout.connect(self.next)
        self.setInterval(Config.slideshowInterval)

        self._cursor = Qt.CursorShape.ArrowCursor
        self._cursorTimer = QTimer(parent=self.tab.imgview, singleShot=True, interval=self.HIDE_TIMEOUT)
        self._cursorTimer.timeout.connect(lambda: self.tab.imgview.setCursor(Qt.CursorShape.BlankCursor))

        self._toolbar = SlideshowToolbar(self)

        self._oldPixmap = None
        self._oldImageItem = None
        self._fade = Config.slideshowFade


    @Slot()
    def setInterval(self, seconds: float):
        ms = int(seconds*1000)
        self._playTimer.setInterval(ms)
        Config.slideshowInterval = seconds

    @Slot()
    def setShuffle(self, shuffle: bool):
        self._shuffle = shuffle
        Config.slideshowShuffle = shuffle
        self.resetHistory()

    @Slot()
    def setFade(self, fade: bool):
        self._fade = fade
        Config.slideshowFade = fade
        self._setOldPixmap()


    def _setOldPixmap(self):
        item = self._imgview.image
        if self._fade and item.TYPE == MediaItemType.Image:
            self._oldPixmap = item.pixmap()
        else:
            self._oldPixmap = None

    def _printHistory(self):
        history = ", ".join(
            f"[{entry.idx}, {entry.lcgState}]" if i == self._historyIndex else f"({entry.idx}, {entry.lcgState})"
            for i, entry in enumerate(self._history)
        )

        print(f"[{history}] @ {self._historyIndex}")


    @Slot()
    def next(self):
        #with self.tab.takeFocus() as filelist:
        filelist = self.tab.filelist
        if not self._shuffle:
            filelist.setNextFile()
            return

        filelist._lazyLoadFolder()
        self._historyIndex += 1

        if self._historyIndex < len(self._history):
            self._setIndexNoHistory(self._history[self._historyIndex].idx)
        elif filelist.getNumFiles() > 0:
            entry = self.getRandomEntry(self._history[-1].lcgState)
            self._history.append(entry)
            self._historyIndex = len(self._history) - 1
            self._setIndexNoHistory(entry.idx)
        else:
            self._historyIndex = 0

        #self._printHistory()

    def prev(self):
        #with self.tab.takeFocus() as filelist:
        filelist = self.tab.filelist
        if not self._shuffle:
            filelist.setPrevFile()
            return

        filelist._lazyLoadFolder()
        self._historyIndex -= 1

        if self._historyIndex >= 0:
            self._setIndexNoHistory(self._history[self._historyIndex].idx)
        elif filelist.getNumFiles() > 0:
            entry = self.getRandomEntry(self._history[0].lcgState, forward=False)
            self._history.appendleft(entry)
            self._historyIndex = 0
            self._setIndexNoHistory(entry.idx)
        else:
            self._historyIndex = 0

        #self._printHistory()

    def getRandomEntry(self, state: int, forward: bool = True) -> HistoryEntry:
        filelist = self.tab.filelist
        numFiles = filelist.getNumFiles()
        if numFiles <= 0:
            return HistoryEntry(0, state)

        numSelectedFiles = len(filelist.selectedFiles)
        if numSelectedFiles > 1:
            numFiles = numSelectedFiles
            idxMap = lambda index: filelist.indexOf(filelist.selection.sorted[index])
        else:
            idxMap = lambda index: index

        lcg = self._getLCG(numFiles)
        if forward:
            lcgFunc = lcg.next
            history = reversed(self._history)
        else:
            lcgFunc = lcg.prev
            history = self._history

        searchLen = min(self.HISTORY_SEARCH_LENGTH, int(lcg.count * 0.9))
        region = set[int](entry.idx for entry in islice(history, searchLen))

        attempts = self.HISTORY_SEARCH_MIN_ATTEMPTS + random.randint(0, self.HISTORY_SEARCH_MIN_ATTEMPTS)
        for _ in range(1000):
            index, state = lcgFunc(state)
            index = idxMap(index)

            if index not in region:
                break

            if index != filelist.currentIndex:
                attempts -= 1
                if attempts <= 0:
                    break

        return HistoryEntry(index, state)

    def _getLCG(self, numFiles: int) -> LCG:
        if self._lcg is None or self._lcg.count != numFiles:
            self._lcg = LCG(numFiles)
        return self._lcg


    def resetHistory(self, addCurrent: bool = True):
        self._history.clear()
        self._historyIndex = 0
        self._lcg = None

        if addCurrent and self._shuffle:
            filelist = self.tab.filelist
            filelist._lazyLoadFolder()

            if filelist.selection:
                state = filelist.selection.sortedIndexOf(filelist.currentFile)
            else:
                state = filelist.currentIndex

            self._history.append(HistoryEntry(filelist.currentIndex, state))

        #self._printHistory()

    def _insertHistory(self, index: int):
        # Ensure max history size before inserting
        if len(self._history) >= self.HISTORY_MAX_LENGTH:
            if self._historyIndex > 0:
                self._history.popleft()
                self._historyIndex -= 1
            else:
                self._history.pop()

        lcgState = self._history[self._historyIndex].lcgState
        self._historyIndex += 1

        self._history.insert(self._historyIndex, HistoryEntry(index, lcgState))
        #self._printHistory()

    def _setIndexNoHistory(self, index: int):
        try:
            self._rememberHistory = False
            self.tab.filelist.setCurrentIndex(index)
        finally:
            self._rememberHistory = True


    def onFileChanged(self, currentFile: str):
        # When shuffle is enabled, remember manual image changes and insert the index at the current history position.
        if self._rememberHistory and self._shuffle and currentFile:
            self.tab.filelist._lazyLoadFolder()
            self._insertHistory(self.tab.filelist.currentIndex)

        if self._fade:
            if self._oldPixmap:
                self._oldImageItem.setPixmap(self._oldPixmap)
                self._oldImageItem.updateTransform(self._imgview.viewport().rect(), 0)
                self._oldImageItem.setZValue(1000)
                self._oldImageItem.startAnim()

            self._setOldPixmap()

        if self._playTimer.isActive():
            self._playTimer.start()

    def onFileListChanged(self, currentFile):
        self._oldPixmap = None
        self.resetHistory()

        try:
            self._rememberHistory = False
            self.onFileChanged(currentFile)
        finally:
            self._rememberHistory = True

    def onFileSelectionChanged(self, selectedFiles: set[str]):
        self.resetHistory()


    def getToolbar(self):
        return self._toolbar

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self.resetHistory()

        self.tab.statusBar().hide()
        self._toolbar.startHideTimeout()
        self.tab.filelist.addListener(self)
        self.tab.filelist.addSelectionListener(self)

        self._cursor = imgview.cursor()

        self._oldImageItem = FadeImgItem()
        imgview.scene().addItem(self._oldImageItem)
        self._setOldPixmap()

    def onDisabled(self, imgview):
        if self._playTimer.isActive():
            self._toolbar.togglePlay()

        self.tab.statusBar().show()
        self.tab.filelist.removeListener(self)
        self.tab.filelist.removeSelectionListener(self)

        self._cursorTimer.stop()
        imgview.setCursor(self._cursor)
        self._cursor = None

        imgview.scene().removeItem(self._oldImageItem)
        self._oldImageItem = None
        self._oldPixmap = None

        super().onDisabled(imgview)
        self.resetHistory(addCurrent=False)

    def onTabActive(self, active: bool):
        if not active and self._playTimer.isActive():
            self._toolbar.togglePlay()


    def onMouseMove(self, event: QtGui.QMouseEvent):
        super().onMouseMove(event)

        rect = self._toolbar.rect()
        match self.tab.toolBarArea(self._toolbar):
            case Qt.ToolBarArea.RightToolBarArea:  rect.adjust(80, 0, 0, 0)
            case Qt.ToolBarArea.LeftToolBarArea:   rect.adjust(0, 0, -80, 0)
            case Qt.ToolBarArea.BottomToolBarArea: rect.adjust(0, 80, 0, 0)
            case Qt.ToolBarArea.TopToolBarArea:    rect.adjust(0, 0, 0, -80)

        rect = QRect(self._toolbar.mapToGlobal(rect.topLeft()), rect.size())
        if rect.contains(event.globalPos()):
            self._toolbar.show()

        self._cursorTimer.start()
        self.tab.imgview.setCursor(self._cursor)

    def onMouseWheel(self, event: QtGui.QWheelEvent) -> bool:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False

        angleDelta = event.angleDelta().y()
        if angleDelta == 0:
            return False

        if angleDelta < 0:
            self.next()
        else:
            self.prev()
        return True

    def onMouseEnter(self, event):
        super().onMouseEnter(event)
        self._cursorTimer.start()

    def onMouseLeave(self, event):
        super().onMouseEnter(event)
        self._cursorTimer.stop()


    def onKeyPress(self, event: QtGui.QKeyEvent):
        match event.key():
            case Qt.Key.Key_Space:
                self._toolbar.togglePlay()
                self._toolbar.showBriefly()
            case Qt.Key.Key_Left:
                self.prev()
            case Qt.Key.Key_Right:
                self.next()
            case Qt.Key.Key_Up:
                self._toolbar.adjustInterval(1)
            case Qt.Key.Key_Down:
                self._toolbar.adjustInterval(-1)
            case Qt.Key.Key_0:
                self._imgview.resetView()
                self._imgview.updateView()



class SlideshowToolbar(QtWidgets.QToolBar):
    def __init__(self, slideshowTool: SlideshowTool):
        super().__init__()
        self._slideshowTool = slideshowTool

        self._hideTimer = QTimer()
        self._hideTimer.setSingleShot(True)
        self._hideTimer.timeout.connect(self._hideToolBar)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self.buildControls())

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def buildControls(self):
        self.btnPlay = GreenButton("▶")
        self.btnPlay.setFixedHeight(40)
        self.btnPlay.clicked.connect(self.togglePlay)

        self.spinInterval = QtWidgets.QDoubleSpinBox()
        self.spinInterval.setRange(0.1, 30.0)
        self.spinInterval.setSingleStep(0.5)
        self.spinInterval.setValue(Config.slideshowInterval)
        self.spinInterval.valueChanged.connect(self._slideshowTool.setInterval)

        chkShuffle = QtWidgets.QCheckBox()
        chkShuffle.setChecked(Config.slideshowShuffle)
        chkShuffle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chkShuffle.stateChanged.connect(self._slideshowTool.setShuffle)

        chkFade = QtWidgets.QCheckBox()
        chkFade.setChecked(Config.slideshowFade)
        chkFade.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        chkFade.stateChanged.connect(self._slideshowTool.setFade)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)

        layout.addWidget(self.btnPlay, 0, 0, 1, 2)

        lblInterval = QtWidgets.QLabel("Seconds:")
        layout.addWidget(lblInterval, 1, 0)
        layout.addWidget(self.spinInterval, 1, 1)

        lblShuffle = QtWidgets.QLabel("Shuffle:")
        layout.addWidget(lblShuffle, 2, 0)
        layout.addWidget(chkShuffle, 2, 1)

        lblFade = QtWidgets.QLabel("Fade:")
        layout.addWidget(lblFade, 3, 0)
        layout.addWidget(chkFade, 3, 1)

        group = QtWidgets.QGroupBox("Slideshow")
        group.setLayout(layout)
        return group

    def showBriefly(self):
        if not self.underMouse():
            self.show()
            self.startHideTimeout()

    def adjustInterval(self, steps):
        interval = self.spinInterval.value() + (self.spinInterval.singleStep() * steps)
        self.spinInterval.setValue(interval)
        self.showBriefly()

    @Slot()
    def togglePlay(self):
        timer = self._slideshowTool._playTimer
        if timer.isActive():
            timer.stop()
            self.btnPlay.setText("▶")
            self.btnPlay.setChanged(False)
        else:
            timer.start()
            self.btnPlay.setText("■") # ❚❚
            self.btnPlay.setChanged(True)


    @Slot()
    def _hideToolBar(self):
        if not self.isFloating():
            self.hide()

    def startHideTimeout(self):
        self._hideTimer.start(SlideshowTool.HIDE_TIMEOUT)

    def enterEvent(self, event):
        self._hideTimer.stop()

    def leaveEvent(self, event):
        self.startHideTimeout()



class FadeImgItem(ImgItem):
    def __init__(self):
        super().__init__()

        self.timer = QTimer()
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.anim)

    def startAnim(self):
        self.setVisible(True)
        self.setOpacity(1.0)
        self.timer.start()

    def anim(self):
        opacity = self.opacity() - 0.12
        if opacity <= 0.0:
            self.timer.stop()
            self.setVisible(False)
        else:
            self.setOpacity(opacity)
