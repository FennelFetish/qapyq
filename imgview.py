from zoompan_view import ZoomPanView
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsLineItem
from PySide6.QtGui import QPen, QBrush, QColor, QPainter, QPainterPath, QPixmap, QTransform
from PySide6.QtCore import QRectF, QPointF, Qt


class ImgView(ZoomPanView):
    def __init__(self):
        super().__init__(None)
        scene = DropScene()
        self.setScene(scene)

        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setFrameStyle(0)

        self.setAcceptDrops(True)

        self._dropZones = [ DropZone(), DropZone() ]
        self._images = [ ImgItem(), ImgItem() ]

        self._dividerLine = QGraphicsLineItem(0, 0, 0, 0)
        self._dividerLine.setZValue(1000)
        self._dividerLine.setPen( QPen(QColor(180, 180, 180, 140)) )
        self._dividerLine.setVisible(False)

        self._guiScene.addItem(self._dropZones[0])
        self._guiScene.addItem(self._dropZones[1])
        self._guiScene.addItem(self._dividerLine)

        scene.addItem(self._images[0])
        scene.addItem(self._images[1])
    
    def updateScene(self):
        super().updateScene()
        vpRect = self.viewport().rect()
        w_half = vpRect.width() / 2.0
        h = vpRect.height()

        self._dropZones[0].setRect(0, 0, w_half, h)
        self._dropZones[1].setRect(w_half, 0, w_half, h)

    def loadImage(self, path, imgIndex):
        print("Load image:", path)
        pixmap = QPixmap(path)
        if pixmap.isNull():
            print("Failed to load image:", path)
            return

        img = self._images[imgIndex]
        img.setPixmap(pixmap)
        img.updateTransform(self.viewport().rect())

        if imgIndex == 0:
            self.resetView()

        self.updateScene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vp_rect = self.viewport().rect()
        self._images[0].updateTransform(vp_rect)
        self._images[1].updateTransform(vp_rect)


    # ===== Drag n Drop =====
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        w = self.viewport().width()
        x = event.position().x()
        left = (x < w/2)
        self._dropZones[0].setVisible(left)
        self._dropZones[1].setVisible(not left)
        self.scene().update()

    def dragLeaveEvent(self, event):
        self._dropZones[0].setVisible(False)
        self._dropZones[1].setVisible(False)
        self.scene().update()

    def dropEvent(self, event):
        self._dropZones[0].setVisible(False)
        self._dropZones[1].setVisible(False)
        self.scene().update()

        if event.mimeData().hasUrls():
            w = self.viewport().width()
            x = event.position().x()
            imgIndex = 0 if x < w/2 else 1

            firstUrl = event.mimeData().urls()[0]
            self.loadImage(firstUrl.toLocalFile(), imgIndex)
            event.acceptProposedAction()
    

    # ===== Divider Line =====
    def enterEvent(self, event):
        super().enterEvent(event)
        if not self._images[1].pixmap().isNull():
            self._dividerLine.setVisible(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        imgpos = self.mapToScene(event.position().x(), event.position().y())
        imgpos = self._images[1].mapFromParent(imgpos)
        self._images[1].setClipWidth(imgpos.x())

        x = event.position().x()
        h = self.viewport().height()
        self._dividerLine.setLine(x, 0, x, h)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._images[1].setClipWidth(0)
        self._dividerLine.setVisible(False)
        


class DropScene(QGraphicsScene):
    # Let event through
    def dragMoveEvent(self, event):
        pass



class DropZone(QGraphicsRectItem):
    def __init__(self):
        super().__init__(None)
        self.setPen( QPen(QColor(180, 180, 180, 140)))
        self.setBrush( QBrush(QColor(180, 180, 180, 80)) )
        self.setZValue(900)
        self.setVisible(False)



class ImgItem(QGraphicsPixmapItem):
    def __init__(self):
        super().__init__(None)
        self.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self.setFlag(QGraphicsItem.ItemClipsToShape, True)
        self.clipPath = None
    
    def setClipWidth(self, x):
        w = self.pixmap().width()
        h = self.pixmap().height()
        self.clipPath = QPainterPath()
        self.clipPath.addRect(x, 0, w-x, h)
        self.update()

    def shape(self) -> QPainterPath:
        if self.clipPath is None:
            return super().shape()
        return self.clipPath

    def updateTransform(self, vpRect: QRectF, rotation=0.0):
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