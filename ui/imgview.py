from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsView
from .dropview import DropView


class ImgView(DropView):
    def __init__(self, filelist):
        super().__init__()

        bgBrush = QBrush(QColor(0, 0, 0))
        bgBrush.setStyle(Qt.Dense2Pattern)
        self.setBackgroundBrush(bgBrush)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFrameStyle(0)

        self.rotation = 0.0
        self._tool = None
        self.filelist = filelist
        filelist.addListener(self)

        self.image = ImgItem()
        self.scene().addItem(self.image)
        

    def onFileChanged(self, currentFile):
        if self.image.loadImage(currentFile):
            self.resetView()
            self.updateImageTransform()
            self.updateScene()
        self.setFocus()
        self.activateWindow()

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    def updateImageTransform(self):
        self.image.updateTransform(self.viewport().rect(), self.rotation)
    
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
        self.updateScene()


    def updateScene(self):
        super().updateScene()
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
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.filepath = ""

    def loadImage(self, path) -> bool:
        #print("Load image:", path)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            print("Failed to load image:", path)
            return False

        self.filepath = path
        self.setPixmap(pixmap)
        return True

    def updateTransform(self, vpRect: QRectF, rotation):
        imgRect = self.boundingRect()
        if imgRect.width() == 0 or imgRect.height() == 0:
            return

        vp_w, vp_h   = vpRect.width(), vpRect.height()
        img_w, img_h = imgRect.width(), imgRect.height()

        scale = min(vp_w/img_w, vp_h/img_h)
        x = (-img_w * scale) / 2
        y = (-img_h * scale) / 2

        transform = QTransform()
        transform = transform.rotate(rotation)
        transform = transform.translate(x, y)
        transform = transform.scale(scale, scale)
        self.setTransform(transform)
