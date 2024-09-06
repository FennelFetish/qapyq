from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
from config import Config


class ZoomPanView(QGraphicsView):
    PAN_BUTTON = Qt.LeftButton

    def __init__(self, scene):
        super().__init__(scene)
        self.zoom = 1.0
        self.zoomFactor = Config.viewZoomFactor
        self.zoomMin = Config.viewZoomMinimum
        self.pan = QPointF(0, 0)
        self._eventState = None

        self._guiScene = QGraphicsScene()

        # Fixes dropped wheel events
        QCoreApplication.setAttribute(Qt.AA_CompressHighFrequencyEvents, False)
        
        #self.setAlignment(Qt.AlignCenter) # The Default
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setMouseTracking(True)

    def updateScene(self):
        w = self.viewport().width()
        h = self.viewport().height()
        self._guiScene.setSceneRect(0, 0, w, h)

        wz = w / self.zoom
        hz = h / self.zoom
        pan = self.pan / self.zoom

        rect = QRectF(pan.x() - (wz/2), pan.y() - (hz/2), wz, hz)
        self.setSceneRect(rect)
        self.fitInView(rect)

    def drawForeground(self, painter, rect):
        self._guiScene.render(painter, rect)


    def resizeEvent(self, event):
        self.updateScene()

    def mouseMoveEvent(self, event):
        if self._eventState is not None:
            self._eventState.onMove(event.position())

    def mousePressEvent(self, event):
        if (self._eventState is None) and (event.button() == self.PAN_BUTTON):
            self._eventState = ViewPan(self, event.position())

    def mouseReleaseEvent(self, event):
        self._eventState = None

    def leaveEvent(self, event):
        self._eventState = None

    def wheelEvent(self, event):
        zoomSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self.zoom *= self.zoomFactor ** zoomSteps
        self.zoom = max(self.zoom, self.zoomMin)
        
        oldPos = self.mapToScene(event.position().toPoint())
        self.updateScene()

        newPos = self.mapToScene(event.position().toPoint())
        self.pan -= (newPos - oldPos) * self.zoom
        self.updateScene()

    def resetView(self):
        self.pan = QPointF(0, 0)
        self.zoom = 1.0


class ViewPan:
    def __init__(self, view: ZoomPanView, startPos: QPointF):
        self._view = view
        self._startPos = QPointF(startPos)
        
    def onMove(self, position: QPointF):
        self._view.pan += self._startPos - position
        self._view.updateScene()
        self._startPos = position
