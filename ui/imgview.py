from __future__ import annotations
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QTransform, QPalette
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsView
from lib import colorlib, imagerw
from .dropview import DropView


class ImgView(DropView):
    SHOW_PIXEL_SIZE_SQUARED = 8**2

    def __init__(self, filelist):
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


    def onFileChanged(self, currentFile):
        if self.image.loadImage(currentFile):
            self.resetView()
            self.updateImageTransform()
            self.updateView()

        if self.takeFocusOnFilechange:
            # TODO: On Windows, this delays the re-painting of selection borders
            self.setFocus()
            self.activateWindow()

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    def updateImageTransform(self):
        self.image.updateTransform(self.viewport().rect(), self.rotation)

    def updateImageSmoothness(self, imgItem):
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
        self._tool.onMouseEnter(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self._tool.onMouseMove(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._tool.onMouseLeave(event)

    def mousePressEvent(self, event):
        if not self._tool.onMousePress(event):
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self._tool.onMouseRelease(event)

    def wheelEvent(self, event):
        if not self._tool.onMouseWheel(event):
            super().wheelEvent(event)

    def tabletEvent(self, event):
        if self._tool.onTablet(event):
            event.accept()
        else:
            super().tabletEvent(event)


    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        self._tool.onKeyPress(event)



class ImgItem(QGraphicsPixmapItem):
    def __init__(self):
        super().__init__(None)
        self.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
        self.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.filepath = ""

    def loadImage(self, path: str) -> bool:
        self.filepath = path
        if not path:
            self.setPixmap(QPixmap())
            return False

        image = imagerw.loadQImage(path)
        pixmap = QPixmap.fromImage(image)
        self.setPixmap(pixmap)
        if pixmap.isNull():
            print(f"Failed to load image: {path}")
            return False
        return True

    def updateTransform(self, vpRect: QRectF, rotation: float):
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
        mode = Qt.TransformationMode.SmoothTransformation if enabled else Qt.TransformationMode.FastTransformation
        if mode != self.transformationMode():
            self.setTransformationMode(mode)
