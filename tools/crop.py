import cv2 as cv
import numpy as np
from PySide6.QtCore import QBuffer, QPointF, QRect, QRectF, Qt, QTimer, QRunnable, QObject, QThreadPool, Signal, Slot
from PySide6.QtGui import QBrush, QPen, QColor, QPainterPath, QPolygonF, QTransform, QCursor
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QMenu
from .view import ViewTool
from lib.filelist import DataKeys
import ui.export_settings as export
from config import Config


# TODO: Upscale using model (whole image upscaled before crop so selected area matches target size? or upscale cropped region only?)

# TODO: Crop Modes:
#       - Start selection in top left corner, drag to bottom right corner
#       - Crop by selecting 4 points, transform using warpPerspective
#       - "Crop by Mask" mode for previewing effect of macros.
# TODO: Size modes for rect selection:
#       - Try to use same buckets: Quantize to Q, separate preview rect


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropToolSignals(QObject):
    sizePresetsUpdated = Signal(list)

CROP_SIGNALS = CropToolSignals()


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 0)
    PEN_UPSCALE   = createPen(255, 0, 0)

    BUTTON_CROP   = Qt.MouseButton.LeftButton
    BUTTON_MENU   = Qt.MouseButton.RightButton


    def __init__(self, tab):
        super().__init__(tab)

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

        from .crop_toolbar import CropToolBar
        self._toolbar = CropToolBar(self)
        CROP_SIGNALS.sizePresetsUpdated.connect(self._toolbar.onSizePresetsUpdated)

        self._menu = CropContextMenu(self)
        CROP_SIGNALS.sizePresetsUpdated.connect(self._menu.onSizePresetsUpdated)


    def setTargetSize(self, width, height):
        self._targetWidth = round(width)
        self._targetHeight = round(height)
        self._cropAspectRatio = self._targetWidth / self._targetHeight

    def swapCropSize(self):
        self._cropHeight = self._cropHeight / self._cropAspectRatio
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)


    def constrainCropSize(self, rotationMatrix, imgSize) -> tuple[float, float]:
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

        # Calculate selected area in image space
        mouse = self.mapPosToImage(mouseCoords)
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
    
    def resetSelection(self, mousePos: QPointF):
        self._waitForConfirmation = False
        self.updateSelection(mousePos)

    def exportImage(self, poly: QPolygonF) -> bool:
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            return False

        exportWidget = self._toolbar.exportWidget
        currentFile = self._imgview.image.filepath
        destFile = exportWidget.getExportPath(currentFile)
        if not destFile:
            return False

        self.tab.statusBar().showMessage("Saving cropped image...")

        interp = exportWidget.getInterpolationMode(self._targetHeight > self._cropHeight)
        border = cv.BORDER_REPLICATE if self._toolbar.constrainToImage else cv.BORDER_CONSTANT

        task = ExportTask(currentFile, destFile, pixmap, poly, self._targetWidth, self._targetHeight, interp, border)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)
        return True

    @Slot()
    def onExportDone(self, file, path):
        print("Exported cropped image to", path)
        self.tab.statusBar().showColoredMessage("Exported cropped image to: " + path, success=True)
        self._imgview.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)
        self._toolbar.updateExport()

    @Slot()
    def onExportFailed(self, msg: str):
        self.tab.statusBar().showColoredMessage(f"Export failed: {msg}", False, 0)


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

    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        imgview._guiScene.removeItem(self._mask)
        imgview._guiScene.removeItem(self._cropRect)
        imgview._guiScene.removeItem(self._confirmRect)

        imgview.rotation = 0.0
        imgview.updateImageTransform()


    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._waitForConfirmation = False
        self.setSelectionVisible(False)
        self.updateSelection(self._cropRect.rect().center())
        self._toolbar.updateExport()

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
                    if self.exportImage(poly):
                        self._confirmRect.setRect(rect)
                        self._confirmRect.startAnim()

                self.resetSelection(event.position())
            else:
                self._waitForConfirmation = True
            return True

        elif button == self.BUTTON_MENU:
            self._menu.exec_(self._imgview.mapToGlobal(event.position()).toPoint())
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
        fail = Signal(str)

        def __init__(self):
            super().__init__()

    def __init__(self, srcFile, destFile, pixmap, poly, targetWidth, targetHeight, interp, border):
        super().__init__()
        self.signals = self.ExportTaskSignals()

        self.srcFile = srcFile
        self.destFile = destFile
        self.poly = poly
        self.targetWidth  = targetWidth
        self.targetHeight = targetHeight
        self.interp = interp
        self.border = border

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

            # Origin of cut image (with padding), offset by half pixel to maintain pixel borders
            ox, oy = self.rect.topLeft().toTuple()
            ox, oy = ox+0.5, oy+0.5

            # Selection relative to origin of cut image
            # Round selection coordinates for pixel-accuracy
            ptsSrc = np.float32([
                [round(p0.x())-ox, round(p0.y())-oy],
                [round(p1.x())-ox, round(p1.y())-oy],
                [round(p2.x())-ox, round(p2.y())-oy]
            ])

            ptsDest = np.float32([
                [-0.5, -0.5],
                [self.targetWidth-0.5, -0.5],
                [self.targetWidth-0.5, self.targetHeight-0.5],
            ])

            # https://docs.opencv.org/3.4/da/d6e/tutorial_py_geometric_transformations.html
            matrix  = cv.getAffineTransform(ptsSrc, ptsDest)
            dsize   = (self.targetWidth, self.targetHeight)
            matSrc  = self.toCvMat(self.img)
            matDest = cv.warpAffine(src=matSrc, M=matrix, dsize=dsize, flags=self.interp, borderMode=self.border)

            export.saveImage(self.destFile, matDest)
            self.signals.done.emit(self.srcFile, self.destFile)

            del matSrc
            del matDest
        except Exception as ex:
            print(f"Export failed: {ex}")
            self.signals.fail.emit(str(ex))
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



class CropContextMenu(QMenu):
    def __init__(self, cropTool: CropTool):
        super().__init__()
        self.cropTool = cropTool
        self.onSizePresetsUpdated(Config.cropSizePresets)

    def onSizePresetsUpdated(self, presets: list[str]):
        self.clear()

        actResetSelection = self.addAction("Reset Selection")
        actResetSelection.triggered.connect(self._onResetSelection)
        self.addSeparator()

        for size in presets:
            actSize = self.addAction(size)
            actSize.triggered.connect(lambda chosen, text=size: self._onSizeSelected(text))
        
        self.addSeparator()
        actResetSelection = self.addAction("Swap")
        actResetSelection.triggered.connect(self._onSwap)

    def getMousePos(self) -> QPointF:
        mousePos = self.cropTool._imgview.mapFromGlobal( QCursor.pos() )
        return mousePos.toPointF()

    @Slot()
    def _onResetSelection(self):
        self.cropTool.resetSelection(self.getMousePos())

    def _onSizeSelected(self, text: str):
        self.cropTool._toolbar.sizePreset(text)
        self.cropTool.updateSelection(self.getMousePos())

    @Slot()
    def _onSwap(self):
        self.cropTool._toolbar.sizeSwap()
        self.cropTool.updateSelection(self.getMousePos())
