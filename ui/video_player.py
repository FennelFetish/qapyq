from __future__ import annotations
from typing import NamedTuple, Callable, Type, TypeVar, Generic, TYPE_CHECKING
from typing_extensions import override
import av, math, traceback
from av.video.reformatter import Interpolation
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRect, QRectF, QSize, QUrl, QThread, QTimer, QObject, QSignalBlocker
from PySide6.QtGui import QPixmap, QImage, QColor, QMouseEvent, QWheelEvent, QSinglePointEvent, QPainter, QPen, QBrush
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudio
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsItemGroup, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem, QGraphicsObject,
    QApplication, QWidget, QStyleOptionGraphicsItem
)
from lib import qtlib, colorlib, videorw
from tools.tool import MediaEvent
from config import Config
from .imgview import ImgView, MediaItemType, MediaMetadata, MediaItemMixin

if TYPE_CHECKING:
    from av.container import InputContainer


VOLUME_SCALE = QAudio.VolumeScale.CubicVolumeScale


# ========== Base class and slots ==========

T = TypeVar("T", bound='VideoItemMixin')
class BaseSlots(QObject, Generic[T]):
    def __init__(self, videoItem: T, parent: QObject):
        super().__init__(parent)
        self.videoItem = videoItem

    def reset(self):
        pass

    @Slot(bool)
    def setPlaying(self, playing: bool):
        pass

    @Slot(float)
    def onPlaybackSpeedChanged(self, speed: float):
        self.videoItem.player.setPlaybackRate(speed)
        self.videoItem.imgview.tool.onMediaEvent(MediaEvent.PlaybackSpeedChanged)

    @Slot(str, QImage)
    def onThumbnailDone(self, file: str, image: QImage):
        if file == self.videoItem.filepath:
            pixmap = QPixmap.fromImage(image)
            self.videoItem.playbackControls.seekThumbnail.setPixmap(pixmap)
            self.videoItem._redrawMainViewport()


S = TypeVar("S", bound=BaseSlots)
class VideoItemMixin(MediaItemMixin, Generic[S]):
    TYPE = MediaItemType.Video

    def __init__(self, imgview: ImgView, slotsClass: Type[S], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.imgview = imgview
        self._slots: S = slotsClass(self, imgview.scene())

        self._size = QSize()

        self.player: QMediaPlayer = None
        self.audioOutput: QAudioOutput = None

    def _initMixin(self):
        self.menu = SeekContextMenu(self)
        self.menu.playToggled.connect(self._slots.setPlaying)
        self.menu.speedChanged.connect(self._slots.onPlaybackSpeedChanged)

        self.playbackControls = PlaybackControls(self)
        self.volumeControl = VolumeControl(self)
        self.info = MediaInfo(self)

        self._extractorThread = QThread()
        self._extractorThread.setObjectName("video-frame-extract")

        self.frameExtractor = FrameExtractWorker()
        self.frameExtractor.moveToThread(self._extractorThread)
        self.frameExtractor.thumbnailDone.connect(self._slots.onThumbnailDone, Qt.ConnectionType.QueuedConnection)
        self._extractorThread.start()

        self.playbackControls.updateSize(self.imgview.viewport().rect())

    def qtParent(self) -> QObject:
        return self._slots


    def _checkLoadVideo(self, size: QSize) -> bool:
        return size.isValid()

    def _loadVideo(self, path: str, duration: int):
        pass


    def _redrawMainViewport(self):
        # The GUI scene is rendered separately as overlay. It's not automatically redrawn when geometries change.
        # The viewport is redrawn when the video is playing. If paused -> force redraw of main view.
        self.imgview.viewport().update()

    def _updateVolume(self):
        self.volumeControl.setVolume(Config.mediaVolume, Config.mediaMute)
        self._redrawMainViewport()


    def setPlaying(self, playing: bool):
        self._slots.setPlaying(playing)

    def setVideoPosition(self, position: int) -> bool:
        self.player.setPosition(position)
        self.playbackControls.setMediaPosition(position, self.info.duration)
        return True

    def skipSteps(self, steps: int) -> int:
        segStart = self.info.segmentStart
        segEnd   = self.info.segmentEnd

        if self.player.isPlaying():
            duration = self.info.duration if segStart < 0 else segEnd - segStart
            skip = min(5000, duration/5)
        elif self.info.fps > 0.0:
            skip = 1000.0 / self.info.fps
        else:
            skip = 0

        skipLen = round(steps * skip)
        videoPos = self.player.position() + skipLen

        if segStart >= 0:
            if steps > 0 and videoPos > segEnd:
                diff = videoPos - segEnd
                videoPos = segEnd if diff < 10 else segStart
            elif steps < 0 and videoPos < segStart:
                diff = segStart - videoPos
                videoPos = segStart if diff < 10 else segEnd

        videoPos = max(min(videoPos, self.info.duration-1), 0)
        self.setVideoPosition(videoPos)
        return skipLen


    @property
    def segmentStart(self) -> int:
        return self.info.segmentStart

    @property
    def segmentEnd(self) -> int:
        return self.info.segmentEnd

    def setSegment(self, start: int, end: int, ensureLength: bool = True):
        length = end - start
        end = min(end, self.info.duration-1)

        if ensureLength and start >= 0:
            start = max(end - length, 0)

        self.info.segmentStart = start
        self.info.segmentEnd = end
        self.playbackControls.setSegment(start, end, self.info.duration)
        self._redrawMainViewport()

    def moveSegment(self, offset: int):
        if self.info.segmentStart < 0:
            return

        length = self.info.segmentEnd - self.info.segmentStart
        start  = max(self.info.segmentStart + offset, 0)
        end    = start + length
        self.setSegment(start, end)

    def clearSegment(self):
        self.setSegment(-1, -1)


    # ===== MediaItemMixin Interface =====

    @override
    def clearImage(self):
        super().clearImage()
        self.frameExtractor.unload()

    @override
    def loadFile(self, path: str) -> bool:
        if path == self.filepath:
            return True

        self.frameExtractor.unload()
        self.info.reset()
        self._slots.reset()
        self.clearSegment()

        if not super().loadFile(path):
            return False

        w, h, fps, frameCount, duration = videorw.readMetadata(path)

        self._size = QSize(w, h)
        if not self._checkLoadVideo(self._size):
            print(f"Failed to load video: {path}")
            self.clearImage()
            return False

        self._updateVolume()
        self.info.fps = fps
        self.info.frameCount = frameCount
        self.player.setPlaybackRate(1.0)

        self._loadVideo(path, duration)

        self.playbackControls.seekThumbnail.setPixmap(QPixmap())
        self.playbackControls.seekThumbnail.hide()
        self.playbackControls.labelSeekTime.hide()
        return True

    @override
    def mediaSize(self) -> QSize:
        return self._size

    @override
    def mediaMetadata(self) -> MediaMetadata:
        return MediaMetadata(False, self.info.fps, self.info.frameCount)

    @override
    def addToScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        super().addToScene(scene, guiScene)
        guiScene.addItem(self.playbackControls)
        guiScene.addItem(self.volumeControl)

    @override
    def removeFromScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        super().removeFromScene(scene, guiScene)
        guiScene.removeItem(self.playbackControls)
        guiScene.removeItem(self.volumeControl)

    @override
    def updateTransform(self, vpRect: QRect | QRectF, rotation: float):
        super().updateTransform(vpRect, rotation)
        self.playbackControls.updateSize(vpRect)
        self.volumeControl.updatePosition(vpRect, -PlaybackControls.SEEK_BAR_HEIGHT_EXPANDED)


    @override
    def onMouseMove(self, event: QMouseEvent) -> bool:
        mouseX, mouseY = event.pos().toTuple()

        mouseOverControls = self.playbackControls.isMouseOver(mouseY)
        redraw = self.playbackControls.setExpanded(mouseOverControls)

        if mouseOverControls:
            self.playbackControls.requestThumbnail(mouseX)
            redraw = True
            mouseOverVolume = False
        elif self.info.audio:
            mouseOverVolume = self.volumeControl.isMouseOver(mouseX, mouseY)
            if not self.volumeControl.isVisible():
                self.volumeControl.show()
                redraw = True
        else:
            mouseOverVolume = False

        self.volumeControl.setMouseOver(mouseOverVolume)
        if redraw:
            self._redrawMainViewport()

        return mouseOverControls | mouseOverVolume

    @override
    def onMousePress(self, event: QMouseEvent) -> bool:
        mouseX, mouseY = event.pos().toTuple()

        if self.playbackControls.isMouseOver(mouseY):
            match event.button():
                case Qt.MouseButton.LeftButton:
                    pos = self.playbackControls.getVideoPosition(mouseX)
                    if self.setVideoPosition(pos) and not self.info.insideSegment(pos):
                        self.imgview.tool.onMediaEvent(MediaEvent.SkipOutsideSegment)
                    return True

                case Qt.MouseButton.RightButton:
                    try:
                        self.playbackControls.keepExpanded = True
                        self.menu.exec(event.globalPos())
                    finally:
                        self.playbackControls.keepExpanded = False
                    return True

                case Qt.MouseButton.MiddleButton:
                    self.togglePlay()
                    return True

        if self.info.audio and self.volumeControl.isMouseOver(mouseX, mouseY):
            match event.button():
                case Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton:
                    Config.mediaMute ^= True
                    self._updateVolume()
                    return True

                case Qt.MouseButton.MiddleButton:
                    return True

        return False

    @override
    def onMouseWheel(self, event: QWheelEvent) -> bool:
        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        mouseX, mouseY = event.position().toPoint().toTuple()

        # Volume
        if self.volumeControl.isMouseOver(mouseX, mouseY):
            vol = Config.mediaVolume + (wheelSteps * 0.05)
            vol = min(max(vol, 0.0), 1.0)
            Config.mediaVolume = vol
            self._updateVolume()

        # Video Seek
        else:
            skipLen = self.skipSteps(-int(wheelSteps))
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self.moveSegment(skipLen)

        return True

    @override
    def onMouseEnter(self, event: QSinglePointEvent) -> bool:
        return self.playbackControls.isMouseOver( int(event.position().y()) )

    @override
    def onMouseLeave(self):
        self.playbackControls.seekThumbnail.hide()
        if self.playbackControls.setExpanded(False):
            self._redrawMainViewport()



# ========== VideoItem for video playback ==========

class VideoItemSlots(BaseSlots['VideoItem']):
    def __init__(self, videoItem: VideoItem, parent: QObject):
        super().__init__(videoItem, parent)
        self.playing = False

    @override
    def reset(self):
        self.playing = False

    @override
    @Slot(bool)
    def setPlaying(self, playing: bool):
        self.playing = playing
        if playing:
            self.videoItem.player.play()
        else:
            self.videoItem.player.pause()
            self.videoItem._redrawMainViewport()


class VideoItem(VideoItemMixin[VideoItemSlots], QGraphicsVideoItem):
    PLAYBACK = True

    def __init__(self, imgview: ImgView):
        super().__init__(imgview=imgview, slotsClass=VideoItemSlots)

        self.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.setSize(QSize())

        self.audioOutput = QAudioOutput(parent=self)
        self.player = QMediaPlayer(parent=self, videoOutput=self, audioOutput=self.audioOutput)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self._initMixin()

        self.info.videoStarted.connect(self._onVideoStarted)

    @override
    def deleteLater(self):
        self.frameExtractor.unload()
        super().deleteLater()

        self._extractorThread.quit()
        self._extractorThread.wait()
        self._extractorThread.deleteLater()

        self._slots.deleteLater()

    @override
    def _redrawMainViewport(self):
        if not self.player.isPlaying():
            super()._redrawMainViewport()

    @override
    def _updateVolume(self):
        super()._updateVolume()
        linVol = QAudio.convertVolume(Config.mediaVolume, VOLUME_SCALE, QAudio.VolumeScale.LinearVolumeScale)
        self.audioOutput.setVolume(linVol)
        self.audioOutput.setMuted(Config.mediaMute)

    @override
    def setVideoPosition(self, position: int) -> bool:
        if self.info.isVideoReady():
            return super().setVideoPosition(position)
        return False

    @override
    def _checkLoadVideo(self, size: QSize) -> bool:
        self.hide()
        self.setSize(size)
        return super()._checkLoadVideo(size)

    @override
    def _loadVideo(self, path: str, duration: int):
        self.player.setSource(QUrl.fromLocalFile(path))
        self.setPlaying(True)
        Config.mediaPlaybackStarted = True

    @Slot()
    def _onVideoStarted(self):
        self.show()

    # ===== MediaItemMixin Interface =====

    def pixmap(self) -> QPixmap:
        frame = self.player.videoSink().videoFrame()
        if not (frame.isValid() and frame.map(frame.MapMode.ReadOnly)):
            raise ValueError("Failed to retrieve video frame")

        try:
            img = frame.toImage()
        finally:
            frame.unmap()

        return QPixmap.fromImage(img)

    @override
    def clearImage(self):
        super().clearImage()
        self.player.setSource(QUrl())
        self.setSize(QSize())

    @override
    def togglePlay(self):
        self.setPlaying(not self.player.isPlaying())

    @override
    def onTabActive(self, active: bool):
        if active:
            self._updateVolume()
            if self._slots.playing:
                self.player.play()
        else:
            self.player.pause()



# ========== FrozenVideoItem witout video playback, only extracted frames ==========

class FrozenVideoItemSlots(BaseSlots['FrozenVideoItem']):
    def __init__(self, videoItem: FrozenVideoItem, parent: QObject):
        super().__init__(videoItem, parent)
        self._needsTransformUpdate = True

    @override
    def reset(self):
        self._needsTransformUpdate = True

    @override
    @Slot(bool)
    def setPlaying(self, playing: bool):
        if playing:
            self.videoItem.menu.updateValues()

    @Slot(str, QImage)
    def onFrameDone(self, file: str, image: QImage):
        if file == self.videoItem.filepath:
            pixmap = QPixmap.fromImage(image)
            self.videoItem.setPixmap(pixmap.copy())

            if self._needsTransformUpdate:
                self.videoItem.imgview.updateImageTransform()
                self._needsTransformUpdate = False
        else:
            self.videoItem.setPixmap(QPixmap())


class FrozenVideoItem(VideoItemMixin[FrozenVideoItemSlots], QGraphicsPixmapItem):
    PLAYBACK = False

    class DummyPlayer:
        def __init__(self):
            self._pos: int = 0
            self._speed: float = 1.0

        def isPlaying(self) -> bool:
            return False

        def position(self) -> int:
            return self._pos

        def setPosition(self, pos: int):
            self._pos = pos

        def playbackRate(self) -> float:
            return self._speed

        def setPlaybackRate(self, speed: float):
            self._speed = speed


    def __init__(self, imgview: ImgView):
        super().__init__(imgview=imgview, slotsClass=FrozenVideoItemSlots)

        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

        self.player = self.DummyPlayer()
        self.audioOutput = None
        self._initMixin()

        self.frameExtractor.frameDone.connect(self._slots.onFrameDone, Qt.ConnectionType.QueuedConnection)

    def deleteLater(self):
        self.frameExtractor.unload()
        self._extractorThread.quit()
        self._extractorThread.wait()
        self._extractorThread.deleteLater()
        self._slots.deleteLater()

    @override
    def setVideoPosition(self, position: int) -> bool:
        if self.info.isVideoReady():
            self.frameExtractor.requestFrame(self.filepath, position)
            return super().setVideoPosition(position)
        return False

    @override
    def _loadVideo(self, path: str, duration: int):
        self.info.duration = duration
        self.info.seekable = True
        self.info.audio = False
        self.info.setVideoReady()

        self.playbackControls.setMediaDuration(duration)
        self.playbackControls.setMediaPlaying(False, 0)
        self.menu.setMediaPlaying(False)
        self.setVideoPosition(0)

    # ===== MediaItemMixin Interface =====

    @override
    def clearImage(self):
        super().clearImage()
        if not self.pixmap().isNull():
            self.setPixmap(QPixmap())

    @override
    def setSmooth(self, enabled: bool):
        mode = Qt.TransformationMode.SmoothTransformation if enabled else Qt.TransformationMode.FastTransformation
        if mode != self.transformationMode():
            self.setTransformationMode(mode)


# ========== Common ==========

class MediaInfo(QObject):
    THUMBNAIL_ENABLE_DELAY = 150

    videoStarted = Signal()

    def __init__(self, videoItem: VideoItemMixin):
        super().__init__(videoItem.qtParent())
        self.videoItem = videoItem
        self.player = videoItem.player
        self.playbackControls = videoItem.playbackControls

        self.fps: float = 0.0
        self.frameCount: int = 0
        self.duration: int = 0
        self.audio: bool = False
        self.seekable: bool = False

        self.segmentStart: int = -1
        self.segmentEnd: int   = -1

        if isinstance(self.player, QMediaPlayer):
            self.player.mediaStatusChanged.connect(self._onMediaStatusChanged, Qt.ConnectionType.QueuedConnection)
            self.player.positionChanged.connect(self._onPosChanged, Qt.ConnectionType.QueuedConnection)
            self.player.durationChanged.connect(self._onDurationChanged, Qt.ConnectionType.QueuedConnection)
            self.player.playingChanged.connect(self._onPlayingChanged, Qt.ConnectionType.QueuedConnection)
            self.player.seekableChanged.connect(self._onSeekableChanged, Qt.ConnectionType.QueuedConnection)
            self.player.hasAudioChanged.connect(self._onHasAudioChanged, Qt.ConnectionType.QueuedConnection)
            self.player.errorOccurred.connect(self._onError, Qt.ConnectionType.QueuedConnection)

            videoItem.audioOutput.volumeChanged.connect(self._onVolumeChanged, Qt.ConnectionType.QueuedConnection)
            videoItem.audioOutput.mutedChanged.connect(self._onMutedChanged, Qt.ConnectionType.QueuedConnection)

        self.videoLoaded: bool = False
        self.thumbnailsEnabled: bool = False

        self._thumbnailDelay = QTimer(self, singleShot=True, interval=self.THUMBNAIL_ENABLE_DELAY)
        self._thumbnailDelay.timeout.connect(self._enableThumbnails)


    def reset(self):
        self.fps = 0.0
        self.frameCount = 0
        self.videoLoaded = False
        self.thumbnailsEnabled = False
        self._onDurationChanged(0)

    def insideSegment(self, pos: int):
        return self.segmentStart <= pos <= self.segmentEnd


    def isThumbnailsEnabled(self) -> bool:
        return self.thumbnailsEnabled & self.seekable & (self.duration > 0)

    @Slot()
    def _enableThumbnails(self):
        self.thumbnailsEnabled = (Config.mediaSeekThumbnailSize > 0)


    def isVideoReady(self) -> bool:
        return self.videoLoaded & self.seekable & (self.duration > 0)

    def setVideoReady(self):
        self.videoLoaded = True
        self._thumbnailDelay.start()
        self.videoStarted.emit()


    @Slot(QMediaPlayer.MediaStatus)
    def _onMediaStatusChanged(self, status: QMediaPlayer.MediaStatus):
        match status:
            case QMediaPlayer.MediaStatus.LoadedMedia:
                self.setVideoReady()

    @Slot("qint64")
    def _onDurationChanged(self, duration: int):
        self.duration = duration
        self.playbackControls.setMediaDuration(duration)

    @Slot("qint64")
    def _onPosChanged(self, pos: int):
        self.playbackControls.setMediaPosition(pos, self.duration)

        if self.segmentStart >= 0 and not self.insideSegment(pos):
            self.videoItem.setVideoPosition(self.segmentStart)

    @Slot(bool)
    def _onPlayingChanged(self, playing: bool):
        self.playbackControls.setMediaPlaying(playing, self.player.position())
        self.videoItem.menu.setMediaPlaying(playing)

        if not playing and self.segmentStart >= 0:
            self.videoItem.setVideoPosition(self.segmentStart)

    @Slot(bool)
    def _onSeekableChanged(self, seekable: bool):
        self.seekable = seekable

    @Slot(bool)
    def _onHasAudioChanged(self, audio: bool):
        self.audio = audio

    @Slot(QMediaPlayer.Error, str)
    def _onError(self, error: QMediaPlayer.Error, errorMsg: str):
        print(f"Error while playing video: {errorMsg} ({error})")

    @Slot("float")
    def _onVolumeChanged(self, volume: float):
        displayVol = QAudio.convertVolume(volume, QAudio.VolumeScale.LinearVolumeScale, VOLUME_SCALE)
        self.videoItem.volumeControl.setVolume(displayVol, self.videoItem.audioOutput.isMuted())

    @Slot(bool)
    def _onMutedChanged(self, muted: bool):
        volume = self.videoItem.audioOutput.volume()
        displayVol = QAudio.convertVolume(volume, QAudio.VolumeScale.LinearVolumeScale, VOLUME_SCALE)
        self.videoItem.volumeControl.setVolume(displayVol, muted)


class PlaybackControls(QGraphicsItemGroup):
    Y_OFFSET = 6  # move down, because otherwise it doesn't reach all the way to the bottom

    SEEK_BAR_HEIGHT = Y_OFFSET + 2
    SEEK_BAR_HEIGHT_EXPANDED = 40

    KNOB_WIDTH = 4
    KNOB_X_OFFSET = -KNOB_WIDTH//2


    def __init__(self, videoItem: VideoItemMixin):
        super().__init__()
        self.videoItem = videoItem

        self.keepExpanded: bool = False
        self._expanded: bool = False

        # UI Elements
        self.seekBar        = SeekBar()
        self.seekBarFull    = SeekBarFull()
        self.seekBarSeg     = SeekBarSegment()
        self.seekKnob       = SeekKnob(self.KNOB_WIDTH, self.SEEK_BAR_HEIGHT)
        self.seekThumbnail  = SeekThumbnail()

        self.addToGroup(self.seekBar)
        self.addToGroup(self.seekBarFull)
        self.addToGroup(self.seekKnob)
        self.addToGroup(self.seekThumbnail)

        # Text Labels
        textColor = QColor(colorlib.BUBBLE_TEXT)
        textColor.setAlphaF(0.7)
        self.labelDuration = TimeLabel(textColor)
        self.labelPlayTime = TimeLabel(textColor)
        self.labelSeekTime = TimeLabel(QColor(colorlib.BUBBLE_TEXT))

        self.addToGroup(self.labelDuration)
        self.addToGroup(self.labelPlayTime)
        self.addToGroup(self.labelSeekTime)

        self.addToGroup(self.seekBarSeg)


    def updateSize(self, rect: QRect | QRectF):
        rectW, rectH = rect.size().toTuple()
        self.prepareGeometryChange()

        self.setPos(0, rectH - self.SEEK_BAR_HEIGHT_EXPANDED + self.Y_OFFSET)

        if self._expanded:
            h = self.SEEK_BAR_HEIGHT_EXPANDED
        else:
            h = self.SEEK_BAR_HEIGHT

        y = self.SEEK_BAR_HEIGHT_EXPANDED - h

        self.seekBar.setRect(0, y, rectW, h)
        self.seekBarFull.setRect(0, y, 0, h)
        self.seekBarSeg.setRect(0, y, 0, h-5)
        self.seekKnob.setRect(0, y, self.KNOB_WIDTH, h)
        self.seekThumbnail.hide()

        info = self.videoItem.info
        self.setMediaPosition(self.videoItem.player.position(), info.duration)
        self.setSegment(info.segmentStart, info.segmentEnd, info.duration)

        self.labelDuration.setPos(rectW - self.labelDuration.boundingRect().width(), 16)
        self.labelPlayTime.setPos(0, 16)
        self.labelSeekTime.setY(-2)
        self.labelSeekTime.hide()


    def isMouseOver(self, mouseY: int) -> bool:
        sceneH = self.scene().sceneRect().height()
        return mouseY > sceneH - PlaybackControls.SEEK_BAR_HEIGHT_EXPANDED

    def setExpanded(self, expanded: bool) -> bool:
        'Returns whether expanded value has changed.'
        expanded |= self.keepExpanded
        if self._expanded == expanded:
            return False

        self._expanded = expanded
        self.seekBar.setExpanded(expanded)
        self.updateSize(self.scene().sceneRect())

        for item in (self.seekThumbnail, self.labelSeekTime, self.labelDuration, self.labelPlayTime):
            item.setVisible(expanded)

        return True


    def requestThumbnail(self, mouseX: float):
        sceneW = self.scene().sceneRect().width()
        videoPos = self.getVideoPosition(mouseX)

        self.labelSeekTime.setTime(videoPos)
        self.labelSeekTime.setBoundedX(mouseX, sceneW)
        self.labelSeekTime.show()

        if self.videoItem.info.isThumbnailsEnabled():
            self.videoItem.frameExtractor.requestThumbnail(self.videoItem.filepath, videoPos)
            self.seekThumbnail.setBoundedX(mouseX, sceneW)
            self.seekThumbnail.show()

    def getVideoPosition(self, x: float) -> int:
        p = x / self.seekBar.rect().width()
        p = self.videoItem.info.duration * p
        return round(p)


    def setMediaDuration(self, duration: int):
        self.labelDuration.setTime(duration)
        self.labelDuration.setBoundedX(100_000_000, self.seekBar.rect().width())

    def setMediaPlaying(self, playing: bool, pos: int):
        self.labelSeekTime.milliseconds = not playing

        self.labelPlayTime.suffix = " ▶" if playing else ""
        self.labelPlayTime.milliseconds = not playing
        self.labelPlayTime.setTime(pos)

    def setMediaPosition(self, pos: int, duration: int):
        if duration < 1:
            p = 0
        else:
            w = self.seekBar.rect().width()
            p = w * pos / duration

        rect = self.seekBarFull.rect()
        rect.setWidth(p)
        self.seekBarFull.setRect(rect)

        self.seekKnob.setX(p + self.KNOB_X_OFFSET)
        self.labelPlayTime.setTime(pos)

    def setSegment(self, start: int, end: int, duration: int):
        if max(start, end) < 0 or duration < 1:
            self.seekBarSeg.hide()
            return

        w = self.seekBar.rect().width()
        pStart = w * start / duration
        pEnd   = w * end / duration

        rect = self.seekBarSeg.rect()
        rect.setX(pStart)
        rect.setWidth(pEnd - pStart)
        self.seekBarSeg.setRect(rect)
        self.seekBarSeg.show()



class SeekBar(QGraphicsRectItem):
    COLOR_BG: QColor = None
    COLOR_BG_EXPANDED: QColor = None

    def __init__(self):
        super().__init__()
        self.setPen(Qt.PenStyle.NoPen)

        if SeekBar.COLOR_BG is None:
            SeekBar.COLOR_BG = QColor(colorlib.BUBBLE_BG)
            SeekBar.COLOR_BG.setAlphaF(0.1)

            SeekBar.COLOR_BG_EXPANDED = QColor(colorlib.BUBBLE_BG)
            SeekBar.COLOR_BG_EXPANDED.setAlphaF(0.5)

        self.setBrush(SeekBar.COLOR_BG)

    def setExpanded(self, expanded: bool):
        self.setBrush(self.COLOR_BG_EXPANDED if expanded else self.COLOR_BG)


class SeekBarFull(QGraphicsRectItem):
    def __init__(self):
        super().__init__()
        palette = QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)
        highlightColor.setAlphaF(0.5)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(highlightColor)


class SeekBarSegment(QGraphicsRectItem):
    def __init__(self):
        super().__init__()
        pen = QPen(colorlib.GREEN)
        self.setPen(pen)
        self.setBrush(Qt.BrushStyle.NoBrush)


class SeekKnob(QGraphicsRectItem):
    def __init__(self, width: int, height: int):
        super().__init__(0, 0, width, height)
        palette = QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(highlightColor)


class SeekThumbnail(QGraphicsPixmapItem):
    def __init__(self):
        super().__init__()
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    @override
    def setPixmap(self, pixmap: QPixmap | QImage):
        super().setPixmap(pixmap)
        self.setY(-pixmap.height())

    def setBoundedX(self, x: float, sceneWidth: float):
        w = self.boundingRect().width()
        x = min(x, sceneWidth - w)
        self.setX(x)


class TimeLabel(QGraphicsTextItem):
    FONT = None

    def __init__(self, color: QColor):
        super().__init__("00:00")
        self.suffix: str = ""
        self.milliseconds: bool = False

        if TimeLabel.FONT is None:
            font = qtlib.getMonospaceFont()
            font.setPointSizeF(font.pointSizeF() * 0.9)
            TimeLabel.FONT = font

        self.setFont(TimeLabel.FONT)
        self.setDefaultTextColor(color)
        self.hide()

    def setTime(self, timeMs: int):
        s, ms = divmod(timeMs, 1000)
        hours, s = divmod(s, 3600)
        minutes, seconds = divmod(s, 60)

        text = f"{minutes:02}:{seconds:02}.{ms:03}" if self.milliseconds else f"{minutes:02}:{seconds:02}"
        text = f"{hours:02}:{text}{self.suffix}"    if hours > 0         else text+self.suffix
        self.setPlainText(text)

    def setBoundedX(self, x: float, sceneWidth: float):
        w = self.boundingRect().width()
        x = min(x, sceneWidth - w)
        self.setX(x)


class VolumeControl(QGraphicsObject):
    RADIUS = 20

    PIXMAPS = list[QPixmap]()
    PIXMAP_RECT: QRect = None

    def __init__(self, videoItem: VideoItemMixin):
        super().__init__()
        self.videoItem = videoItem

        color = QColor(colorlib.BUBBLE_TEXT)
        if not self.PIXMAPS:
            self._initPixmaps(32, color)

        self._pixmap = self.PIXMAPS[1]

        color.setAlphaF(0.5)
        self._penBorder = QPen(color)
        self._penBorder.setWidthF(2.0)

        colorBg = QColor(colorlib.BUBBLE_BG)
        colorBg.setAlphaF(0.5)
        self._brushBg = QBrush(colorBg)

        colorFill = QColor(colorlib.BUBBLE_TEXT)
        colorFill.setAlphaF(0.35)
        self._brushFill = QBrush(colorFill)
        colorFill.setAlphaF(0.2)
        self._brushFillMute = QBrush(colorFill)

        self._chordStart: int = 0
        self._chordSpan: int  = 0
        self._chordBrush = self._brushFill

        self._hideTimer = QTimer(videoItem.qtParent(), singleShot=True, interval=600)
        self._hideTimer.timeout.connect(self._autohide)
        self.hide()

    @classmethod
    def _initPixmaps(cls, size: int, color: QColor):
        cls.PIXMAPS = [
            qtlib.loadSvg(size, size, "./res/volume-mute.svg", color),
            qtlib.loadSvg(size, size, "./res/volume-low.svg", color),
            qtlib.loadSvg(size, size, "./res/volume-medium.svg", color),
            qtlib.loadSvg(size, size, "./res/volume-high.svg", color)
        ]

        offset = ((cls.RADIUS * 2) - size) // 2
        cls.PIXMAP_RECT = QRect(offset, offset, size, size)


    @Slot()
    def _autohide(self):
        self.hide()
        self.videoItem._redrawMainViewport()

    def updatePosition(self, vpRect: QRect | QRectF, yOffset: int):
        # Place volume control on the opposite side of toolbar, otherwise autohide interferes
        toolbarRight = (qtlib.toolbarAreaFromString(Config.toolToolbarPosition) == Qt.ToolBarArea.RightToolBarArea)
        size = self.RADIUS * 2
        padX = 6

        x = padX if toolbarRight else (vpRect.width() - size - padX)
        y = vpRect.height() - size + yOffset
        self.setPos(x, y)

    def setVolume(self, volume: float, mute: bool):
        if mute:
            self._pixmap = self.PIXMAPS[0]
        elif volume >= 1.0:
            self._pixmap = self.PIXMAPS[3]
        elif volume > 0.0:
            self._pixmap = self.PIXMAPS[2]
        else:
            self._pixmap = self.PIXMAPS[1]

        self._chordBrush = self._brushFillMute if mute else self._brushFill

        cosVal = 1 - (2 * volume)
        cosVal = max(-1.0, min(cosVal, 1.0))
        angle = math.degrees(math.acos(cosVal))
        angle = round(angle * 16) # drawChord takes 1/16 deg as unit

        self._chordStart = (270*16) - angle
        self._chordSpan  = 2 * angle

    def isMouseOver(self, mouseX: int, mouseY: int) -> bool:
        center = self.sceneBoundingRect().center()
        dx = mouseX - center.x()
        dy = mouseY - center.y()
        return (dx*dx) + (dy*dy) < (self.RADIUS * self.RADIUS)

    def setMouseOver(self, mouseOver: bool):
        if mouseOver:
            self._hideTimer.stop()
        else:
            self._hideTimer.start()

    @override
    def show(self):
        super().show()
        self._hideTimer.start()

    @override
    def boundingRect(self) -> QRectF:
        size = self.RADIUS * 2
        return QRectF(0, 0, size, size)

    @override
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        rect = self.boundingRect()

        painter.setPen(self._penBorder)
        painter.setBrush(self._brushBg)
        painter.drawEllipse(rect)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._chordBrush)
        painter.drawChord(rect, self._chordStart, self._chordSpan)

        painter.drawPixmap(self.PIXMAP_RECT, self._pixmap)



class SeekContextMenu(QtWidgets.QMenu):
    playToggled = Signal(bool)
    speedChanged = Signal(float)

    def __init__(self, videoItem: VideoItemMixin):
        super().__init__()
        self.videoItem = videoItem

        self.addAction(self._buildKeyframeNavi())

        self.addSeparator()
        self.addAction(self._buildPlayback(videoItem.player))

        self.aboutToShow.connect(self.updateValues)

    def _buildPlayback(self, player: QMediaPlayer) -> QtWidgets.QWidgetAction:
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)

        self.btnTogglePlay = qtlib.ToggleButton("▶")
        self.btnTogglePlay.setFixedWidth(30)
        self.btnTogglePlay.setChecked(True)
        self.btnTogglePlay.toggled.connect(self.playToggled.emit)
        layout.addWidget(self.btnTogglePlay)

        lblSpeed = QtWidgets.QLabel("Speed:")
        layout.addWidget(lblSpeed)

        self.spinSpeed = QtWidgets.QDoubleSpinBox(decimals=2)
        self.spinSpeed.setFixedWidth(60)
        self.spinSpeed.setRange(0.05, 100.0)
        self.spinSpeed.setSingleStep(0.05)
        self.spinSpeed.setValue(player.playbackRate())
        self.spinSpeed.valueChanged.connect(self.speedChanged.emit)
        layout.addWidget(self.spinSpeed)

        btnResetSpeed = QtWidgets.QPushButton("1.0")
        btnResetSpeed.setToolTip("Reset playback speed to 1.0")
        btnResetSpeed.setFixedWidth(30)
        btnResetSpeed.clicked.connect(lambda: self.spinSpeed.setValue(1.0))
        layout.addWidget(btnResetSpeed)

        widget = QWidget()
        widget.setLayout(layout)

        widgetAct = QtWidgets.QWidgetAction(self)
        widgetAct.setDefaultWidget(widget)
        return widgetAct

    def _buildKeyframeNavi(self) -> QtWidgets.QWidgetAction:
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)

        btnPrevKeyframe = QtWidgets.QPushButton("⇤")
        btnPrevKeyframe.setToolTip("Skip back to previous keyframe")
        btnPrevKeyframe.setFixedWidth(30)
        btnPrevKeyframe.clicked.connect(self._prevKeyframe)
        layout.addWidget(btnPrevKeyframe)

        btnAlignKeyframe = QtWidgets.QPushButton("Align to Keyframe")
        btnAlignKeyframe.setToolTip("Align to nearest keyframe")
        btnAlignKeyframe.clicked.connect(self._alignKeyframe)
        qtlib.setFontSize(btnAlignKeyframe, 0.9)
        layout.addWidget(btnAlignKeyframe)

        btnNextKeyframe = QtWidgets.QPushButton("⇥")
        btnNextKeyframe.setToolTip("Skip forward to next keyframe")
        btnNextKeyframe.setFixedWidth(30)
        btnNextKeyframe.clicked.connect(self._nextKeyframe)
        layout.addWidget(btnNextKeyframe)

        widget = QWidget()
        widget.setLayout(layout)

        widgetAct = QtWidgets.QWidgetAction(self)
        widgetAct.setDefaultWidget(widget)
        return widgetAct

    @Slot()
    def updateValues(self):
        player = self.videoItem.player
        with QSignalBlocker(self):
            self.btnTogglePlay.setChecked(player.isPlaying())
            self.spinSpeed.setValue(player.playbackRate())

    def setMediaPlaying(self, playing: bool):
        with QSignalBlocker(self):
            self.btnTogglePlay.setChecked(playing)


    @Slot()
    def _prevKeyframe(self):
        currentPos = self.videoItem.player.position()
        def timeChooser(keyframes: list[int]) -> int:
            return next((p for p in reversed(keyframes) if p < currentPos), currentPos)

        self._setKeyframe(currentPos, -15000, 1, timeChooser)

    @Slot()
    def _nextKeyframe(self):
        currentPos = self.videoItem.player.position()
        def timeChooser(keyframes: list[int]) -> int:
            return next((p for p in keyframes if p > currentPos), currentPos)

        self._setKeyframe(currentPos, -1, 15000, timeChooser)

    @Slot()
    def _alignKeyframe(self):
        currentPos = self.videoItem.player.position()
        def timeChooser(keyframes: list[int]) -> int:
            return min(keyframes, key=lambda p: abs(p-currentPos), default=currentPos)

        self._setKeyframe(currentPos, -8000, 8000, timeChooser)

    def _setKeyframe(self, currentPos: int, startOffset: int, endOffset: int, timeChooser: Callable[[list[int]], int]):
        keyframes = videorw.getKeyframes(self.videoItem.filepath, currentPos+startOffset, currentPos+endOffset)
        if not keyframes:
            print("No keyframes")
            return

        keyframePos = timeChooser(keyframes)
        if keyframePos != currentPos:
            diffPos = keyframePos - currentPos
            self.videoItem.moveSegment(diffPos)
            self.videoItem.setVideoPosition(keyframePos)


    @override
    def mouseMoveEvent(self, event: QMouseEvent):
        rect = self.rect()
        rect.adjust(-40, -40, 40, 40)
        if not rect.contains(event.pos()):
            self.close()

        super().mouseMoveEvent(event)



class ThumbnailRequest(NamedTuple):
    file: str
    pos: int

class FrameExtractWorker(QObject):
    THUMBNAIL_INTERVAL = 100  # ms

    _unload = Signal()
    _requestThumbnail = Signal(str, int) # file, pos
    _requestFrame = Signal(str, int)     # file, pos

    thumbnailDone = Signal(str, QImage)  # file, img
    frameDone = Signal(str, QImage)      # file, img


    def __init__(self):
        super().__init__()
        self.container: InputContainer | None = None
        self.file = ""

        self.frameSize: QSize = QSize()
        self.thumbnailConvert: videorw.FrameConvertFunc | None = None
        self.frameConvert: videorw.FrameConvertFunc | None = None

        self._thumbnailRequest: ThumbnailRequest | None = None
        self._thumbnailTimer = QTimer(self, singleShot=True, interval=self.THUMBNAIL_INTERVAL)
        self._thumbnailTimer.timeout.connect(self._doExtractThumbnail)

        self._unload.connect(self._onUnload, Qt.ConnectionType.QueuedConnection)
        self._requestThumbnail.connect(self._onThumbnailRequested, Qt.ConnectionType.QueuedConnection)
        self._requestFrame.connect(self._doExtractFrame, Qt.ConnectionType.QueuedConnection)

    def unload(self):
        self._unload.emit()

    @Slot()
    def _onUnload(self):
        if self.container is not None:
            self.container.close()

        self.container = None
        self.file = ""
        self.frameSize = QSize()
        self.thumbnailConvert = None
        self.frameConvert = None


    def _prepareContainer(self, file: str) -> InputContainer:
        if file != self.file and self.file:
            self._onUnload()

        if self.container is None:
            try:
                self.container = av.open(file, 'r')
                self.file = file

                stream = self.container.streams.video[0]
                w, h = videorw.avGetFrameSize(stream)
                if min(w, h) <= 0:
                    raise ValueError(f"Invalid video size of width={w}, height={h}")

                self.frameSize = QSize(w, h)

            except Exception as ex:
                traceback.print_exc()
                self._onUnload()
                raise ex

        return self.container

    @classmethod
    def _calcThumbnailSize(cls, w: int, h: int) -> tuple[int, int]:
        ar = w / h
        if ar > 1:
            w = Config.mediaSeekThumbnailSize
            h = round(w / ar)
        else:
            h = Config.mediaSeekThumbnailSize
            w = round(h * ar)

        return w, h


    def requestThumbnail(self, file: str, pos: int):
        self._requestThumbnail.emit(file, pos)

    @Slot(str, int)
    def _onThumbnailRequested(self, file: str, pos: int):
        self._thumbnailRequest = ThumbnailRequest(file, pos)
        if not self._thumbnailTimer.isActive():
            self._thumbnailTimer.start()

    @Slot()
    def _doExtractThumbnail(self):
        req = self._thumbnailRequest
        if req is None:
            return

        try:
            container = self._prepareContainer(req.file)
            if self.thumbnailConvert is None:
                w, h = self.frameSize.toTuple()
                w, h = self._calcThumbnailSize(w, h)
                self.thumbnailConvert = videorw.createFrameConverter(w, h, True, Interpolation.AREA)

            image = self._extractFrame(container, req.pos, self.thumbnailConvert)
            self.thumbnailDone.emit(req.file, image)
        except Exception as ex:
            print(f"Failed to extract thumbnail: {ex} ({type(ex).__name__})")


    def requestFrame(self, file: str, pos: int):
        self._requestFrame.emit(file, pos)

    @Slot(str, int)
    def _doExtractFrame(self, file: str, pos: int):
        try:
            container = self._prepareContainer(file)
            if self.frameConvert is None:
                w, h = self.frameSize.toTuple()
                self.frameConvert = videorw.createFrameConverter(w, h, True, Interpolation.LANCZOS)

            image = self._extractFrame(container, pos, self.frameConvert)
            self.frameDone.emit(file, image)
        except Exception as ex:
            print(f"Failed to extract video frame: {ex} ({type(ex).__name__})")


    def _extractFrame(self, container: InputContainer, posMs: int, convertFunc: videorw.FrameConvertFunc) -> QImage:
        stream = container.streams.video[0]

        targetPts = int((posMs/1000) / stream.time_base)
        container.seek(targetPts, stream=stream)

        for frame in container.decode(stream):
            if frame.pts + frame.duration >= targetPts:
                mat = convertFunc(frame)
                return qtlib.numpyToQImage(mat, fromRGB=True)

        raise ValueError(f"No frame at position {posMs/1000:.3f}")
