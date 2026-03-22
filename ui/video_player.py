from __future__ import annotations
from typing import NamedTuple
from typing_extensions import override
import cv2 as cv
from PySide6.QtCore import Qt, Signal, Slot, QRect, QRectF, QSize, QUrl, QThread, QTimer, QObject, QLoggingCategory
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItemGroup, QGraphicsRectItem, QGraphicsTextItem, QGraphicsPixmapItem, QApplication
from PySide6.QtGui import QPixmap, QImage, QColor, QMouseEvent, QWheelEvent, QSinglePointEvent
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaMetaData
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from lib import qtlib, colorlib, threadlib
from .imgview import ImgView, MediaItemMixin

QLoggingCategory.setFilterRules("qt.multimedia=false\nqt.multimedia.*=false")


class VideoItem(QGraphicsVideoItem, MediaItemMixin):
    TYPE = MediaItemMixin.ItemType.Video

    def __init__(self, imgview: ImgView):
        super().__init__()
        self.imgview = imgview

        self._playing: bool = False

        self.setAspectRatioMode(Qt.AspectRatioMode.IgnoreAspectRatio)
        self.setSize(QSize())

        self.audioOutput = QAudioOutput(parent=self)
        self.player = QMediaPlayer(parent=self, videoOutput=self, audioOutput=self.audioOutput)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)

        self.playbackControls = PlaybackControls(self)
        self.info = MediaInfo(self.player, self.playbackControls)

        self._extractorThread = QThread()
        self._extractorThread.setObjectName("video-frame-extract")

        self.frameExtractor = FrameExtractWorker()
        self.frameExtractor.moveToThread(self._extractorThread)
        self.frameExtractor.thumbnailDone.connect(self._onThumbnailDone)
        self._extractorThread.start()

        self.playbackControls.updateSize(imgview.viewport().rect())

    # TODO: Don't wait for GC
    def __del__(self):
        self._extractorThread.quit()
        self._extractorThread.wait()
        self._extractorThread.deleteLater()


    def _redrawMainViewport(self):
        # The GUI scene is rendered separately as overlay. It's not automatically redrawn when geometries change.
        # The viewport is redrawn when the video is playing. If paused -> force redraw of main view.
        if not self.player.isPlaying():
            self.imgview.viewport().update()

    @Slot(QImage)
    def _onThumbnailDone(self, file: str, image: QImage | None):
        if image is not None and file == self.filepath:
            pixmap = QPixmap.fromImage(image)
            self.playbackControls.seekThumbnail.setPixmap(pixmap)
            self._redrawMainViewport()


    # ===== MediaItemMixin Interface =====

    def pixmap(self) -> QPixmap:
        pos = self.player.position()
        image = self.frameExtractor.extractFrame(pos)  # raises on error
        return QPixmap.fromImage(image)

    @override
    def clearImage(self):
        super().clearImage()
        self.player.setSource(QUrl())
        self.setSize(QSize())

    @override
    def loadFile(self, path: str) -> bool:
        self._playing = False
        if not super().loadFile(path):
            return False

        videoSize, thumbnailSize = self.frameExtractor.loadFile(path)
        if not videoSize.isValid():
            print("Warning: Failed to load video")
            self.clearImage()
            return False

        self.setSize(videoSize)

        self.player.setSource(path)
        self.player.play()
        self._playing = True

        self.playbackControls.seekThumbnail.onFileLoaded(thumbnailSize)
        self.playbackControls.seekThumbnail.hide()
        self.playbackControls.labelSeekTime.hide()
        return True

    @override
    def mediaSize(self) -> QSize:
        size = self.size().toSize()
        return size if (size.width() > 0 and size.height() > 0) else QSize()

    @override
    def addToScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        super().addToScene(scene, guiScene)
        guiScene.addItem(self.playbackControls)

    @override
    def removeFromScene(self, scene: QGraphicsScene, guiScene: QGraphicsScene):
        super().removeFromScene(scene, guiScene)
        guiScene.removeItem(self.playbackControls)

    @override
    def updateTransform(self, vpRect: QRect | QRectF, rotation: float):
        super().updateTransform(vpRect, rotation)
        self.playbackControls.updateSize(vpRect)

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
        mouseX, mouseY = event.pos().toTuple()

        expanded = self.playbackControls.isMouseOver(mouseY)
        expandedChanged = self.playbackControls.setExpanded(expanded)

        if expanded:
            self.playbackControls.requestThumbnail(mouseX)
            self._redrawMainViewport()
        elif expandedChanged:
            self._redrawMainViewport()

        return expanded

    @override
    def onMousePress(self, event: QMouseEvent) -> bool:
        if event.button() not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            return False

        mouseX, mouseY = event.pos().toTuple()
        if self.playbackControls.isMouseOver(mouseY):
            pos = self.playbackControls.getVideoPosition(mouseX)
            self.player.setPosition(pos)
            return True

        return False

    @override
    def onMouseWheel(self, event: QWheelEvent) -> bool:
        if self.player.isPlaying():
            skip = min(5000, self.player.duration()/5)
        elif self.info.fps > 0.0:
            skip = 1000.0 / self.info.fps
        else:
            skip = 0

        skipSteps = -event.angleDelta().y() / 120.0 # 8*15° standard

        videoPos = self.player.position() + (skipSteps * skip)
        self.player.setPosition(round(videoPos))
        return True

    @override
    def onMouseEnter(self, event: QSinglePointEvent) -> bool:
        return self.playbackControls.isMouseOver( int(event.position().y()) )

    @override
    def onMouseLeave(self):
        self.playbackControls.seekThumbnail.hide()
        if self.playbackControls.setExpanded(False):
            self._redrawMainViewport()



class MediaInfo(QObject):
    def __init__(self, player: QMediaPlayer, playbackControls: PlaybackControls):
        super().__init__(player)
        self.player = player
        self.playbackControls = playbackControls

        self.fps: float = 0.0
        self.duration: int = 0
        self.seekable: bool = False

        player.mediaStatusChanged.connect(self._onMediaStatusChanged, Qt.ConnectionType.QueuedConnection)
        player.positionChanged.connect(self._onPosChanged, Qt.ConnectionType.QueuedConnection)
        player.durationChanged.connect(self._onDurationChanged, Qt.ConnectionType.QueuedConnection)
        player.playingChanged.connect(self._onPlayingChanged, Qt.ConnectionType.QueuedConnection)
        player.seekableChanged.connect(self._onSeekableChanged, Qt.ConnectionType.QueuedConnection)
        player.errorOccurred.connect(self._onError, Qt.ConnectionType.QueuedConnection)

    @Slot(QMediaPlayer.MediaStatus)
    def _onMediaStatusChanged(self, status: QMediaPlayer.MediaStatus):
        match status:
            case QMediaPlayer.MediaStatus.LoadingMedia:
                self.fps = 0.0

            case QMediaPlayer.MediaStatus.LoadedMedia:
                try:
                    meta = self.player.metaData()
                    self.fps = float( meta.value(QMediaMetaData.Key.VideoFrameRate) )
                except (ValueError, TypeError):
                    self.fps = 0.0

    @Slot(int)
    def _onDurationChanged(self, duration: int):
        self.duration = duration
        self.playbackControls.setMediaDuration(duration)

    @Slot(int)
    def _onPosChanged(self, pos: int):
        self.playbackControls.setMediaPosition(pos, self.duration)

    @Slot(bool)
    def _onPlayingChanged(self, playing: bool):
        self.playbackControls.setMediaPlaying(playing, self.player.position())

    @Slot(bool)
    def _onSeekableChanged(self, seekable: bool):
        self.seekable = seekable

    @Slot(QMediaPlayer.Error, str)
    def _onError(self, error: QMediaPlayer.Error, errorMsg: str):
        print(f"Error while playing video: {errorMsg} ({error})")



class PlaybackControls(QGraphicsItemGroup):
    Y_OFFSET = 6  # move down, because otherwise it doesn't reach all the way to the bottom

    SEEK_BAR_HEIGHT = Y_OFFSET + 2
    SEEK_BAR_HEIGHT_EXPANDED = 40

    KNOB_WIDTH = 4
    KNOB_X_OFFSET = -KNOB_WIDTH//2


    def __init__(self, videoItem: VideoItem):
        super().__init__()
        self.videoItem = videoItem
        self._expanded: bool = False

        # UI Elements
        self.seekBar = SeekBar()
        self.seekBarFull = SeekBarFull()
        self.seekKnob = SeekKnob(self.KNOB_WIDTH, self.SEEK_BAR_HEIGHT)
        self.seekThumbnail = SeekThumbnail()

        self.addToGroup(self.seekBar)
        self.addToGroup(self.seekBarFull)
        self.addToGroup(self.seekKnob)
        self.addToGroup(self.seekThumbnail)

        # Text Labels
        palette = QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)

        textColor = QColor(colorlib.BUBBLE_TEXT)
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

        self.setPos(0, rectH - self.SEEK_BAR_HEIGHT_EXPANDED + self.Y_OFFSET)

        if self._expanded:
            h = self.SEEK_BAR_HEIGHT_EXPANDED
        else:
            h = self.SEEK_BAR_HEIGHT

        y = self.SEEK_BAR_HEIGHT_EXPANDED - h

        self.seekBar.setRect(0, y, rectW, h)
        self.seekBarFull.setRect(0, y, 0, h)
        self.seekKnob.setRect(0, y, self.KNOB_WIDTH, h)
        self.seekThumbnail.hide()
        self.setMediaPosition(self.videoItem.player.position(), self.videoItem.info.duration)

        self.labelDuration.setPos(rectW - self.labelDuration.boundingRect().width(), 16)
        self.labelPlayTime.setPos(0, 16)
        self.labelSeekTime.setY(-2)
        self.labelSeekTime.hide()


    def isMouseOver(self, mouseY: int) -> bool:
        sceneH = self.scene().sceneRect().height()
        return mouseY > sceneH - PlaybackControls.SEEK_BAR_HEIGHT_EXPANDED

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


    def requestThumbnail(self, mouseX: float):
        sceneW = self.scene().sceneRect().width()
        videoPos = self.getVideoPosition(mouseX)

        self.labelSeekTime.setTime(videoPos)
        self.labelSeekTime.setBoundedX(mouseX, sceneW)
        self.labelSeekTime.show()

        if self.videoItem.info.seekable:
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

    def setMediaPosition(self, pos: int, duration: int):
        if duration < 1:
            p = 0
        else:
            w = self.seekBar.rect().width()
            p = w * pos / duration

        rectFull = self.seekBarFull.rect()
        rectFull.setWidth(p)
        self.seekBarFull.setRect(rectFull)

        self.seekKnob.setX(p + self.KNOB_X_OFFSET)
        self.labelPlayTime.setTime(pos)

    def setMediaPlaying(self, playing: bool, pos: int):
        self.labelPlayTime.suffix = " ▶" if playing else ""
        self.labelPlayTime.setTime(pos)



class SeekBar(QGraphicsRectItem):
    COLOR_BG          = QColor(80, 80, 80, 20)
    COLOR_BG_EXPANDED = QColor(80, 80, 80, 50)  # TODO: Better readability

    def __init__(self):
        super().__init__()
        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(self.COLOR_BG)

    def setExpanded(self, extended: bool):
        self.setBrush(self.COLOR_BG_EXPANDED if extended else self.COLOR_BG)


class SeekBarFull(QGraphicsRectItem):
    def __init__(self):
        super().__init__()
        palette = QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)
        highlightColor.setAlphaF(0.5)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(highlightColor)


class SeekKnob(QGraphicsRectItem):
    def __init__(self, width: int, height: int):
        super().__init__(0, 0, width, height)
        palette = QApplication.palette()
        highlightColor = palette.color(palette.ColorRole.Highlight)
        #highlightColor.setAlphaF(0.8)

        self.setPen(Qt.PenStyle.NoPen)
        self.setBrush(highlightColor)


class SeekThumbnail(QGraphicsPixmapItem):
    def __init__(self):
        super().__init__()
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def onFileLoaded(self, thumbnailSize: QSize):
        if not self.pixmap().isNull():
            self.setPixmap(QPixmap())

        self.setY(-thumbnailSize.height())

    def setBoundedX(self, x: float, sceneWidth: float):
        w = self.boundingRect().width()
        x = min(x, sceneWidth - w)
        self.setX(x)


class TimeLabel(QGraphicsTextItem):
    FONT = None

    def __init__(self, color: QColor):
        super().__init__("00:00")
        self.suffix: str = ""

        if TimeLabel.FONT is None:
            font = qtlib.getMonospaceFont()
            font.setPointSizeF(font.pointSizeF() * 0.9)
            TimeLabel.FONT = font

        self.setFont(TimeLabel.FONT)
        self.setDefaultTextColor(color)
        self.hide()

    def setTime(self, timeMs: int):
        s = timeMs // 1000
        hours, s = divmod(s, 3600)
        minutes, seconds = divmod(s, 60)

        text = f"{hours:02}:{minutes:02}:{seconds:02}" if hours > 0 else f"{minutes:02}:{seconds:02}"
        text += self.suffix
        self.setPlainText(text)

    def setBoundedX(self, x: float, sceneWidth: float):
        w = self.boundingRect().width()
        x = min(x, sceneWidth - w)
        self.setX(x)



class VideoSizeFuture(threadlib.Future[tuple[QSize, QSize]]): pass
class FrameExtractFuture(threadlib.Future[QImage]): pass

class ThumbnailRequest(NamedTuple):
    file: str
    pos: int

class FrameExtractWorker(QObject):
    THUMBNAIL_SIZE = 250
    THUMBNAIL_INTERVAL = 100  # ms

    _loadFile = Signal(str, VideoSizeFuture)        # file, future
    _extractFrame = Signal(int, FrameExtractFuture) # pos, future
    _requestThumbnail = Signal(str, int)            # file, pos

    thumbnailDone = Signal(str, QImage)             # file, img|None


    def __init__(self):
        super().__init__()
        self.cap = cv.VideoCapture()

        self.videoSize: QSize = QSize()
        self.thumbnailSize: QSize = QSize()

        self._thumbnailRequest: ThumbnailRequest | None = None
        self._thumbnailTimer = QTimer(self, singleShot=True, interval=self.THUMBNAIL_INTERVAL)
        self._thumbnailTimer.timeout.connect(self._doExtractThumbnail)

        self._loadFile.connect(self._doLoadFile)
        self._requestThumbnail.connect(self._onThumbnailRequested)
        self._extractFrame.connect(self._doExtractFrame)


    def loadFile(self, file: str) -> tuple[QSize, QSize]:
        future = VideoSizeFuture()
        self._loadFile.emit(file, future)
        return future.result()

    @Slot(str, VideoSizeFuture)
    def _doLoadFile(self, file: str, future: VideoSizeFuture):
        try:
            self._thumbnailTimer.stop()
            self._thumbnailRequest = None

            self.cap.open(file)
            if self.cap.isOpened():
                w = int(self.cap.get(cv.CAP_PROP_FRAME_WIDTH))
                h = int(self.cap.get(cv.CAP_PROP_FRAME_HEIGHT))
            else:
                w = h = -1

            self.videoSize = QSize(w, h)
            self.thumbnailSize = self._calcThumbnailSize(w, h)
            future.setResult((self.videoSize, self.thumbnailSize))

        except Exception as ex:
            future.setException(ex)

    @classmethod
    def _calcThumbnailSize(cls, w: int, h: int) -> QSize:
        if min(w, h) <= 0:
            return QSize()

        ar = w / h
        if ar > 1:
            w = cls.THUMBNAIL_SIZE
            h = round(w / ar)
        else:
            h = cls.THUMBNAIL_SIZE
            w = round(h * ar)

        return QSize(w, h)


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
            self.cap.set(cv.CAP_PROP_POS_MSEC, req.pos)
            ret, frame = self.cap.read()

            if ret:
                frame = cv.resize(frame, self.thumbnailSize.toTuple(), interpolation=cv.INTER_AREA)
                image = qtlib.numpyToQImage(frame)
                self.thumbnailDone.emit(req.file, image)
            else:
                self.thumbnailDone.emit(req.file, None)

        except Exception as ex:
            print(f"Failed to extract thumbnail: {ex} ({type(ex).__name__})")
            self.thumbnailDone.emit(req.file, None)


    def extractFrame(self, pos: int) -> QImage:
        future = FrameExtractFuture()
        self._extractFrame.emit(pos, future)
        return future.result()

    @Slot(str, int, FrameExtractFuture)
    def _doExtractFrame(self, pos: int, future: FrameExtractFuture):
        try:
            self.cap.set(cv.CAP_PROP_POS_MSEC, pos)
            ret, frame = self.cap.read()

            if ret:
                image = qtlib.numpyToQImage(frame)
                future.setResult(image)
            else:
                raise ValueError("Failed to extract video frame")

        except Exception as ex:
            future.setException(ex)


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
