from typing import TYPE_CHECKING
from typing_extensions import override
import cv2 as cv
import numpy as np
from PySide6.QtCore import Qt, Slot, QPointF, QRect, QRectF, QSize, QTimer, QThreadPool
from PySide6.QtGui import QBrush, QPen, QColor, QPainterPath, QPolygonF, QTransform, QCursor, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QMenu
from lib import videorw
from lib.filelist import DataKeys
from ui.imgview import ImgView, MediaItemMixin
from ui.effect import ConfirmRect
from ui.size_preset import SIZE_PRESET_SIGNALS
import ui.export_settings as export
from config import Config
from .view import ViewTool

if TYPE_CHECKING:
    from ui.video_player import VideoItem


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
        self._cropRect = SelectionRect(-50, -50, 100, 100)
        self._cropRect.setPen(self.PEN_UPSCALE)
        self._cropRect.setVisible(False)
        self._lastCenter = QPointF() # For nudging

        self._confirmRect = ConfirmRect(tab.imgview.scene())

        self._mask = MaskRect()
        self._mask.setBrush( QBrush(QColor(0, 0, 0, 100)) )
        self._selectionFixed = False

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


    # TODO: Buggy when rotated by 90, and then moving rect
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

        imgSize = self._imgview.image.mediaSize()

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


    def constrainCropSize(self, rotationMatrix: QTransform, imgSize: QSize) -> tuple[float, float]:
        rectSel = QRectF(0, 0, self._cropAspectRatio, 1.0)
        rectSel = rotationMatrix.mapRect(rectSel) # Bounds

        sizeRatioH = imgSize.height() / rectSel.height()
        sizeRatioW = imgSize.width() / rectSel.width()
        cropH = min(self._cropHeight, min(sizeRatioH, sizeRatioW))
        cropW = cropH * self._cropAspectRatio

        self._cropHeight = cropH
        return (cropW, cropH)

    def constrainCropPos(self, poly: QPolygonF, imgSize: QSize):
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
        imgSize = self._imgview.image.mediaSize()

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
        poly = rot.map(QPolygonF(rect))
        poly.translate(int(mouse.x()), int(mouse.y()))

        # Constrain selection position
        if self._toolbar.constrainToImage:
            self.constrainCropPos(poly, imgSize)

        self._cropRect.setCropPoly(poly, self._imgview)

    def updateSelection(self, mouseCoords: QPointF):
        self._lastCenter.setX(mouseCoords.x())
        self._lastCenter.setY(mouseCoords.y())

        self.updateSelectionRect(mouseCoords)
        self._mask.setHighlightRegion(self.mapImageToViewport(), self._cropRect.rect())

        # Change selection color depending on crop size
        pen = self.PEN_UPSCALE if self._cropHeight < self._targetHeight else self.PEN_DOWNSCALE
        if pen != self._cropRect.pen():
            self._cropRect.setPen(pen)

        self._imgview.scene().update()
        self._toolbar.setSelectionSize(self._cropHeight * self._cropAspectRatio, self._cropHeight)

    def setSelectionVisible(self, visible: bool):
        needsUpdate = (self._cropRect.isVisible() != visible) or (self._mask.isVisible() != visible)
        if needsUpdate:
            self._cropRect.setVisible(visible)
            self._mask.setVisible(visible)
            self._imgview.scene().update()

    def setSelectionFixed(self, fixed: bool):
        self._selectionFixed = fixed
        self.updateTimeSegment()

    def resetSelection(self, mousePos: QPointF | None = None):
        self.setSelectionFixed(False)
        if mousePos is None:
            self.setSelectionVisible(False)
        else:
            self.updateSelection(mousePos)


    def updateTimeSegment(self, setStart: bool = True):
        if not self._imgview:
            return

        item: VideoItem = self._imgview.image
        if item.TYPE != MediaItemMixin.ItemType.Video:
            return

        if not self._selectionFixed:
            item.clearSegment()
            return

        if self._toolbar.needTimeSegment():
            length = self._toolbar.getDurationMs()
            start  = item.player.position() if setStart else item.segmentStart
            end    = start + length
            item.setSegment(start, end)
        else:
            item.player.pause()
            item.clearSegment()


    def export(self, selectionRect: QRect) -> bool:
        poly = self._cropRect.cropPoly
        if not poly:
            return False

        item = self._imgview.image
        if not item.mediaSize().isValid():
            return False

        destFile = self._toolbar.exportWidget.getExportPath(item.filepath)
        if not destFile:
            return False

        self.tab.statusBar().showMessage("Starting export...")

        try:
            if videorw.isVideoFile(destFile):
                self.exportVideo(item.filepath, destFile, poly)
            else:
                self.exportImage(item.filepath, destFile, poly)

            self._confirmRect.startFade(selectionRect)
            return True

        except Exception as ex:
            self.tab.statusBar().showColoredMessage(f"Export failed: {ex} ({type(ex).__name__})", False, 0)
            return False

    def exportImage(self, currentFile: str, destFile: str, poly: QPolygonF):
        pixmap = self._imgview.image.pixmap()
        if not pixmap:
            raise ValueError("No image")

        scaleFactor = self._targetHeight / self._cropHeight
        scaleConfig = self._toolbar.exportWidget.getScaleConfig(scaleFactor)
        border = cv.BORDER_REPLICATE if self._toolbar.constrainToImage else cv.BORDER_CONSTANT

        task = ExportTask(currentFile, destFile, pixmap, poly, self._targetWidth, self._targetHeight, scaleConfig, border)
        task.signals.done.connect(self.onExportDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.progress.connect(self.onExportProgress, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self.onExportFailed, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    def exportVideo(self, currentFile: str, destFile: str, poly: QPolygonF):
        item: VideoItem = self._imgview.image
        if item.TYPE != MediaItemMixin.ItemType.Video:
            raise ValueError("Current file is not a video")

        numFrames = self._toolbar.spinLength.value()
        if numFrames < 2:
            raise ValueError("Video must have more than 1 frame")

        srcPos = item.segmentStart
        if srcPos < 0:
            raise ValueError("No time range selected")

        srcSize = item.mediaSize()
        targetSize = QSize(self._targetWidth, self._targetHeight)
        rot = self._imgview.rotation

        fps = self._toolbar.exportWidget.getFps()
        Config.exportVideoFps = fps

        proc = videorw.VideoExportProcess(self.tab, currentFile, srcSize, srcPos, destFile, poly, targetSize, rot, numFrames, fps)
        proc.done.connect(self.onExportDone, Qt.ConnectionType.QueuedConnection)
        proc.progress.connect(self.onExportProgress, Qt.ConnectionType.QueuedConnection)
        proc.fail.connect(self.onExportFailed, Qt.ConnectionType.QueuedConnection)
        proc.start()


    @Slot()
    def onExportDone(self, file, path):
        fileType = "video" if videorw.isVideoFile(path) else "image"

        message = f"Exported cropped {fileType} to: {path}"
        print(message)
        self.tab.statusBar().showColoredMessage(message, success=True)

        self.tab.filelist.setData(file, DataKeys.CropState, DataKeys.IconStates.Saved)
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

        item: VideoItem = imgview.image
        if item.TYPE == MediaItemMixin.ItemType.Video:
            item.clearSegment()


    def onSceneUpdate(self):
        super().onSceneUpdate()
        self.setSelectionFixed(False)
        self.setSelectionVisible(False)
        self.updateSelection(self._cropRect.rect().center())
        self._toolbar.updateExport()

    def onResetView(self):
        self._toolbar.rotation = self._imgview.rotation

    def onResize(self, event):
        self._mask.setRect(self._imgview.viewport().rect())

    def onMediaSkip(self, insideSegment: bool):
        if not insideSegment:
            self.resetSelection()


    def onMouseEnter(self, event):
        self.setSelectionVisible(True)

    def onMouseMove(self, event):
        super().onMouseMove(event)
        if not self._mask.isVisible():
            self.setSelectionVisible(True)
        if not self._selectionFixed:
            self.updateSelection(event.position())

    def onMouseLeave(self, event):
        if not self._selectionFixed:
            self.setSelectionVisible(False)


    def onMousePress(self, event) -> bool:
        # CTRL pressed -> Use default controls (pan)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().onMousePress(event)

        match event.button():
            case self.BUTTON_CROP:
                if self._selectionFixed:
                    # Start export if mouse click is inside selection rectangle
                    rect = self._cropRect.rect().toRect()
                    rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
                    if rect.contains(event.position().toPoint()):
                        self.export(rect)
                    self.resetSelection(event.position())
                else:
                    self.setSelectionFixed(True)

                return True

            case self.BUTTON_SWAP:
                self.setSelectionFixed(False)
                self._menu._onSwap()
                return True

            case self.BUTTON_MENU:
                self._menu.exec_(self._imgview.mapToGlobal(event.position()).toPoint())
                self.setSelectionFixed(False)
                return True

        return super().onMousePress(event)


    def onMouseWheel(self, event) -> bool:
        # CTRL pressed -> Use default controls (zoom)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return False

        if self._selectionFixed:
            return True

        change = round(self._imgview.image.mediaSize().height() * Config.cropWheelStep)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            change = 1

        wheelSteps = event.angleDelta().y() / 120.0 # 8*15° standard
        self._cropHeight += wheelSteps * change
        self._cropHeight = round(max(self._cropHeight, 1))
        self.updateSelection(event.position())
        return True


    def onKeyPress(self, event):
        if not self._selectionFixed:
            return super().onKeyPress(event)

        # SHIFT: Bigger steps for nudge and resize
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            match event.key():
                case Qt.Key.Key_E:
                    rect = self._cropRect.rect().toRect()
                    rect.setRect(rect.x(), rect.y(), max(1, rect.width()), max(1, rect.height()))
                    self.export(rect)
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
        self.rect = self.calcCutRect(poly, pixmap.size())

        super().__init__(srcFile, destFile, pixmap, targetWidth, targetHeight, scaleConfig)
        self.borderMode = border

    @staticmethod
    def calcCutRect(poly: QPolygonF, imgSize: QSize, pad: int = 4) -> QRect:
        rect = poly.boundingRect().toRect()
        if rect.right() < 0 or rect.left() >= imgSize.width() or rect.bottom() < 0 or rect.top() >= imgSize.height():
            raise EmptyRegionException("Empty region")

        # Try to pad so the resulting dimensions are even.
        # This avoids padding of the crop region when downscaling with reduce.
        x = max(0, rect.x()-pad)
        w = min(imgSize.width()-1,  rect.right()+pad) - x + 1
        if w & 1:
            if x > 0:
                x -= 1
                w += 1
            elif x+w < imgSize.width():
                w += 1

        y = max(0, rect.y()-pad)
        h = min(imgSize.height()-1, rect.bottom()+pad) - y + 1
        if h & 1:
            if y > 0:
                y -= 1
                h += 1
            elif y+h < imgSize.height():
                h += 1

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



class SelectionRect(QGraphicsRectItem):
    def __init__(self, x: float, y: float, w: float, h: float):
        super().__init__(x, y, w, h)
        self._cropPoly: QPolygonF = None

    @property
    def cropPoly(self):
        return QPolygonF(self._cropPoly.sliced(0, 4))

    def setCropPoly(self, poly: QPolygonF, imgview: ImgView):
        self._cropPoly = poly

        # Map selected polygon to viewport
        polyMapped = imgview.image.mapToParent(poly)
        polyMapped = imgview.mapFromScene(polyMapped)
        self.setRect(polyMapped.boundingRect())



class MaskRect(QGraphicsRectItem):
    def __init__(self):
        super().__init__(None)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self._clipPath = QPainterPath()

    def setHighlightRegion(self, imgPoly, selectionRect) -> None:
        self._clipPath.clear()
        self._clipPath.addPolygon(imgPoly)
        self._clipPath.addRect(selectionRect)

    def shape(self) -> QPainterPath:
        return self._clipPath



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

        actSwap = self.addAction("Swap Size")
        actSwap.triggered.connect(self._onSwap)

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
        w, h, *length = text.split("x")
        l = int(length[0]) if length else -1
        self.cropTool._toolbar.selectSizePreset(int(w), int(h), l)
        self.cropTool.updateSelection(self.getMousePos())

    @Slot()
    def _onSwap(self):
        self.cropTool._toolbar.sizeSwap()
        self.cropTool.updateSelection(self.getMousePos())
