from PySide6 import QtGui
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QTimer
import random
from .view import ViewTool


class SlideshowTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._shuffle = False
        self._hideTimeout = 600

        self._history = [] # Indices
        self._historyIndex = 0

        self._playTimer = QTimer()
        self._playTimer.setInterval(4000)
        self._playTimer.timeout.connect(self.next)

        self._cursor = Qt.CursorShape.ArrowCursor
        self._cursorTimer = QTimer()
        self._cursorTimer.setInterval(self._hideTimeout)
        self._cursorTimer.timeout.connect(lambda: self.tab.imgview.setCursor(Qt.CursorShape.BlankCursor))

        self._toolbar = SlideshowToolbar(self)


    @Slot()
    def setInterval(self, seconds):
        ms = int(seconds*1000)
        self._playTimer.setInterval(ms)

    @Slot()
    def setShuffle(self, shuffle):
        self.resetHistory()
        self._shuffle = shuffle


    @Slot()
    def next(self):
        if not self._shuffle:
            self.tab.filelist.setNextFile()
            return

        self._historyIndex += 1
        if self._historyIndex < len(self._history):
            self.tab.filelist.setCurrentIndex(self._history[self._historyIndex])
        elif (numFiles := self.tab.filelist.getNumFiles()) > 0:
            index = self.getRandomIndex()
            self.tab.filelist.setCurrentIndex(index)
            self._history.append(index)
        

    def prev(self):
        if not self._shuffle:
            self.tab.filelist.setPrevFile()
            return

        self._historyIndex -= 1
        if self._historyIndex >= 0:
            self.tab.filelist.setCurrentIndex(self._history[self._historyIndex])
        elif (numFiles := self.tab.filelist.getNumFiles()) > 0:
            self._historyIndex = 0
            index = self.getRandomIndex(False)
            self.tab.filelist.setCurrentIndex(index)
            self._history.insert(0, index)

    def getRandomIndex(self, tail=True) -> int:
        numFiles = self.tab.filelist.getNumFiles()
        if numFiles <= 0:
            return 0
        
        region = self._history[-10:] if tail else self._history[:10]
        attempts = 3
        while attempts > 0 and (index := random.randint(0, numFiles-1)) in region:
            attempts -= 1
        return index
        
    def resetHistory(self):
        self._history.clear()
        self._historyIndex = 0


    def getToolbar(self):
        return self._toolbar

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self.tab.statusBar().hide()
        self._toolbar.startHideTimeout()

        self._cursor = self.tab.imgview.cursor()

    def onDisabled(self, imgview):
        self._playTimer.stop()
        self.resetHistory()
        self.tab.statusBar().show()

        self.tab.imgview.setCursor(self._cursor)
        self._cursor = None


    def onMouseMove(self, event):
        super().onMouseMove(event)
        w = self._imgview.width()
        if event.position().x() > w-80:
            self._toolbar.show()

        self._cursorTimer.start()
        self.tab.imgview.setCursor(self._cursor)

    def onMouseWheel(self, event) -> bool:
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False

        angleDelta = event.angleDelta().y()
        if angleDelta == 0:
            return False

        if angleDelta < 0:
            self.next()
        else:
            self.prev()
        
        if self._playTimer.isActive():
            self._playTimer.start()
        return True

    def onMouseEnter(self, event):
        super().onMouseEnter(event)
        self._cursorTimer.start()

    def onMouseLeave(self, event):
        super().onMouseEnter(event)
        self._cursorTimer.stop()

    
    def onKeyPress(self, event):
        #super().onKeyPress(event)
        key = event.key()
        if key == Qt.Key_Space:
            self._toolbar.togglePlay()
            self._toolbar.showBriefly()
        elif key == Qt.Key_Left:
            self.prev()
            if self._playTimer.isActive():
                self._playTimer.start()
        elif key == Qt.Key_Right:
            self.next()
            if self._playTimer.isActive():
                self._playTimer.start()
        elif key == Qt.Key_Up:
            self._toolbar.adjustInterval(1)
        elif key == Qt.Key_Down:
            self._toolbar.adjustInterval(-1)



class SlideshowToolbar(QtWidgets.QToolBar):
    def __init__(self, slideshowTool):
        super().__init__()
        self._slideshowTool = slideshowTool

        self._hideTimer = QTimer()
        self._hideTimer.setSingleShot(True)
        self._hideTimer.timeout.connect(lambda: self.hide())

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self.buildControls())

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def buildControls(self):
        self.btnPlay = QtWidgets.QPushButton("▶")
        self.btnPlay.setStyleSheet("border:2px outset grey; border-radius: 8px")
        self.btnPlay.setFixedHeight(40)
        self.btnPlay.clicked.connect(self.togglePlay)

        self.spinInterval = QtWidgets.QDoubleSpinBox()
        self.spinInterval.setRange(0.1, 20.0)
        self.spinInterval.setSingleStep(0.5)
        self.spinInterval.setValue(4.0)
        self.spinInterval.valueChanged.connect(self._slideshowTool.setInterval)

        chkShuffle = QtWidgets.QCheckBox()
        chkShuffle.setFocusPolicy(Qt.NoFocus)
        chkShuffle.stateChanged.connect(self._slideshowTool.setShuffle)

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
            self.btnPlay.setStyleSheet("border:2px outset grey; border-radius: 8px")
        else:
            timer.start()
            self.btnPlay.setText("❚❚")
            self.btnPlay.setStyleSheet("border:2px outset green; border-radius: 8px")

    def startHideTimeout(self):
        self._hideTimer.start(self._slideshowTool._hideTimeout)
    
    def enterEvent(self, event):
        self._hideTimer.stop()

    def leaveEvent(self, event):
        self.startHideTimeout()
