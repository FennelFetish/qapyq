from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QLineF, QPointF, QPoint
from .view import ViewTool
import qtlib
import math

# Right click (?) sets origin point
# Mouse move updates ruler that shows distance in pixels (manhattan distance?)
# Also rectangular measurement? selected via tool bar?

class MeasureTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        self._startPoint = QPointF()
        self._endPoint = QPointF()
        self._frozen = True
        
        color = QtGui.QColor(0, 255, 255, 200)
        linePen = QtGui.QPen(color)
        linePen.setCapStyle(Qt.RoundCap)
        linePen.setWidth(2)

        self._line = QtWidgets.QGraphicsLineItem()
        self._line.setPen(linePen)
        self._line.setVisible(False)

        rectPen = QtGui.QPen(QtGui.QColor(80, 180, 180, 180))
        rectPen.setCapStyle(Qt.RoundCap)
        rectPen.setStyle(Qt.DashLine)
        rectPen.setWidth(1)

        rectBrush = QtGui.QBrush(QtGui.QColor(80, 180, 180, 30))
        rectBrush.setStyle(Qt.Dense2Pattern)

        self._rect = QtWidgets.QGraphicsRectItem()
        self._rect.setPen(rectPen)
        self._rect.setBrush(rectBrush)
        self._rect.setVisible(False)

        textPen = QtGui.QPen(QtGui.QColor(0, 0, 0, 140))
        textPen.setCapStyle(Qt.RoundCap)
        textPen.setWidth(1.5)

        self._text = QtWidgets.QGraphicsSimpleTextItem()
        self._text.setPen(textPen)
        self._text.setBrush(color)
        qtlib.setMonospace(self._text, 1.5, True)
        self._text.setVisible(False)


    def updateLine(self):
        startPoint = self.imgToView(self._startPoint)
        endPoint   = self.imgToView(self._endPoint)

        line = self._line.line()
        line.setP1(startPoint)
        line.setP2(endPoint)
        self._line.setLine(line)

        rectX = min(self._startPoint.x(), self._endPoint.x()) - 0.5
        rectY = min(self._startPoint.y(), self._endPoint.y()) - 0.5
        rectTopLeft = self.imgToView(QPointF(rectX, rectY))
        rectMaxX = max(self._startPoint.x(), self._endPoint.x()) + 0.5
        rectMaxY = max(self._startPoint.y(), self._endPoint.y()) + 0.5
        rectBottomRight = self.imgToView(QPointF(rectMaxX, rectMaxY))

        rect = self._rect.rect()
        rect.setTopLeft(rectTopLeft)
        rect.setBottomRight(rectBottomRight)
        self._rect.setRect(rect)

        dx = self._endPoint.x() - self._startPoint.x()
        dy = self._endPoint.y() - self._startPoint.y()
        dist = math.sqrt((dx*dx) + (dy*dy))
        self._text.setText(f"{dist:.1f} px")
        self._text.setPos(QPointF(endPoint.x(), endPoint.y()-24))

        self._imgview.scene().update()

        startX, startY = int(self._startPoint.x()), int(self._startPoint.y())
        endX, endY = int(self._endPoint.x()), int(self._endPoint.y())
        dx = int(abs(dx))
        dy = int(abs(dy))
        manhattan = dx+dy
        self.tab.statusBar().showMessage(f"From [X: {startX} Y: {startY}]   To [X: {endX} Y: {endY}]   Δ [X: {dx} Y: {dy}]   Distance: {dist:.2f} px   Manhattan: {manhattan} px   Rectangle [W: {dx+1} H: {dy+1}]")

    def updateEndPoint(self, cursorPos: QPointF):
        if not self._frozen:
            self._endPoint = self.viewToImg(cursorPos.toPoint())
        self.updateLine()

    def viewToImg(self, point: QPoint) -> QPointF:
        point = self._imgview.mapToScene(point)
        point = self._imgview.image.mapFromParent(point)

        # Constrain to image
        imgsize = self._imgview.image.pixmap().size()
        x = max(point.x(), 0)
        y = max(point.y(), 0)
        x = min(x, imgsize.width()-1)
        y = min(y, imgsize.height()-1)

        # On pixel center
        point.setX( int(x) + 0.5 )
        point.setY( int(y) + 0.5 )
        return point

    def imgToView(self, point: QPointF) -> QPoint:
        point = self._imgview.image.mapToParent(point)
        return self._imgview.mapFromScene(point)

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        imgview._guiScene.addItem(self._line)
        imgview._guiScene.addItem(self._rect)
        imgview._guiScene.addItem(self._text)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._line)
        imgview._guiScene.removeItem(self._rect)
        imgview._guiScene.removeItem(self._text)

    def onSceneUpdate(self):
        super().onSceneUpdate()
        self.updateLine()

    def onMousePress(self, event):
        if event.button() == Qt.RightButton:
            if self._frozen:
                self._frozen = False
                self._startPoint = self.viewToImg(event.position().toPoint())
                self._endPoint = self._startPoint

                self._line.setVisible(True)
                self._rect.setVisible(True)
                self._text.setVisible(True)
                self.updateLine()
            else:
                self._frozen = True
            return True
        else:
            return super().onMousePress(event)

    def onMouseMove(self, event):
        super().onMouseMove(event)
        self.updateEndPoint(event.position())

    def onMouseWheel(self, event):
        self.updateEndPoint(event.position())
        return super().onMouseWheel(event)
