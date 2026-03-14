from __future__ import annotations
import cv2 as cv
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QRect, QRectF, QSize, QUrl, QTimer, QLoggingCategory, QObject, QRunnable, QThreadPool, QMutex, QMutexLocker
from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QGraphicsItemGroup, QGraphicsPixmapItem
from PySide6.QtGui import QPixmap, QImage, QMouseEvent, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from lib import qtlib, colorlib
from .imgview import ImgView, MediaItemMixin

QLoggingCategory.setFilterRules("qt.multimedia=false\nqt.multimedia.*=false")

class VideoLoadError(Exception): pass


class VideoItem(QGraphicsVideoItem, MediaItemMixin):
    TYPE = MediaItemMixin.ItemType.Video

    def __init__(self, imgview: ImgView):
        super().__init__()
        self.imgview = imgview

        self._fps: float = 0.0
        self._playing = False
        self._mouseInside = False

        self.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.setSize(QSize(-1, -1))

        self.audioOutput = QAudioOutput(parent=self)
        self.player = QMediaPlayer(parent=self, videoOutput=self, audioOutput=self.audioOutput)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.mediaStatusChanged.connect(self._onMediaStatusChanged, Qt.ConnectionType.QueuedConnection)
        self.player.errorOccurred.connect(self._onError, Qt.ConnectionType.QueuedConnection)

        self.capture = cv.VideoCapture()
        self.captureMutex = QMutex()

        self.playbackControls = PlaybackControls(self)
        self.playbackControls.updateSize(imgview.viewport().rect())
        self.playbackControls.seekThumbnail.signals.thumbnailShown.connect(self._redrawMainViewport)

    @override
    def deleteLater(self):
        with QMutexLocker(self.captureMutex):
            self.capture.release()

        super().deleteLater()


    @Slot(QMediaPlayer.MediaStatus)
    def _onMediaStatusChanged(self, status: QMediaPlayer.MediaStatus):
        match status:
            case QMediaPlayer.MediaStatus.LoadingMedia:
                self._fps = 0.0

            case QMediaPlayer.MediaStatus.LoadedMedia:
                try:
                    meta = self.player.metaData()
                    self._fps = float( meta.value(QMediaMetaData.Key.VideoFrameRate) )
                except (ValueError, TypeError):
                    self._fps = 0.0

    @Slot(QMediaPlayer.Error, str)
    def _onError(self, error: QMediaPlayer.Error, errorMsg: str):
        print(f"Error while playing video ({error}): {errorMsg}")

    @Slot()
    def _redrawMainViewport(self):
        # The GUI scene is rendered separately as overlay. It's not automatically redrawn when geometries change.
        # The viewport is redrawn when the video is playing. If paused -> force redraw of main view.
        if not self.player.isPlaying():
            self.imgview.viewport().update()


    @override
    def clearImage(self):
        super().clearImage()
        self.player.setSource(QUrl())
        self.setSize(QSize(-1, -1))

        with QMutexLocker(self.captureMutex):
            self.capture.release()

    @override
    def loadFile(self, path: str) -> bool:
        self._playing = False
        if not super().loadFile(path):
            return False

        try:
            with QMutexLocker(self.captureMutex):
                self.capture.open(path)
                if not self.capture.isOpened():
                    raise VideoLoadError()

                w = int(self.capture.get(cv.CAP_PROP_FRAME_WIDTH))
                h = int(self.capture.get(cv.CAP_PROP_FRAME_HEIGHT))

            if w < 0 or h < 0:
                raise VideoLoadError()
        except VideoLoadError:
            self.clearImage()
            return False

        self.setSize(QSize(w, h))

        self.player.setSource(path)
        self.player.play()
        self._playing = True

        self.playbackControls.seekThumbnail.onFileLoaded()
        self.playbackControls.seekThumbnail.hide()
        self.playbackControls.labelSeekTime.hide()
        return True

    @override
    def mediaSize(self) -> QSize:
        return self.size().toSize()

    @override
    def addToScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        scene.addItem(self)
        guiScene.addItem(self.playbackControls)

    @override
    def removeFromScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        scene.removeItem(self)
        guiScene.removeItem(self.playbackControls)

    @override
    def updateTransform(self, vpRect: QRect | QRectF, rotation: float):
        super().updateTransform(vpRect, rotation)
        self.playbackControls.updateSize(vpRect)


    def pixmap(self) -> QPixmap:
        # print(f"video pixmap @ {self.player.position()}")
        # import traceback
        # traceback.print_stack()

        #return self.playbackControls.seekThumbnail.extractFrame(self.filepath, self.player.position())

        # frame = self.videoSink().videoFrame()
        # if frame.isValid():
        #     return QPixmap.fromImage(frame.toImage())
        # return QPixmap(self.size().toSize())

        with QMutexLocker(self.captureMutex):
            self.capture.set(cv.CAP_PROP_POS_MSEC, self.player.position())
            ret, frame = self.capture.read()

        if ret:
            image = qtlib.numpyToQImage(frame)
            return QPixmap.fromImage(image)

        return QPixmap(self.size().toSize())


    @override
    def togglePlay(self):
        if self.player.isPlaying():
            self.player.pause()
            self._playing = False
            self._redrawMainViewport()
        else:
            self.player.play()
            self._playing = True

    @override
    def onTabActive(self, active: bool):
        if not active:
            self.player.pause()
        elif self._playing:
            self.player.play()


    @override
    def onMouseMove(self, event: QMouseEvent) -> bool:
        sceneW, sceneH = self.playbackControls.scene().sceneRect().size().toTuple()

        expanded = (event.pos().y() > sceneH - PlaybackControls.SEEK_BAR_HEIGHT_EXPANDED)
        expandedChanged = self.playbackControls.setExpanded(expanded)

        if expanded:
            x = self.playbackControls.mapFromParent(event.pos()).x()
            self.playbackControls.requestThumbnail(self.filepath, x, sceneW)
            self._redrawMainViewport()
        elif expandedChanged:
            self._redrawMainViewport()

        if expanded == self._mouseInside:
            self._mouseInside ^= True
            if self._mouseInside:
                self.imgview.tool.onMouseEnter(None)
            else:
                self.imgview.tool.onMouseLeave(None)

        return expanded

    @override
    def onMousePress(self, event: QMouseEvent) -> bool:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False

        pos = self.playbackControls.mapFromParent(event.pos())
        if self.playbackControls.seekBar.rect().contains(pos):
            p = self.playbackControls.getVideoPosition(pos.x())
            self.player.setPosition(p)
            return True

        return False

    @override
    def onMouseWheel(self, event: QWheelEvent) -> bool:
        if self.player.isPlaying():
            skip = min(5000, self.player.duration()/5)
        elif self._fps > 0.0:
            skip = 1000.0 / self._fps
        else:
            skip = 0

        skipSteps = -event.angleDelta().y() / 120.0 # 8*15° standard

        videoPos = self.player.position() + (skipSteps * skip)
        self.player.setPosition(round(videoPos))
        return True


    @override
    def onMouseEnter(self):
        self._mouseInside = True

    @override
    def onMouseLeave(self):
        self._mouseInside = False

        self.playbackControls.seekThumbnail.hide()
        if self.playbackControls.setExpanded(False):
            self._redrawMainViewport()



class PlaybackControls(QGraphicsItemGroup):
    SEEK_BAR_HEIGHT = 10
    SEEK_BAR_HEIGHT_EXPANDED = 40
    KNOB_WIDTH = 4
    KNOB_X_OFFSET = -KNOB_WIDTH//2

    def __init__(self, videoItem: VideoItem):
        super().__init__()
        self.player = videoItem.player
        self.player.positionChanged.connect(self._onPosChanged)
        self.player.durationChanged.connect(self._onDurationChanged, Qt.ConnectionType.QueuedConnection)
        self.player.playingChanged.connect(self._onPlayingChanged, Qt.ConnectionType.QueuedConnection)
        self.player.seekableChanged.connect(self._onSeekableChanged, Qt.ConnectionType.QueuedConnection)

        self._duration: int = 0
        self._seekable: bool = False
        self._expanded: bool = False

        # UI Elements
        self.seekBar = SeekBar()
        self.seekKnob = SeekKnob(self.KNOB_WIDTH, self.SEEK_BAR_HEIGHT)
        self.seekThumbnail = OpenCvSeekThumbnail(videoItem)

        self.addToGroup(self.seekBar)
        self.addToGroup(self.seekKnob)
        self.addToGroup(self.seekThumbnail)

        # Text Labels
        palette = QtWidgets.QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)

        textColor = QtGui.QColor(colorlib.BUBBLE_TEXT)
        textColor.setAlphaF(0.5)
        self.labelDuration = TimeLabel(textColor)
        self.labelPlayTime = TimeLabel(textColor)
        self.labelSeekTime = TimeLabel(highlightColor)

        self.addToGroup(self.labelDuration)
        self.addToGroup(self.labelPlayTime)
        self.addToGroup(self.labelSeekTime)


    def updateSize(self, rect: QRect | QRectF):
        rectW, rectH = rect.size().toTuple()
        self.prepareGeometryChange()

        self.setPos(0, rectH - self.SEEK_BAR_HEIGHT_EXPANDED + 6)  # +6 because otherwise it doesn't reach all the way to the bottom

        if self._expanded:
            h = self.SEEK_BAR_HEIGHT_EXPANDED
            y = 0
        else:
            h = self.SEEK_BAR_HEIGHT
            y = self.SEEK_BAR_HEIGHT_EXPANDED - self.SEEK_BAR_HEIGHT

        self.seekBar.setRect(0, y, rectW, h)
        self.seekKnob.setRect(0, y, self.KNOB_WIDTH, h)
        self.seekThumbnail.hide()
        self._onPosChanged(self.player.position())

        self.labelDuration.setPos(rectW - self.labelDuration.boundingRect().width(), 16)
        self.labelPlayTime.setPos(0, 16)
        self.labelSeekTime.setY(-2)
        self.labelSeekTime.hide()

    def setExpanded(self, expanded: bool) -> bool:
        'Returns whether expanded value has changed.'
        if self._expanded == expanded:
            return False

        self._expanded = expanded
        self.seekBar.setExpanded(expanded)
        self.updateSize(self.scene().sceneRect())

        for item in (self.seekThumbnail, self.labelSeekTime, self.labelDuration, self.labelPlayTime):
            item.setVisible(expanded)

        return True

    def requestThumbnail(self, path: str, x: float, sceneWidth: float):
        videoPos = self.getVideoPosition(x)

        self.labelSeekTime.setTime(videoPos)
        self.labelSeekTime.setBoundedX(x, sceneWidth)
        self.labelSeekTime.show()

        if self._seekable:
            self.seekThumbnail.requestThumbnail(x, sceneWidth, videoPos)
            self.seekThumbnail.show()

    def getVideoPosition(self, x: float) -> int:
        p = x / self.seekBar.rect().width()
        p = self._duration * p
        return round(p)


    # TODO: This is not a QObject -> Move slots

    @Slot(int)
    def _onDurationChanged(self, duration: int):
        self._duration = duration

        self.labelDuration.setTime(duration)
        self.labelDuration.setBoundedX(100_000_000, self.seekBar.rect().width())

    @Slot(int)
    def _onPosChanged(self, pos: int):
        if self._duration < 1:
            p = 0
        else:
            w = self.seekBar.rect().width()
            p = w * pos / self._duration

        self.seekKnob.setX(p + self.KNOB_X_OFFSET)
        self.labelPlayTime.setTime(pos)

    @Slot(bool)
    def _onPlayingChanged(self, playing: bool):
        self.labelPlayTime.suffix = " ▶" if playing else ""
        self.labelPlayTime.setTime(self.player.position())

    @Slot(bool)
    def _onSeekableChanged(self, seekable: bool):
        self._seekable = seekable


class SeekBar(QGraphicsRectItem):
    COLOR_BG          = QtGui.QColor(80, 80, 80, 20)
    COLOR_BG_EXPANDED = QtGui.QColor(80, 80, 80, 50)  # TODO: Better readability

    def __init__(self):
        super().__init__()
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(self.COLOR_BG)

    def setExpanded(self, extended: bool):
        self.setBrush(self.COLOR_BG_EXPANDED if extended else self.COLOR_BG)


class SeekKnob(QGraphicsRectItem):
    def __init__(self, width: int, height: int):
        super().__init__(0, 0, width, height)
        palette = QtWidgets.QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)
        highlightColor.setAlphaF(0.8)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(highlightColor)


class TimeLabel(QGraphicsTextItem):
    def __init__(self, color: QtGui.QColor):
        super().__init__("00:00")
        self.suffix: str = ""

        font = qtlib.getMonospaceFont()
        font.setPointSizeF(font.pointSizeF() * 0.9)

        self.setFont(font)
        self.setDefaultTextColor(color)
        self.hide()

    def setTime(self, timeMs: int):
        s = timeMs // 1000
        hours, s = divmod(s, 3600)
        minutes, seconds = divmod(s, 60)

        text = f"{hours:02}:{minutes:02}:{seconds:02}" if hours > 0 else f"{minutes:02}:{seconds:02}"
        self.setPlainText(text + self.suffix)

    def setBoundedX(self, x: float, sceneWidth: float):
        w = self.boundingRect().width()
        x = min(x, sceneWidth - w)
        self.setX(x)



class OpenCvSeekThumbnail(QGraphicsPixmapItem):
    class Signals(QObject):
        thumbnailShown = Signal()

    THUMBNAIL_SIZE = 250
    THUMBNAIL_INTERVAL = 100  # ms

    def __init__(self, videoItem: VideoItem):
        super().__init__(parent=videoItem)
        self.signals = self.Signals(parent=videoItem)
        self.videoItem = videoItem

        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self._thumbnailSize: QSize | None = None
        self._requestVideoPos: int = 0
        self._task: ThumbnailTask | None = None

        self._updateTimer = QTimer(videoItem, singleShot=True, interval=self.THUMBNAIL_INTERVAL)
        self._updateTimer.timeout.connect(self._startThumbnailTask)

        #self.setOpacity(0.9)
        self.hide()

    def onFileLoaded(self):
        if not self.pixmap().isNull():
            self.setPixmap(QPixmap())

        self._thumbnailSize = None
        w, h = self.videoItem.size().toSize().toTuple()
        if min(w, h) > 0:
            self._setThumbnailSize(w, h)

    def _setThumbnailSize(self, w: int, h: int):
        ar = w / h
        if ar > 1:
            w = self.THUMBNAIL_SIZE
            h = round(w / ar)
        else:
            h = self.THUMBNAIL_SIZE
            w = round(h * ar)

        self._thumbnailSize = QSize(w, h)
        self.setY(-h)

    def requestThumbnail(self, x: float, sceneWidth: float, videoPos: int):
        if self._thumbnailSize is None:
            return

        x = min(x, sceneWidth - self._thumbnailSize.width())
        self.setX(x)

        self._requestVideoPos = videoPos
        if not self._updateTimer.isActive():
            self._updateTimer.start()


    # TODO: This is not a QObject -> Move slots

    @Slot()
    def _startThumbnailTask(self):
        assert self._thumbnailSize is not None
        if self._task:
            return

        file = self.videoItem.filepath
        self._task = ThumbnailTask(self.videoItem.capture, self.videoItem.captureMutex, file, self._requestVideoPos, self._thumbnailSize)
        self._task.signals.done.connect(self._onThumbnailDone, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(self._task)

    @Slot(QImage)
    def _onThumbnailDone(self, image: QImage | None, file: str, pos: int):
        self._task = None
        if image is None or file != self.videoItem.filepath:
            return

        pixmap = QPixmap.fromImage(image)
        self.setPixmap(pixmap)
        self.signals.thumbnailShown.emit()

        if pos != self._requestVideoPos and not self._updateTimer.isActive():
            self._updateTimer.start()


class ThumbnailTask(QRunnable):
    class Signals(QObject):
        done = Signal(QImage, str, int)  # QImage|None, file, position

    def __init__(self, capture: cv.VideoCapture, mutex: QMutex, file: str, pos: int, size: QSize):
        super().__init__()
        self.setAutoDelete(True)
        self.signals = self.Signals()

        self.capture = capture
        self.mutex = mutex
        self.file = file
        self.pos = pos
        self.size = size

    def run(self):
        image = None
        try:
            with QMutexLocker(self.mutex):
                self.capture.set(cv.CAP_PROP_POS_MSEC, self.pos)
                ret, frame = self.capture.read()

            if ret:
                frame = cv.resize(frame, self.size.toTuple(), interpolation=cv.INTER_AREA)
                image = qtlib.numpyToQImage(frame)

        finally:
            self.signals.done.emit(image, self.file, self.pos)




# Thread name: MainThread, ident: 139877960665984
# Stack for thread 139877960665984
#   File "qapyq/./main.py", line 598, in <module>
#     exitCode = main()
#   File "qapyq/./main.py", line 590, in main
#     return app.exec()
#   File "qapyq/ui/imgview.py", line 173, in wheelEvent
#     if not (self._tool.onMouseWheel(event) or self.image.onMouseWheel(event)):
#   File "qapyq/tools/slideshow.py", line 355, in onMouseWheel
#     self.prev()
#   File "qapyq/tools/slideshow.py", line 157, in prev
#     self._setIndexNoHistory(self._history[self._historyIndex].idx)
#   File "qapyq/tools/slideshow.py", line 249, in _setIndexNoHistory
#     self.tab.filelist.setCurrentIndex(index)
#   File "qapyq/lib/filelist.py", line 497, in setCurrentIndex
#     self.notifyFileChanged()
#   File "qapyq/lib/filelist.py", line 621, in notifyFileChanged
#     l.onFileChanged(self.currentFile)
#   File "qapyq/ui/imgview.py", line 75, in onFileChanged
#     if self.image.loadFile(currentFile):
#   File "qapyq/ui/video_player.py", line 110, in loadFile
#     self.player.setSource(path)
#   File "qapyq/ui/video_player.py", line 363, in _onPlayingChanged
#     self.labelPlayTime.setTime(self.player.position())
#   File "qapyq/ui/video_player.py", line 412, in setTime
#     self.setPlainText(text + self.suffix)
#   File "<string>", line 3, in <module>
