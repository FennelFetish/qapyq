from PySide6.QtWidgets import QGraphicsScene, QGraphicsRectItem
from PySide6.QtGui import QPen, QBrush, QColor, QDropEvent
from PySide6.QtCore import QRectF
from .zoompan_view import ZoomPanView


class DropZone(QGraphicsRectItem):
    def __init__(self, rectRelative: QRectF):
        super().__init__(None)
        self.rectRelative = QRectF(rectRelative)
        self.setPen( QPen(QColor(180, 180, 180, 140)) )
        self.setBrush( QBrush(QColor(180, 180, 180, 80)) )
        self.setZValue(900)
        self.setVisible(False)



class DropView(ZoomPanView):
    def __init__(self):
        super().__init__(None)
        self.setScene(DropScene())
        self.setAcceptDrops(True)
        self._dropZones = []

    def addDropZone(self, dropZone: DropZone):
        self._dropZones.append(dropZone)
        self._guiScene.addItem(dropZone)
    
    def clearDropZones(self):
        for dz in self._dropZones:
            self._guiScene.removeItem(dz)
        self._dropZones.clear()

    def updateScene(self):
        super().updateScene()
        vpRect = self.viewport().rect()
        w = vpRect.width()
        h = vpRect.height()

        for zone in self._dropZones:
            rel = zone.rectRelative
            zone.setRect(rel.x()*w, rel.y()*h, rel.width()*w, rel.height()*h)


    def checkDrop(self, event: QDropEvent) -> bool:
        return event.mimeData().hasUrls()

    def onDrop(self, event: QDropEvent, zoneIndex) -> None:
        pass


    def dragEnterEvent(self, event):
        if self.checkDrop(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        cursor = event.position()
        hit = False
        for zone in self._dropZones:
            if (not hit) and zone.contains(cursor):
                zone.setVisible(True)
                hit = True
            else:
                zone.setVisible(False)
        self.scene().update()

    def dragLeaveEvent(self, event):
        for zone in self._dropZones:
            zone.setVisible(False)
        self.scene().update()

    def dropEvent(self, event):
        for zone in self._dropZones:
            zone.setVisible(False)
        self.scene().update()

        if self.checkDrop(event):
            event.acceptProposedAction()

            cursor = event.position()
            for i, zone in enumerate(self._dropZones):
                if zone.contains(cursor):
                    self.onDrop(event, i)
                    break



class DropScene(QGraphicsScene):
    # Let event through
    def dragMoveEvent(self, event):
        pass
