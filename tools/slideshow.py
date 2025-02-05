from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QTimer
import random
from config import Config
from lib.qtlib import GreenButton
from ui.imgview import ImgItem
from .view import ViewTool


class SlideshowTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._shuffle = Config.slideshowShuffle
        self._hideTimeout = 600

        self._history = [] # Indices
        self._historyIndex = 0

        self._playTimer = QTimer()
        self._playTimer.timeout.connect(self.next)
        self.setInterval(Config.slideshowInterval)

        self._cursor = Qt.CursorShape.ArrowCursor
        self._cursorTimer = QTimer()
        self._cursorTimer.setInterval(self._hideTimeout)
        self._cursorTimer.timeout.connect(lambda: self.tab.imgview.setCursor(Qt.CursorShape.BlankCursor))

        self._toolbar = SlideshowToolbar(self)
        self._toolbar.setFloatable(False)
        self._toolbar.setMovable(False)

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
        self.resetHistory()
        self._shuffle = shuffle
        Config.slideshowShuffle = shuffle

    @Slot()
    def setFade(self, fade: bool):
        self._fade = fade
        Config.slideshowFade = fade


    @Slot()
    def next(self):
        with self.tab.takeFocus() as filelist:
            if not self._shuffle:
                filelist.setNextFile()
                return

            filelist._lazyLoadFolder()
            self._historyIndex += 1
            if self._historyIndex < len(self._history):
                filelist.setCurrentIndex(self._history[self._historyIndex])
            elif filelist.getNumFiles() > 0:
                index = self.getRandomIndex()
                filelist.setCurrentIndex(index)
                self._history.append(index)


    def prev(self):
        with self.tab.takeFocus() as filelist:
            if not self._shuffle:
                filelist.setPrevFile()
                return

            filelist._lazyLoadFolder()
            self._historyIndex -= 1
            if self._historyIndex >= 0:
                filelist.setCurrentIndex(self._history[self._historyIndex])
            elif filelist.getNumFiles() > 0:
                self._historyIndex = 0
                index = self.getRandomIndex(False)
                filelist.setCurrentIndex(index)
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
        self._history = list()
        self._historyIndex = 0


    def onFileChanged(self, currentFile):
        if self._fade and self._oldPixmap:
            self._oldImageItem.setPixmap(self._oldPixmap)
            self._oldImageItem.updateTransform(self._imgview.viewport().rect(), 0)
            self._oldImageItem.startAnim()
        self._oldPixmap = self._imgview.image.pixmap()

        if self._playTimer.isActive():
            self._playTimer.start()

    def onFileListChanged(self, currentFile):
        self.resetHistory()

        self._oldPixmap = None
        self.onFileChanged(currentFile)


    def getToolbar(self):
        return self._toolbar

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self.tab.statusBar().hide()
        self._toolbar.startHideTimeout()
        self.tab.filelist.addListener(self)

        self._cursor = imgview.cursor()

        self._oldImageItem = FadeImgItem()
        imgview.scene().addItem(self._oldImageItem)
        self._oldPixmap = imgview.image.pixmap()

    def onDisabled(self, imgview):
        if self._playTimer.isActive():
            self._toolbar.togglePlay()

        self.resetHistory()
        self.tab.statusBar().show()
        self.tab.filelist.removeListener(self)

        imgview.setCursor(self._cursor)
        self._cursor = None

        imgview.scene().removeItem(self._oldImageItem)
        self._oldImageItem = None
        self._oldPixmap = None


    def onMouseMove(self, event):
        super().onMouseMove(event)
        w = self._imgview.width()
        if event.position().x() > w-80:
            self._toolbar.show()

        self._cursorTimer.start()
        self.tab.imgview.setCursor(self._cursor)

    def onMouseWheel(self, event) -> bool:
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


    def onKeyPress(self, event):
        #super().onKeyPress(event)
        key = event.key()
        if key == Qt.Key_Space:
            self._toolbar.togglePlay()
            self._toolbar.showBriefly()
        elif key == Qt.Key_Left:
            self.prev()
        elif key == Qt.Key_Right:
            self.next()
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
        chkShuffle.setFocusPolicy(Qt.NoFocus)
        chkShuffle.stateChanged.connect(self._slideshowTool.setShuffle)

        chkFade = QtWidgets.QCheckBox()
        chkFade.setChecked(Config.slideshowFade)
        chkFade.setFocusPolicy(Qt.NoFocus)
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
            self.btnPlay.setText("❚❚")
            self.btnPlay.setChanged(True)

    def startHideTimeout(self):
        self._hideTimer.start(self._slideshowTool._hideTimeout)

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
