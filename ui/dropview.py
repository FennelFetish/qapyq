from typing import NamedTuple
from typing_extensions import override
from PySide6.QtWidgets import QGraphicsScene, QGraphicsItemGroup, QGraphicsRectItem, QGraphicsTextItem
from PySide6.QtGui import QPen, QBrush, QColor, QFont, QDropEvent, QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent
from PySide6.QtCore import Qt
from lib import colorlib
from .zoompan_view import ZoomPanView


class DropRect(NamedTuple):
    name: str
    x: float
    y: float
    w: float
    h: float

    def toAbsolute(self, w: float, h: float) -> tuple[float, float, float, float]:
        return (self.x * w), (self.y * h), (self.w * w), (self.h * h)


class DropZone(QGraphicsItemGroup):
    RECT_BRUSH: QBrush = None
    RECT_PEN: QPen     = None
    FONT: QFont        = None

    def __init__(self, rect: DropRect):
        super().__init__()
        self.rectRelative = rect

        if DropZone.FONT is None:
            self._initStyle()

        self.rectItem = QGraphicsRectItem(self)
        self.rectItem.setPen(self.RECT_PEN)
        self.rectItem.setBrush(self.RECT_BRUSH)

        self.textItem = QGraphicsTextItem(rect.name, self)
        self.textItem.setFont(self.FONT)
        self.textItem.setDefaultTextColor(colorlib.BUBBLE_TEXT)
        self.textItem.adjustSize()

        self.addToGroup(self.rectItem)
        self.addToGroup(self.textItem)

        self.setZValue(900)
        self.hide()

    @classmethod
    def _initStyle(cls):
        font = QFont()
        font.setPointSizeF(font.pointSizeF() * 2.0)
        font.setBold(True)
        cls.FONT = font

        bgAlpha = 0.63 if colorlib.DARK_THEME else 0.43
        colorBg = QColor(colorlib.BUBBLE_BG)
        colorBg.setAlphaF(bgAlpha)
        cls.RECT_BRUSH = QBrush(colorBg)

        colorBorder = QColor(colorBg)
        colorBorder.setAlphaF(0.9)
        cls.RECT_PEN = QPen(colorBorder)

    def updateZoneSize(self, vpWidth: float, vpHeight: float):
        x, y, w, h = self.rectRelative.toAbsolute(vpWidth, vpHeight)
        self.rectItem.setRect(x, y, w, h)

        textX = (w - self.textItem.textWidth()) / 2
        textY = h/2 - 20
        self.textItem.setPos(x+textX, y+textY)

    @override
    def contains(self, point) -> bool:
        return self.rectItem.contains(point)



class DropView(ZoomPanView):
    def __init__(self):
        super().__init__(None)
        self.setScene(DropScene())
        self.setAcceptDrops(True)
        self._dropZones: list[DropZone] = []

    def addDropZone(self, dropRect: DropRect):
        dropZone = DropZone(dropRect)
        self._dropZones.append(dropZone)
        self._guiScene.addItem(dropZone)

    def clearDropZones(self):
        for dz in self._dropZones:
            self._guiScene.removeItem(dz)
        self._dropZones.clear()

    @override
    def updateView(self):
        super().updateView()
        vpW, vpH = self.viewport().rect().size().toTuple()
        for zone in self._dropZones:
            zone.updateZoneSize(vpW, vpH)


    def checkDrop(self, event: QDropEvent) -> bool:
        return event.mimeData().hasUrls()

    def onDrop(self, event: QDropEvent, zoneIndex: int):
        pass


    @override
    def dragEnterEvent(self, event: QDragEnterEvent):
        if self.checkDrop(event):
            event.acceptProposedAction()

    @override
    def dragMoveEvent(self, event: QDragMoveEvent):
        cursor = event.position()
        hit = False
        for zone in self._dropZones:
            zone.show()

            if (not hit) and zone.contains(cursor):
                zone.setOpacity(1.0)
                hit = True
            else:
                zone.setOpacity(0.35)

        self.scene().update()

    @override
    def dragLeaveEvent(self, event: QDragLeaveEvent):
        for zone in self._dropZones:
            zone.hide()
        self.scene().update()

    @override
    def dropEvent(self, event: QDropEvent):
        for zone in self._dropZones:
            zone.hide()
        self.scene().update()

        if self.checkDrop(event):
            # On Windows, dropping with SHIFT key from Explorer will create a MoveAction,
            # and the files will be moved to Trash! Manually set CopyAction instead.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

            cursor = event.position()
            for i, zone in enumerate(self._dropZones):
                if zone.contains(cursor):
                    self.onDrop(event, i)
                    break



class DropScene(QGraphicsScene):
    # Let event through
    def dragMoveEvent(self, event):
        pass
