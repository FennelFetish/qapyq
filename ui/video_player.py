from __future__ import annotations
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QRect, QRectF, QSizeF, QUrl, QTimer, QLoggingCategory
from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem, QGraphicsTextItem, QGraphicsItemGroup
from PySide6.QtGui import QPixmap, QMouseEvent, QWheelEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from lib import qtlib, colorlib
from .imgview import ImgView, MediaItemMixin

QLoggingCategory.setFilterRules("qt.multimedia=false\nqt.multimedia.*=false")

# TODO: Pause when switching tab

class VideoItem(QGraphicsVideoItem, MediaItemMixin):
    TYPE = MediaItemMixin.ItemType.Video

    def __init__(self, imgview: ImgView):
        super().__init__()
        self.imgview = imgview
        self._fps: float = 0.0
        self._mouseInside = False

        self.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)

        self.audioOutput = QAudioOutput(parent=self)
        self.player = QMediaPlayer(parent=self, videoOutput=self, audioOutput=self.audioOutput)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.player.mediaStatusChanged.connect(self._onMediaStatusChanged)
        self.player.errorOccurred.connect(self._onError)

        self.playbackControls = PlaybackControls(self.player)
        self.playbackControls.updateSize(imgview.viewport().rect())
        #self.playbackControls.seekThumbnail.thumbnailShown.connect(self._redrawMainViewport)

        self.videoSink().videoSizeChanged.connect(self._onVideoSizeChanged, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _onVideoSizeChanged(self):
        size = self.videoSink().videoSize()
        self.setSize(size)
        self.imgview.updateImageTransform()

    @Slot(QMediaPlayer.MediaStatus)
    def _onMediaStatusChanged(self, status: QMediaPlayer.MediaStatus):
        match status:
            case QMediaPlayer.MediaStatus.LoadingMedia:
                self._fps = 0.0

            case QMediaPlayer.MediaStatus.LoadedMedia:
                try:
                    meta = self.player.metaData()
                    self._fps = float( meta.value(QMediaMetaData.Key.VideoFrameRate) )
                except ValueError:
                    self._fps = 0.0

    @Slot(QMediaPlayer.Error, str)
    def _onError(self, error: QMediaPlayer.Error, errorMsg: str):
        print(f"Error while playing video ({error}): {errorMsg}")

    #@Slot()
    def _redrawMainViewport(self):
        # The GUI scene is rendered separately as overlay. It's not automatically redrawn when geometries change.
        # The viewport is redrawn when the video is playing. If paused -> force redraw of main view.
        if not self.player.isPlaying():
            self.imgview.viewport().update()


    @override
    def clearImage(self):
        super().clearImage()
        self.player.setSource(QUrl())

    @override
    def loadFile(self, path: str) -> bool:
        if not super().loadFile(path):
            return False

        self.player.setSource(path)
        self.player.play()

        self.playbackControls.seekThumbnail.loadFile(None)
        self.playbackControls.labelSeekTime.hide()
        return True

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
        frame = self.videoSink().videoFrame()
        if frame.isValid():
            return QPixmap.fromImage(frame.toImage())
        return QPixmap(self.size().toSize())

    @override
    def togglePlay(self):
        if self.player.isPlaying():
            self.player.pause()
            self._redrawMainViewport()
        else:
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

    def __init__(self, player: QMediaPlayer):
        super().__init__()
        self.player = player
        player.durationChanged.connect(self._onDurationChanged)
        player.positionChanged.connect(self._onPosChanged)
        player.playingChanged.connect(self._onPlayingChanged)
        player.seekableChanged.connect(self._onSeekableChanged)

        self._duration: int = 0
        self._seekable: bool = False
        self._expanded: bool = False

        # UI Elements
        self.seekBar = SeekBar()
        self.seekKnob = SeekKnob(self.KNOB_WIDTH, self.SEEK_BAR_HEIGHT)
        self.seekThumbnail = SeekThumbnail()

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
            self.seekThumbnail.requestThumbnail(path, x, sceneWidth, videoPos)

    def getVideoPosition(self, x: float) -> int:
        p = x / self.seekBar.rect().width()
        p = self._duration * p
        return round(p)

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
    COLOR_BG_EXPANDED = QtGui.QColor(80, 80, 80, 50)

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



class SeekThumbnail(QGraphicsVideoItem):
    THUMBNAIL_SIZE = 250

    #thumbnailShown = Signal()

    def __init__(self):
        super().__init__(aspectRatioMode=Qt.AspectRatioMode.IgnoreAspectRatio)

        self.player = QMediaPlayer(parent=self, videoOutput=self)
        self.player.errorOccurred.connect(self._onError)
        self.player.positionChanged.connect(self._onVideoPosChanged)
        self.videoSink().videoFrameChanged.connect(self._onVideoSizeChanged)

        self._requestedFile: str | None = None
        self._requestVideoPos = 0
        self._active = False

        self._updateTimer = QTimer(self, singleShot=True, interval=200)
        self._updateTimer.timeout.connect(self._doRequestThumbnail)

        self.setSize(QSizeF(self.THUMBNAIL_SIZE, self.THUMBNAIL_SIZE))
        #self.setOpacity(0.8)
        self.hide()

    @override
    def hide(self):
        self._active = False
        super().hide()

    def loadFile(self, path: str | None):
        self._requestedFile = path
        if path:
            self.player.setSource(path)
        else:
            self.player.setSource(QUrl())
            self.hide()

    def requestThumbnail(self, path: str, x: float, sceneWidth: float, videoPos: int):
        if path != self._requestedFile:
            self.loadFile(path)

        w = self.size().width()
        x = min(x, sceneWidth-w)
        self.setX(x)

        self._requestVideoPos = videoPos
        self._active = True

        if not self._updateTimer.isActive():
            self._updateTimer.start()

    @Slot()
    def _doRequestThumbnail(self):
        self.player.setPosition(self._requestVideoPos)

    @Slot()
    def _onVideoSizeChanged(self):
        size = self.videoSink().videoSize()
        ar = size.width() / size.height()
        if ar > 1:
            w = self.THUMBNAIL_SIZE
            h = w / ar
        else:
            h = self.THUMBNAIL_SIZE
            w = h * ar

        self.setSize(QSizeF(w, h))
        self.setY(-h)

    @Slot()
    def _onVideoPosChanged(self, pos: int):
        if self._active:
            self.player.play()
            self.player.pause()
            self.show()
            #self.thumbnailShown.emit()

    @Slot(QMediaPlayer.Error, str)
    def _onError(self, error: QMediaPlayer.Error, errorMsg: str):
        print(f"Error while retrieving video thumbnail ({error}): {errorMsg}")


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
