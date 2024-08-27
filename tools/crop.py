import cv2 as cv
import numpy as np
from PySide6 import QtWidgets
from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QPen, QColor, QPainterPath, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem
from .crop_toolbar import CropToolBar
from .view import ViewTool
from filelist import DataKeys


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 0)
    PEN_UPSCALE   = createPen(255, 0, 0)

    BUTTON_CROP   = Qt.LeftButton


    def __init__(self, export):
        super().__init__()
        self._export = export

        self._targetWidth = 512
        self._targetHeight = 512

        self._cropHeight = 100.0
        self._cropAspectRatio = self._targetWidth / self._targetHeight

        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)) )

        self._toolbar = CropToolBar(self)


    def getToolbar(self):
        return self._toolbar


    def setTargetSize(self, width, height):
        self._targetWidth = round(width)
        self._targetHeight = round(height)
        self._cropAspectRatio = self._targetWidth / self._targetHeight


    def constrainCropSize(self, rotationMatrix, imgSize) -> (float, float):
        rectSel = QRectF(0, 0, self._cropAspectRatio, 1.0)
        rectSel = rotationMatrix.mapRect(rectSel)
        
        sizeRatioH = imgSize.height() / rectSel.height()
        sizeRatioW = imgSize.width() / rectSel.width()
        cropH = min(self._cropHeight, min(sizeRatioH, sizeRatioW))
        cropW = cropH * self._cropAspectRatio

        self._cropHeight = cropH
        return (cropW, cropH)

    def constraingCropPos(self, poly, imgSize):
        rect = poly.boundingRect()
        moveX, moveY = 0, 0
        
        if rect.x() < 0:
            moveX = -rect.x()
        if rect.y() < 0:
            moveY = -rect.y()
        
        if rect.right() > imgSize.width():
            moveX += imgSize.width() - rect.right()
        if rect.bottom() > imgSize.height():
            moveY += imgSize.height() - rect.bottom()
        
        poly.translate(moveX, moveY)

    def updateSelectionRect(self, mouseCoords: QPointF):
        rot = QTransform().rotate(-self._imgview.rotation)
        imgSize = self._imgview.image.pixmap().size()

        # Constrain selection size
        if self._toolbar.constrainSize():
            cropW, cropH = self.constrainCropSize(rot, imgSize)
        else:
            cropW, cropH = (self._cropHeight * self._cropAspectRatio), self._cropHeight
        
        # Map mouse coordinates to image space
        mouse = self._imgview.mapToScene(mouseCoords.toPoint())
        mouse = self._imgview.image.mapFromParent(mouse)

        # Calculate selected area in image space
        rect = QRect(-cropW/2, -cropH/2, cropW, cropH)
        poly = rot.mapToPolygon(rect)
        poly.translate(mouse.x(), mouse.y())

        # Constrain selection position
        if self._toolbar.constrainSize():
            self.constraingCropPos(poly, imgSize)

        # Map selected polygon to viewport
        poly = self._imgview.image.mapToParent(poly)
        poly = self._imgview.mapFromScene(poly)
        self._cropRect.setRect(poly.boundingRect())

    def updateSelection(self, mouseCoords: QPointF):
        self.updateSelectionRect(mouseCoords)

        self._mask.clipPath.clear()
        self._mask.clipPath.addRect(self._imgview.viewport().rect())
        self._mask.clipPath.addRect(self._cropRect.rect())

        # Change selection color depending on crop size
        pen = self.PEN_UPSCALE if self._cropHeight < self._targetHeight else self.PEN_DOWNSCALE
        if pen != self._cropRect.pen():
            self._cropRect.setPen(pen)

        self._imgview.scene().update()
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)

    def toCvMat(self, pixmap):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        pixmap.save(buffer, "PNG") # Preserve transparency with PNG

        buf = np.frombuffer(buffer.data(), dtype=np.uint8)
        return cv.imdecode(buf, cv.IMREAD_UNCHANGED)

    def calcCutRect(self, poly: QPolygonF, pixmap):
        pad  = 4
        rect = poly.boundingRect().toRect()

        rect.setLeft(max(0, rect.x()-pad))
        rect.setTop (max(0, rect.y()-pad))
        rect.setRight (min(pixmap.width(),  rect.right()+pad))
        rect.setBottom(min(pixmap.height(), rect.bottom()+pad))
        return rect

    def getExportPath(self):
        self._export.suffix = f"_{self._targetWidth}x{self._targetHeight}"
        return self._export.getExportPath(self._imgview.image.filepath)

    def exportImage(self, poly: QPolygonF):
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            return

        rect = self.calcCutRect(poly, pixmap)
        mat  = self.toCvMat( pixmap.copy(rect) )
        
        p0, p1, p2, _ = poly
        ox, oy = rect.topLeft().toTuple()
        ptsSrc = np.float32([
            [p0.x()-ox, p0.y()-oy],
            [p1.x()-ox, p1.y()-oy],
            [p2.x()-ox, p2.y()-oy]
        ])

        ptsDest = np.float32([
            [0, 0],
            [self._targetWidth, 0],
            [self._targetWidth, self._targetHeight],
        ])

        # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
        matrix  = cv.getAffineTransform(ptsSrc, ptsDest)
        dsize   = (self._targetWidth, self._targetHeight)
        interp  = self._toolbar.getInterpolationMode(self._targetHeight > self._cropHeight)
        border  = cv.BORDER_REPLICATE if self._toolbar.constrainSize() else cv.BORDER_CONSTANT
        matDest = cv.warpAffine(src=mat, M=matrix, dsize=dsize, flags=interp, borderMode=border)

        path = self.getExportPath()
        self._export.createFolders(path)
        params = self._toolbar.getSaveParams()
        cv.imwrite(path, matDest, params)
        print("Exported cropped image to", path)

        filelist = self._imgview.filelist
        filelist.setData(filelist.getCurrentFile(), DataKeys.CropState, DataKeys.IconStates.Saved)

    def onFileChanged(self, currentFile):
        self._toolbar.updateExport()

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)

    # === Tool Interface ===

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self._mask.setRect(self._imgview.viewport().rect())
        imgview._guiScene.addItem(self._mask)
        imgview._guiScene.addItem(self._cropRect)

        imgview.rotation = self._toolbar.slideRot.value() / 10
        imgview.updateImageTransform()

        self._toolbar.updateSize()
        imgview.filelist.addListener(self)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._mask)
        imgview._guiScene.removeItem(self._cropRect)

        imgview.rotation = 0.0
        imgview.updateImageTransform()

        imgview.filelist.removeListener(self)


    def onSceneUpdate(self):
        self.updateSelection(self._cropRect.rect().center())

    def onResetView(self):
        self._toolbar.slideRot.setValue(self._imgview.rotation)

    def onResize(self, event):
        self._mask.setRect(self._imgview.viewport().rect())


    def onMouseEnter(self, event):
        self._cropRect.setVisible(True)
        self._mask.setVisible(True)

    def onMouseMove(self, event):
        self.updateSelection(event.position())

    def onMouseLeave(self, event):
        self._cropRect.setVisible(False)
        self._mask.setVisible(False)
        self._imgview.scene().update()


    def onMousePress(self, event) -> bool:
        if event.button() != self.BUTTON_CROP:
            return super().onMousePress(event)
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return super().onMousePress(event)

        rect = self._cropRect.rect().toRect()
        rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
        poly = self._imgview.mapToScene(rect)
        poly = self._imgview.image.mapFromParent(poly)
        self.exportImage(poly)
        return True


    def onMouseWheel(self, event) -> bool:
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False
        
        change = self._imgview.image.pixmap().height() * 0.03
        if (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier:
            change = 1

        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self._cropHeight += wheelSteps * change
        self._cropHeight = round(max(self._cropHeight, 1))
        self.updateSelection(event.position())
        return True



class MaskRect(QGraphicsRectItem):
    def __init__(self):
        super().__init__(None)
        self.setFlag(QGraphicsItem.ItemClipsToShape, True)
        self.clipPath = QPainterPath()

    def shape(self) -> QPainterPath:
        return self.clipPath
