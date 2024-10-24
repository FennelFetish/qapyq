import cv2 as cv
import numpy as np
from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt, QTimer, QRunnable, QObject, QThreadPool, Signal, Slot
from PySide6.QtGui import QBrush, QPen, QColor, QPainterPath, QPolygonF, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem
from .crop_toolbar import CropToolBar
from .view import ViewTool
from lib.filelist import DataKeys
from config import Config


# TODO: Upscale using model (whole image upscaled before crop so selected area matches target size? or upscale cropped region only?)


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 0)
    PEN_UPSCALE   = createPen(255, 0, 0)

    BUTTON_CROP   = Qt.LeftButton
    BUTTON_ABORT  = Qt.RightButton


    def __init__(self, tab):
        super().__init__(tab)
        self._export = tab.export

        self._targetWidth = 512
        self._targetHeight = 512

        self._cropHeight = 100.0
        self._cropAspectRatio = self._targetWidth / self._targetHeight

        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)

        self._confirmRect = ConfirmRect(tab.imgview.scene())
        self._confirmRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)) )
        self._waitForConfirmation = False

        self._toolbar = CropToolBar(self)


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
        if not self._toolbar.allowUpscale:
            self._cropHeight = max(self._cropHeight, self._targetHeight)

        if self._toolbar.constrainToImage:
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
        if self._toolbar.constrainToImage:
            self.constraingCropPos(poly, imgSize)

        # Map selected polygon to viewport
        poly = self._imgview.image.mapToParent(poly)
        poly = self._imgview.mapFromScene(poly)
        self._cropRect.setRect(poly.boundingRect())

    def updateSelection(self, mouseCoords: QPointF):
        self.updateSelectionRect(mouseCoords)
        self._mask.setHighlightRegion(self._imgview.viewport().rect(), self._cropRect.rect())

        # Change selection color depending on crop size
        pen = self.PEN_UPSCALE if self._cropHeight < self._targetHeight else self.PEN_DOWNSCALE
        if pen != self._cropRect.pen():
            self._cropRect.setPen(pen)

        self._imgview.scene().update()
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)

    def setSelectionVisible(self, visible: bool):
        self._cropRect.setVisible(visible)
        self._mask.setVisible(visible)
        self._imgview.scene().update()

    def exportImage(self, poly: QPolygonF):
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            return

        self.tab.statusBar().showMessage("Saving cropped image...")

        currentFile = self._imgview.image.filepath
        interp = self._toolbar.getInterpolationMode(self._targetHeight > self._cropHeight)
        border = cv.BORDER_REPLICATE if self._toolbar.constrainToImage else cv.BORDER_CONSTANT
        params = self._toolbar.getSaveParams()

        task = ExportTask(self._export, currentFile, pixmap, poly, self._targetWidth, self._targetHeight, interp, border, params)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot()
    def onExportDone(self, file, path):
        print("Exported cropped image to", path)
        self.tab.statusBar().showColoredMessage("Exported cropped image to: " + path, success=True)
        self._imgview.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)
    
    @Slot()
    def onExportFailed(self):
        self.tab.statusBar().showColoredMessage("Export failed", success=False)


    def onFileChanged(self, currentFile):
        self._toolbar.updateExport()

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    # === Tool Interface ===

    def getToolbar(self):
        return self._toolbar

    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self._mask.setRect(self._imgview.viewport().rect())
        imgview._guiScene.addItem(self._mask)
        imgview._guiScene.addItem(self._cropRect)
        imgview._guiScene.addItem(self._confirmRect)

        imgview.rotation = self._toolbar.rotation
        imgview.updateImageTransform()

        self._toolbar.updateSize()
        imgview.filelist.addListener(self)

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._mask)
        imgview._guiScene.removeItem(self._cropRect)
        imgview._guiScene.removeItem(self._confirmRect)

        imgview.rotation = 0.0
        imgview.updateImageTransform()

        imgview.filelist.removeListener(self)


    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._waitForConfirmation = False
        self.setSelectionVisible(False)
        self.updateSelection(self._cropRect.rect().center())

    def onResetView(self):
        self._toolbar.rotation = self._imgview.rotation

    def onResize(self, event):
        self._mask.setRect(self._imgview.viewport().rect())


    def onMouseEnter(self, event):
        self.setSelectionVisible(True)

    def onMouseMove(self, event):
        super().onMouseMove(event)
        if not self._mask.isVisible():
            self.setSelectionVisible(True)
        if not self._waitForConfirmation:
            self.updateSelection(event.position())

    def onMouseLeave(self, event):
        if not self._waitForConfirmation:
            self.setSelectionVisible(False)


    def onMousePress(self, event) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return super().onMousePress(event)
        
        button = event.button()
        if button == self.BUTTON_CROP:
            if self._waitForConfirmation:
                rect = self._cropRect.rect().toRect()
                rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))

                # Start export if mouse click is inside selection rectangle
                if rect.contains(event.position().toPoint()):
                    poly = self._imgview.mapToScene(rect)
                    poly = self._imgview.image.mapFromParent(poly)
                    self.exportImage(poly)

                    self._confirmRect.setRect(rect)
                    self._confirmRect.startAnim()

                self._waitForConfirmation = False
                self.updateSelection(event.position())
            else:
                self._waitForConfirmation = True
            return True
        
        elif button == self.BUTTON_ABORT:
            self._waitForConfirmation = False
            self.updateSelection(event.position())
            return True

        return super().onMousePress(event)


    def onMouseWheel(self, event) -> bool:
        # CTRL pressed -> Use default controls (zoom)
        if (event.modifiers() & Qt.ControlModifier) == Qt.ControlModifier:
            return False
        
        if self._waitForConfirmation:
            return True
        
        change = round(self._imgview.image.pixmap().height() * Config.cropWheelStep)
        if (event.modifiers() & Qt.ShiftModifier) == Qt.ShiftModifier:
            change = 1

        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self._cropHeight += wheelSteps * change
        self._cropHeight = round(max(self._cropHeight, 1))
        self.updateSelection(event.position())
        return True



class ExportTask(QRunnable):
    class ExportTaskSignals(QObject):
        done = Signal(str, str)
        fail = Signal()

        def __init__(self):
            super().__init__()

    def __init__(self, export, file, pixmap, poly, targetWidth, targetHeight, interp, border, saveParams):
        super().__init__()
        self.signals = self.ExportTaskSignals()

        self.export = export
        export.suffix = f"_{targetWidth}x{targetHeight}"
        self.destFile = export.getExportPath(file)

        self.srcFile = file
        self.poly = poly
        self.targetWidth  = targetWidth
        self.targetHeight = targetHeight
        self.interp = interp
        self.border = border
        self.saveParams = saveParams
        self.rect = self.calcCutRect(poly, pixmap)
        self.img = pixmap.copy(self.rect).toImage()

    def calcCutRect(self, poly: QPolygonF, pixmap):
        pad  = 4
        rect = poly.boundingRect().toRect()

        rect.setLeft(max(0, rect.x()-pad))
        rect.setTop (max(0, rect.y()-pad))
        rect.setRight (min(pixmap.width(),  rect.right()+pad))
        rect.setBottom(min(pixmap.height(), rect.bottom()+pad))
        return rect

    def toCvMat(self, image):
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        image.save(buffer, "PNG", 100) # Preserve transparency with PNG. quality 100 actually fastest?

        buf = np.frombuffer(buffer.data(), dtype=np.uint8)
        return cv.imdecode(buf, cv.IMREAD_UNCHANGED)

    @Slot()
    def run(self):
        try:
            p0, p1, p2, _ = self.poly
            ox, oy = self.rect.topLeft().toTuple()
            ptsSrc = np.float32([
                [p0.x()-ox, p0.y()-oy],
                [p1.x()-ox, p1.y()-oy],
                [p2.x()-ox, p2.y()-oy]
            ])

            ptsDest = np.float32([
                [0, 0],
                [self.targetWidth, 0],
                [self.targetWidth, self.targetHeight],
            ])

            # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
            matrix  = cv.getAffineTransform(ptsSrc, ptsDest)
            dsize   = (self.targetWidth, self.targetHeight)
            matSrc  = self.toCvMat(self.img)
            matDest = cv.warpAffine(src=matSrc, M=matrix, dsize=dsize, flags=self.interp, borderMode=self.border)

            self.export.createFolders(self.destFile)
            cv.imwrite(self.destFile, matDest, self.saveParams)
            self.signals.done.emit(self.srcFile, self.destFile)

            del matSrc
            del matDest
        except Exception as ex:
            print("Error while exporting:")
            print(ex)
            self.signals.fail.emit()
        finally:
            del self.img



class MaskRect(QGraphicsRectItem):
    def __init__(self):
        super().__init__(None)
        self.setFlag(QGraphicsItem.ItemClipsToShape, True)
        self._clipPath = QPainterPath()
    
    def setHighlightRegion(self, viewportRect, selectionRect) -> None:
        self._clipPath.clear()
        self._clipPath.addRect(viewportRect)
        self._clipPath.addRect(selectionRect)

    def shape(self) -> QPainterPath:
        return self._clipPath



class ConfirmRect(QGraphicsRectItem):
    ALPHA = 100

    def __init__(self, scene):
        super().__init__(None)
        self._scene = scene
        self.alpha = ConfirmRect.ALPHA

        self.color = QColor(60, 255, 60, self.alpha)
        self.brush = QBrush(self.color)
        self.setBrush(self.brush)
        self.setPen(QPen(QColor(0, 0, 0, 0)))
        
        self.timer = QTimer()
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.anim)

    def startAnim(self):
        self.alpha = ConfirmRect.ALPHA
        self.setVisible(True)
        self.timer.start()

    def anim(self):
        if self.alpha <= 0:
            self.timer.stop()
            self.setVisible(False)
            return

        self.color.setAlpha(self.alpha)
        self.brush.setColor(self.color)
        self.setBrush(self.brush)
        self._scene.update()

        self.alpha = max(0, self.alpha-7)
