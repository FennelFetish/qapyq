from typing_extensions import override
import cv2 as cv
import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, QThreadPool, Slot
from PySide6.QtGui import QBrush, QPen, QColor, QPainterPath, QPolygonF, QTransform, QCursor, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QMenu
from .view import ViewTool
from lib.filelist import DataKeys
import ui.export_settings as export
from ui.size_preset import SIZE_PRESET_SIGNALS
from config import Config


# TODO: Crop Modes:
#       - Start selection in top left corner, drag to bottom right corner
#       - Crop by selecting 4 points, transform using warpPerspective
#       - "Crop by Mask" mode for previewing effect of macros.
# TODO: Size modes for rect selection:
#       - Try to use same buckets: Quantize to Q, separate preview rect
# TODO: Display cropped image in extra window that can be toggled from CropToolBar


def createPen(r, g, b):
    pen = QPen( QColor(r, g, b, 180) )
    pen.setDashPattern([5,5])
    return pen


class CropTool(ViewTool):
    PEN_DOWNSCALE = createPen(0, 255, 0)
    PEN_UPSCALE   = createPen(255, 0, 0)

    BUTTON_CROP   = Qt.MouseButton.LeftButton
    BUTTON_SWAP   = Qt.MouseButton.MiddleButton
    BUTTON_MENU   = Qt.MouseButton.RightButton


    def __init__(self, tab):
        super().__init__(tab)

        self._targetWidth = 512
        self._targetHeight = 512

        self._cropHeight = 100.0
        self._cropAspectRatio = self._targetWidth / self._targetHeight

        # Crop rectangle in view space
        self._cropRect = QGraphicsRectItem(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)
        self._lastCenter = QPointF() # For nudging

        self._confirmRect = ConfirmRect(tab.imgview.scene())
        self._confirmRect.setVisible(False)

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)) )
        self._waitForConfirmation = False

        self._lastExportedFile = ""

        from .crop_toolbar import CropToolBar
        self._toolbar = CropToolBar(self)
        self._menu = CropContextMenu(self)


    def setTargetSize(self, width, height):
        self._targetWidth = round(width)
        self._targetHeight = round(height)
        self._cropAspectRatio = self._targetWidth / self._targetHeight

    def swapCropSize(self):
        self._cropHeight = self._cropHeight / self._cropAspectRatio
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)


    # TODO: Buggy when nudging outside of image edges when the image is rotated ('_lastCenter' moves outside). -> use polygon for constraing pos to image
    # TODO: Buggy when growing selection when image is rotated: It will also move the edge that should be kept.
    # TODO: Buggy when growing outside of image edges: It will grow in the other direction. It should stop growing instead.
    def nudgeSelectionRect(self, offsetX: float, offsetY: float, heightChange=0.0) -> None:
        # When a big image is zoomed out and multiple image pixels are covered by one screen pixel,
        # increase the step size to at least 1 screen pixel. Without this, the selection won't move.
        pxScale = QRect(0, 0, 1, 1)
        pxScale = self._imgview.mapToScene(pxScale)
        pxScale = self._imgview.image.mapFromParent(pxScale).boundingRect()

        pxScaleX = max(1.0, pxScale.width())
        pxScaleY = max(1.0, pxScale.height())

        imgSize = self._imgview.image.pixmap().size()

        if heightChange != 0.0:
            newHeight = self._cropHeight + (heightChange * pxScaleY)
            if (not self._toolbar.allowUpscale) and newHeight < self._targetHeight:
                return
            if self._toolbar.constrainToImage and (newHeight > imgSize.height() or (newHeight * self._cropAspectRatio) > imgSize.width()):
                return
            self._cropHeight = newHeight

        # Create direction vector in image space
        pxStep = QPointF(offsetX * pxScaleX, offsetY * pxScaleY)
        rot = QTransform().rotate(-self._imgview.rotation)
        pxStep = rot.map(pxStep)

        # Get current selection center in image space and offset it.
        x, y = self.mapPosToImageInt(self._lastCenter)
        x += pxStep.x()
        y += pxStep.y()

        if self._toolbar.constrainToImage:
            cropH = self._cropHeight // 2
            cropW = (self._cropHeight * self._cropAspectRatio) // 2

            # TODO: With rotation we have to check the polygon's bbox here?
            x = max(x, cropW)
            x = min(x, imgSize.width()-cropW)
            y = max(y, cropH)
            y = min(y, imgSize.height()-cropH)

        # Offset by half pixel to base calculation on pixel center.
        pImg  = QPointF(x+0.5, y+0.5)
        pView = self.mapPosFromImage(pImg).toPointF()
        self.updateSelection(pView)


    def constrainCropSize(self, rotationMatrix, imgSize) -> tuple[float, float]:
        rectSel = QRectF(0, 0, self._cropAspectRatio, 1.0)
        rectSel = rotationMatrix.mapRect(rectSel)

        sizeRatioH = imgSize.height() / rectSel.height()
        sizeRatioW = imgSize.width() / rectSel.width()
        cropH = min(self._cropHeight, min(sizeRatioH, sizeRatioW))
        cropW = cropH * self._cropAspectRatio

        self._cropHeight = cropH
        return (cropW, cropH)

    def constrainCropPos(self, poly, imgSize):
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
        rect = QRect(-np.floor(cropW/2), -np.floor(cropH/2), round(cropW), round(cropH))
        poly = rot.mapToPolygon(rect)
        poly.translate(int(mouse.x()), int(mouse.y()))

        # Constrain selection position
        if self._toolbar.constrainToImage:
            self.constrainCropPos(poly, imgSize)

        # Map selected polygon to viewport
        poly = self._imgview.image.mapToParent(poly)
        poly = self._imgview.mapFromScene(poly)
        self._cropRect.setRect(poly.boundingRect())

    def updateSelection(self, mouseCoords: QPointF):
        self._lastCenter.setX(mouseCoords.x())
        self._lastCenter.setY(mouseCoords.y())

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

    def getSelectionPoly(self, rect: QRect) -> QPolygonF:
        poly = self._imgview.mapToScene(rect)
        poly = self._imgview.image.mapFromParent(poly)

        # Constrain polygon to image (again, to account for rounding errors)
        if self._toolbar.constrainToImage:
            imgSize = self._imgview.image.pixmap().size()
            for i in range(poly.size()):
                p = poly[i]
                x = min(p.x(), imgSize.width())
                x = max(x, 0)

                y = min(p.y(), imgSize.height())
                y = max(y, 0)
                poly[i] = QPointF(x, y)

        return poly

    def exportImage(self, selectionRect: QRect) -> bool:
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            return False

        exportWidget = self._toolbar.exportWidget
        currentFile = self._imgview.image.filepath
        destFile = exportWidget.getExportPath(currentFile)
        if not destFile:
            return False

        self.tab.statusBar().showMessage("Exporting image...")

        poly = self.getSelectionPoly(selectionRect)
        scaleFactor = self._targetHeight / self._cropHeight
        scaleConfig = exportWidget.getScaleConfig(scaleFactor)
        border = cv.BORDER_REPLICATE if self._toolbar.constrainToImage else cv.BORDER_CONSTANT

        try:
            task = ExportTask(currentFile, destFile, pixmap, poly, self._targetWidth, self._targetHeight, scaleConfig, border)
        except EmptyRegionException:
            self.tab.statusBar().showColoredMessage("Empty region", False)
            return False

        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.progress.connect(self.onExportProgress, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

        self._confirmRect.setRect(selectionRect)
        self._confirmRect.startAnim()
        return True

    @Slot()
    def onExportDone(self, file, path):
        message = f"Exported cropped image to: {path}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)

        self._imgview.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)
        self._toolbar.updateExport()
        self._lastExportedFile = path

    @Slot()
    def onExportProgress(self, message: str):
        self.tab.statusBar().showMessage(message)

    @Slot()
    def onExportFailed(self, msg: str):
        self.tab.statusBar().showColoredMessage(f"Export failed: {msg}", False, 0)


    @Slot()
    def openLastExportedFile(self):
        if self._lastExportedFile:
            tab = self.tab.mainWindow.addTab()
            tab.filelist.load(self._lastExportedFile)


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
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().onMousePress(event)

        match event.button():
            case self.BUTTON_CROP:
                if self._waitForConfirmation:
                    # Start export if mouse click is inside selection rectangle
                    rect = self._cropRect.rect().toRect()
                    rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
                    if rect.contains(event.position().toPoint()):
                        self.exportImage(rect)
                    self.resetSelection(event.position())
                else:
                    self._waitForConfirmation = True
                return True

            case self.BUTTON_SWAP:
                self._waitForConfirmation = False
                self._menu._onSwap()
                return True

            case self.BUTTON_MENU:
                self._menu.exec_(self._imgview.mapToGlobal(event.position()).toPoint())
                self._waitForConfirmation = False
                return True

        return super().onMousePress(event)


    def onMouseWheel(self, event) -> bool:
        # CTRL pressed -> Use default controls (zoom)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False

        if self._waitForConfirmation:
            return True

        change = round(self._imgview.image.pixmap().height() * Config.cropWheelStep)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            change = 1

        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self._cropHeight += wheelSteps * change
        self._cropHeight = round(max(self._cropHeight, 1))
        self.updateSelection(event.position())
        return True


    def onKeyPress(self, event):
        if not self._waitForConfirmation:
            return super().onKeyPress(event)

        # SHIFT: Bigger steps for nudge and resize
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            match event.key():
                case Qt.Key.Key_E:
                    rect = self._cropRect.rect().toRect()
                    rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
                    self.exportImage(rect)
                    return

            # Ctrl+Arrow: Grow selection size
            if self._onKeyPressNudge(event.key(), step, 2):
                return

        elif event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Alt+Arrow: Shrink selection size
            if self._onKeyPressNudge(event.key(), -step, 2):
                return

        else:
            # Arrow Keys: Nudge selection position
            if self._onKeyPressNudge(event.key(), step, 0):
                return

        return super().onKeyPress(event)

    def _onKeyPressNudge(self, key: Qt.Key, change: int, heightChange: float) -> bool:
        heightChange *= change
        match key:
            case Qt.Key.Key_Left:
                self.nudgeSelectionRect(-change, 0, heightChange/self._cropAspectRatio)
                return True
            case Qt.Key.Key_Right:
                self.nudgeSelectionRect(change, 0, heightChange/self._cropAspectRatio)
                return True
            case Qt.Key.Key_Up:
                self.nudgeSelectionRect(0, -change, heightChange)
                return True
            case Qt.Key.Key_Down:
                self.nudgeSelectionRect(0, change, heightChange)
                return True

        return False



class EmptyRegionException(Exception): pass

class ExportTask(export.ImageExportTask):
    def __init__(self, srcFile: str, destFile: str, pixmap: QPixmap, poly: QPolygonF, targetWidth: int, targetHeight: int, scaleConfig: export.ScaleConfig, border: int):
        self.poly = poly
        self.rect = self.calcCutRect(poly, pixmap)

        super().__init__(srcFile, destFile, pixmap, targetWidth, targetHeight, scaleConfig)
        self.borderMode = border

    @staticmethod
    def calcCutRect(poly: QPolygonF, pixmap: QPixmap) -> QRect:
        pad  = 4
        rect = poly.boundingRect().toRect()

        if rect.right() < 0 or rect.left() >= pixmap.width() or rect.bottom() < 0 or rect.top() >= pixmap.height():
            raise EmptyRegionException()

        x = max(0, rect.x()-pad)
        y = max(0, rect.y()-pad)
        w = min(pixmap.width(),  rect.right()+pad)  - x + 1
        h = min(pixmap.height(), rect.bottom()+pad) - y + 1

        rect.setRect(x, y, w, h)
        return rect

    @override
    def toImage(self, pixmap: QPixmap):
        return pixmap.copy(self.rect).toImage()

    @override
    def processImage(self, mat: np.ndarray) -> np.ndarray:
        p0, p1, p2, _ = self.poly

        # Origin of cut image (with padding), offset by half pixel to maintain pixel borders
        ox, oy = self.rect.topLeft().toTuple()
        ox, oy = ox+0.5, oy+0.5

        # Selection relative to origin of cut image
        # Round selection coordinates for pixel-accuracy
        ptsSrc = [
            [round(p0.x())-ox, round(p0.y())-oy],
            [round(p1.x())-ox, round(p1.y())-oy],
            [round(p2.x())-ox, round(p2.y())-oy]
        ]

        ptsDest = [
            [-0.5, -0.5],
            [self.targetWidth-0.5, -0.5],
            [self.targetWidth-0.5, self.targetHeight-0.5],
        ]

        return self.warpAffine(mat, ptsSrc, ptsDest)

    @override
    def inferUpscale(self, mat: np.ndarray) -> np.ndarray:
        hOrig, wOrig = mat.shape[:2]
        mat = super().inferUpscale(mat)
        h, w = mat.shape[:2]

        # Adjust poly and rect
        wScale = w / wOrig
        hScale = h / hOrig

        for i in range(self.poly.size()):
            p = self.poly[i]
            x = round(p.x()) * wScale
            y = round(p.y()) * hScale
            self.poly[i] = QPointF(x, y)

        x = int(self.rect.left() * wScale)
        y = int(self.rect.top() * hScale)
        self.rect.setCoords(x, y, x+w-1, y+h-1)

        return mat



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
        SIZE_PRESET_SIGNALS.sizePresetsUpdated.connect(self.onSizePresetsUpdated)

    @Slot()
    def onSizePresetsUpdated(self, presets: list[str]):
        self.clear()

        actResetSelection = self.addAction("Reset Selection")
        actResetSelection.triggered.connect(self._onResetSelection)

        actResetSelection = self.addAction("Swap")
        actResetSelection.triggered.connect(self._onSwap)

        self.addSeparator()

        for size in presets:
            actSize = self.addAction(size)
            actSize.triggered.connect(lambda chosen, text=size: self._onSizeSelected(text))

    def getMousePos(self) -> QPointF:
        mousePos = self.cropTool._imgview.mapFromGlobal( QCursor.pos() )
        return mousePos.toPointF()

    @Slot()
    def _onResetSelection(self):
        self.cropTool.resetSelection(self.getMousePos())

    def _onSizeSelected(self, text: str):
        w, h = text.split("x")
        self.cropTool._toolbar.selectSizePreset(int(w), int(h))
        self.cropTool.updateSelection(self.getMousePos())

    @Slot()
    def _onSwap(self):
        self.cropTool._toolbar.sizeSwap()
        self.cropTool.updateSelection(self.getMousePos())
