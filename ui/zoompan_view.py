from typing_extensions import override
from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
from PySide6.QtGui import QMouseEvent, QWheelEvent
from config import Config


class ZoomPanView(QGraphicsView):
    PAN_BUTTON = Qt.MouseButton.LeftButton

    def __init__(self, scene):
        super().__init__(scene)
        self.zoom = 1.0
        self.zoomFactor = Config.viewZoomFactor
        self.zoomMin = Config.viewZoomMinimum
        self.pan = QPointF(0, 0)
        self._eventState = None

        self._guiScene = QGraphicsScene()

        # Fixes dropped wheel events
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_CompressHighFrequencyEvents, False)
        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_CompressTabletEvents, False) # Default already false

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setMouseTracking(True)

    def updateView(self):
        w, h = self.viewport().size().toTuple()
        self._guiScene.setSceneRect(0, 0, w, h)

        wz = w / self.zoom
        hz = h / self.zoom
        pan = self.pan / self.zoom

        rect = QRectF(pan.x() - (wz/2), pan.y() - (hz/2), wz, hz)
        self.setSceneRect(rect)
        self.fitInView(rect)

    def resetView(self):
        self.pan = QPointF(0, 0)
        self.zoom = 1.0

    @override
    def drawForeground(self, painter, rect):
        self._guiScene.render(painter, rect)

    @override
    def resizeEvent(self, event):
        self.updateView()

    @override
    def mouseMoveEvent(self, event: QMouseEvent):
        if self._eventState is not None:
            self._eventState.onMove(event.position())

    @override
    def mousePressEvent(self, event: QMouseEvent):
        if (self._eventState is None) and (event.button() == self.PAN_BUTTON):
            self._eventState = ViewPan(self, event.position())

    @override
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QMouseEvent):
        self._eventState = None

    @override
    def leaveEvent(self, event):
        self._eventState = None

    @override
    def wheelEvent(self, event: QWheelEvent):
        zoomSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self.zoom *= self.zoomFactor ** zoomSteps
        self.zoom = max(self.zoom, self.zoomMin)

        mousePos = event.position().toPoint()
        oldPos = self.mapToScene(mousePos)
        ZoomPanView.updateView(self)

        newPos = self.mapToScene(mousePos)
        self.pan -= (newPos - oldPos) * self.zoom
        self.updateView()



class ViewPan:
    def __init__(self, view: ZoomPanView, startPos: QPointF):
        self._view = view
        self._startPos = QPointF(startPos)

    def onMove(self, position: QPointF):
        self._view.pan += self._startPos - position
        self._view.updateView()
        self._startPos = position
