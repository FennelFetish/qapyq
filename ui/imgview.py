from __future__ import annotations
from enum import IntEnum
from typing_extensions import override
from PySide6.QtCore import Qt, QRect, QRectF
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QTransform, QPalette, QShortcut, QKeySequence, QMouseEvent, QWheelEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsView, QGraphicsItem, QGraphicsScene
from lib import colorlib, imagerw, videorw
from lib.filelist import FileList
from .dropview import DropView


class ImgView(DropView):
    SHOW_PIXEL_SIZE_SQUARED = 8**2

    def __init__(self, filelist: FileList):
        super().__init__()

        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFrameStyle(0)

        self._setupBackground()

        self.rotation = 0.0
        self.takeFocusOnFilechange = False

        from tools.tool import Tool
        self._tool: Tool = None

        self.filelist = filelist
        filelist.addListener(self)

        self.image = ImgItem()
        self.scene().addItem(self.image)

        self._playShortcut = QShortcut(QKeySequence(" "), self, context=Qt.ShortcutContext.WindowShortcut)
        self._playShortcut.setEnabled(False)
        self._playShortcut.activated.connect(lambda: self.image.togglePlay())

    def _setupBackground(self):
        palette = self.palette()
        baseColor = palette.color(QPalette.ColorRole.Base)

        if colorlib.DARK_THEME:
            baseColor  = QColor(15, 15, 15)
            brushColor = QColor(50, 50, 50)
        else:
            baseColor  = QColor(232, 232, 232)
            brushColor = QColor(160, 160, 160)

        palette.setColor(QPalette.ColorRole.Base, baseColor)
        self.setPalette(palette)

        bgBrush = QBrush(brushColor)
        bgBrush.setStyle(Qt.BrushStyle.Dense7Pattern)
        self.setBackgroundBrush(bgBrush)


    def onFileChanged(self, currentFile: str):
        isVideoFile = videorw.isVideoFile(currentFile)
        if isVideoFile != (self.image.TYPE == MediaItemMixin.ItemType.Video):
            self.image.removeFromScene(self.scene(), self._guiScene)
            self.image.deleteLater()

            if isVideoFile:
                from .video_player import VideoItem
                self.image = VideoItem(self)
            else:
                self.image = ImgItem()

            self.image.addToScene(self.scene(), self._guiScene)
            self._playShortcut.setEnabled(isVideoFile)

        if self.image.loadFile(currentFile):
            self.resetView()
            self.updateImageTransform()
            self.updateView()

        if self.takeFocusOnFilechange:
            # TODO: On Windows, this delays the re-painting of selection borders
            self.setFocus()
            self.activateWindow()

    def onFileListChanged(self, currentFile: str):
        if currentFile != self.image.filepath:
            self.onFileChanged(currentFile)


    def updateImageTransform(self):
        self.image.updateTransform(self.viewport().rect(), self.rotation)

    def updateImageSmoothness(self, imgItem: ImgItem):
        p0 = imgItem.mapToParent(0, 0)
        p0 = self.mapFromScene(p0)

        p1 = imgItem.mapToParent(1, 0)
        p1 = self.mapFromScene(p1)

        # Properly calculate length to make it work with rotated images.
        dx = p1.x() - p0.x()
        dy = p1.y() - p0.y()
        pixelSizeSquared = dx*dx + dy*dy
        imgItem.setSmooth(pixelSizeSquared < self.SHOW_PIXEL_SIZE_SQUARED)

    def resetView(self):
        super().resetView()
        self.rotation = 0.0
        self._tool.onResetView()


    @property
    def tool(self):
        return self._tool

    @tool.setter
    def tool(self, tool):
        if tool is self._tool:
            return

        if self._tool is not None:
            self._tool.onDisabled(self)
        self._tool = tool
        tool.onEnabled(self)
        self.updateView()


    def updateView(self):
        super().updateView()
        self.updateImageSmoothness(self.image)
        self._tool.onSceneUpdate()

    def onDrop(self, event, zoneIndex) -> None:
        self._tool.onDrop(event, zoneIndex)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateImageTransform()
        self._tool.onResize(event)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.image.onMouseEnter()
        self._tool.onMouseEnter(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.image.onMouseLeave()
        self._tool.onMouseLeave(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.image.onMouseMove(event):
            super().mouseMoveEvent(event)
            self._tool.onMouseMove(event)

    def mousePressEvent(self, event: QMouseEvent):
        if not (self.image.onMousePress(event) or self._tool.onMousePress(event)):
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        self._tool.onMouseRelease(event)

    def wheelEvent(self, event: QWheelEvent):
        if not (self._tool.onMouseWheel(event) or self.image.onMouseWheel(event)):
            super().wheelEvent(event)

    def tabletEvent(self, event):
        if self._tool.onTablet(event):
            event.accept()
        else:
            super().tabletEvent(event)


    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self._tool.onKeyPress(event)



class MediaItemMixin:
    class ItemType(IntEnum):
        Image = 0
        Video = 1


    def __init__(self):
        self.filepath = ""

    def clearImage(self):
        self.filepath = ""

    def loadFile(self, path: str) -> bool:
        self.filepath = path
        if not path:
            self.clearImage()
            return False
        return True

    def addToScene(self: QGraphicsItem, scene: QGraphicsScene, guiScene: QGraphicsScene):
        scene.addItem(self)

    def removeFromScene(self: QGraphicsItem, scene: QGraphicsScene, guiScene: QGraphicsScene):
        scene.removeItem(self)

    def updateTransform(self: QGraphicsItem, vpRect: QRect | QRectF, rotation: float):
        imgRect = self.boundingRect()
        if imgRect.width() == 0 or imgRect.height() == 0:
            return

        transform = QTransform().rotate(rotation)
        transform.translate(-imgRect.width()/2, -imgRect.height()/2)

        bbox = transform.mapRect(imgRect)
        scale = min(
            vpRect.width() / bbox.width(),
            vpRect.height() / bbox.height()
        )

        transform *= QTransform.fromScale(scale, scale)
        self.setTransform(transform)

    def setSmooth(self, enabled: bool):
        pass

    def togglePlay(self):
        pass

    def onMouseMove(self, event: QMouseEvent) -> bool:
        return False

    def onMousePress(self, event: QMouseEvent) -> bool:
        return False

    def onMouseWheel(self, event: QWheelEvent) -> bool:
        return False

    def onMouseEnter(self):
        pass

    def onMouseLeave(self):
        pass


class ImgItem(QGraphicsPixmapItem, MediaItemMixin):
    TYPE = MediaItemMixin.ItemType.Image

    def __init__(self):
        super().__init__()
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    def deleteLater(self):
        pass

    @override
    def clearImage(self):
        super().clearImage()
        if not self.pixmap().isNull():
            self.setPixmap(QPixmap())

    @override
    def loadFile(self, path: str) -> bool:
        if not super().loadFile(path):
            return False

        image = imagerw.loadQImage(path)
        pixmap = QPixmap.fromImage(image)
        self.setPixmap(pixmap)
        if pixmap.isNull():
            print(f"Failed to load image: {path}")
            return False
        return True

    @override
    def setSmooth(self, enabled: bool):
        mode = Qt.TransformationMode.SmoothTransformation if enabled else Qt.TransformationMode.FastTransformation
        if mode != self.transformationMode():
            self.setTransformationMode(mode)
