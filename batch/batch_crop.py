import os, re
from enum import Enum
from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import cv2 as cv
import numpy as np
from config import Config
from lib import qtlib
from lib.mask_macro import MaskingMacro, ChainedMacroRunner
import lib.imagerw as imagerw
from infer.inference import InferenceChain
import ui.export_settings as export
from ui.size_preset import SizeBucket, SizePresetWidget
from .batch_task import BatchTask, BatchInferenceTask, BatchTaskHandler, BatchUtil
from .batch_log import BatchLog


# TODO: Set which mask layers are used to define crop region (last layer, layer nr, each layer defines a region, maximum)

# TODO: When writing multiple regions into multiple files, when Size Factor is large, the regions may overlap.
#       Should this be handled when writing output mask is enabled? Remove other regions from mask?


class InputMaskType(Enum):
    Macro = "macro"
    File  = "file"
    Alpha = "alpha"

class OutputMaskType(Enum):
    Discard = "discard"
    File    = "file"
    Alpha   = "alpha"



class BatchCrop(QtWidgets.QWidget):
    EXPORT_PRESET_KEY_INMASK  = "batch-crop-mask-in"
    EXPORT_PRESET_KEY_OUTMASK = "batch-crop-mask-out"
    EXPORT_PRESET_KEY_IMG     = "batch-crop"

    BUCKET_SPLIT = re.compile(r'[ ,x]')

    def __init__(self, tab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler(bars, "Crop", self.createTask)

        self.inputPathParser = export.ExportVariableParser()
        self.outputPathParser = export.ExportVariableParser()

        currentFile = self.tab.filelist.getCurrentFile()
        self.inputPathParser.setup(currentFile, None)
        self.outputPathParser.setup(currentFile, None)

        self._build()
        self.reloadMacros()

    def _build(self):
        leftCol = QtWidgets.QVBoxLayout()
        leftCol.addWidget(self._buildCropSettings())
        leftCol.addWidget(self._buildBuckets())

        layout = QtWidgets.QGridLayout()
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setRowStretch(0, 0)
        layout.setRowStretch(1, 0)
        layout.setRowStretch(2, 0)
        layout.setRowStretch(3, 1)
        layout.setRowStretch(4, 0)
        layout.setColumnMinimumWidth(0, 250)

        layout.addLayout(leftCol, 0, 0, 4, 1)
        layout.addWidget(self._buildInputMask(), 0, 1)
        layout.addWidget(self._buildOutputMask(), 1, 1)
        layout.addWidget(self._buildOutputImage(), 2, 1)
        layout.addWidget(QtWidgets.QWidget(), 3, 1)

        layout.addWidget(self.taskHandler.btnStart, 4, 0, 1, 2)

        self.setLayout(layout)

    def _buildCropSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

        row = 0
        self.spinCropSize = QtWidgets.QDoubleSpinBox()
        self.spinCropSize.setRange(0.1, 100)
        self.spinCropSize.setSingleStep(0.1)
        self.spinCropSize.setValue(1.0)
        layout.addWidget(QtWidgets.QLabel("Crop Size Factor:"), row, 0)
        layout.addWidget(self.spinCropSize, row, 1)

        row += 1
        self.chkAllowUpscale = QtWidgets.QCheckBox("Allow Upscale")
        layout.addWidget(self.chkAllowUpscale, row, 0)

        row += 1
        self.chkMultipleOutputs = QtWidgets.QCheckBox("Multiple Regions → Multiple Files")
        #self.chkMultipleOutputs.setChecked(True)
        layout.addWidget(self.chkMultipleOutputs, row, 0, 1, 2)

        groupBox = QtWidgets.QGroupBox("Crop Settings")
        groupBox.setLayout(layout)
        return groupBox

    def _buildBuckets(self):
        layout = QtWidgets.QGridLayout()

        row = 0
        self.sizePresets = SizePresetWidget()
        layout.addWidget(self.sizePresets, row, 0, 1, 2)

        row += 1
        self.chkInverseBuckets = QtWidgets.QCheckBox("Include Swapped (Height x Width)")
        self.chkInverseBuckets.setChecked(True)
        layout.addWidget(self.chkInverseBuckets, row, 0, 1, 2)

        row += 1
        btnSaveBuckets = QtWidgets.QPushButton("Save to Config")
        btnSaveBuckets.clicked.connect(self.sizePresets.saveSizeBuckets)
        layout.addWidget(btnSaveBuckets, row, 0)

        btnLoadBuckets = QtWidgets.QPushButton("Load from Config")
        btnLoadBuckets.clicked.connect(lambda: self.sizePresets.reloadSizeBuckets())
        layout.addWidget(btnLoadBuckets, row, 1)

        groupBox = QtWidgets.QGroupBox("Target Size Buckets")
        groupBox.setLayout(layout)
        return groupBox

    def _buildInputMask(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnMinimumWidth(0, 90)
        layout.setColumnMinimumWidth(1, 150)
        layout.setColumnMinimumWidth(2, 20)

        row = 0
        self.cboInputMaskMode = QtWidgets.QComboBox()
        self.cboInputMaskMode.addItem("Macro", InputMaskType.Macro)
        self.cboInputMaskMode.addItem("Separate Image", InputMaskType.File)
        self.cboInputMaskMode.addItem("Alpha Channel", InputMaskType.Alpha)
        self.cboInputMaskMode.currentIndexChanged.connect(self._onInputMaskModeChanged)
        layout.addWidget(QtWidgets.QLabel("Mask Source:"), row, 0)
        layout.addWidget(self.cboInputMaskMode, row, 1)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY_INMASK, {})
        self.inputMaskPathSettings = export.PathSettings(self.inputPathParser, showInfo=False)
        self.inputMaskPathSettings.pathTemplate = config.get("path_template", "{{path}}-masklabel.png")
        self.inputMaskPathSettings.setAsInput()
        layout.addWidget(self.inputMaskPathSettings, row, 3, 3, 1)

        row += 1
        self.lblInputMacro = QtWidgets.QLabel("Macro:")
        layout.addWidget(self.lblInputMacro, row, 0)

        self.cboInputMacro = QtWidgets.QComboBox()
        layout.addWidget(self.cboInputMacro, row, 1)

        row += 1
        self.btnReloadMacros = QtWidgets.QPushButton("Reload Macros")
        self.btnReloadMacros.clicked.connect(self.reloadMacros)
        layout.addWidget(self.btnReloadMacros, row, 1)

        self._onInputMaskModeChanged(self.cboInputMaskMode.currentIndex())
        groupBox = QtWidgets.QGroupBox("Input Mask defines Crop Region(s)")
        groupBox.setLayout(layout)
        return groupBox

    def _buildOutputMask(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnMinimumWidth(0, 90)
        layout.setColumnMinimumWidth(1, 150)
        layout.setColumnMinimumWidth(2, 20)

        row = 0
        self.cboOutputMaskMode = QtWidgets.QComboBox()
        self.cboOutputMaskMode.addItem("Discard", OutputMaskType.Discard)
        self.cboOutputMaskMode.addItem("Separate Image", OutputMaskType.File)
        self.cboOutputMaskMode.addItem("Alpha Channel", OutputMaskType.Alpha)
        self.cboOutputMaskMode.currentIndexChanged.connect(self._onOutputMaskModeChanged)
        layout.addWidget(QtWidgets.QLabel("Destination:"), row, 0)
        layout.addWidget(self.cboOutputMaskMode, row, 1)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY_OUTMASK, {})
        self.outputMaskPathSettings = export.PathSettings(self.outputPathParser, showInfo=False)
        self.outputMaskPathSettings.pathTemplate   = config.get("path_template", "{{path}}_{{region}}_{{w}}x{{h}}-masklabel.png")
        self.outputMaskPathSettings.overwriteFiles = config.get("overwrite", False)
        layout.addWidget(self.outputMaskPathSettings, row, 3, 3, 1)

        row += 1
        layout.addWidget(QtWidgets.QWidget(), row, 0)

        self._onOutputMaskModeChanged(self.cboOutputMaskMode.currentIndex())
        groupBox = QtWidgets.QGroupBox("Save Cropped Mask")
        groupBox.setLayout(layout)
        return groupBox

    def _buildOutputImage(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 0)
        layout.setColumnMinimumWidth(0, 90)
        layout.setColumnMinimumWidth(1, 150)
        layout.setColumnMinimumWidth(2, 20)

        row = 0
        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(export.INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos
        layout.addWidget(QtWidgets.QLabel("Interp Up:"), row, 0)
        layout.addWidget(self.cboInterpUp, row, 1)

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY_IMG, {})
        self.outputImagePathSettings = export.PathSettings(self.outputPathParser, showInfo=False)
        self.outputImagePathSettings.pathTemplate   = config.get("path_template", "{{path}}_{{region}}_{{w}}x{{h}}.png")
        self.outputImagePathSettings.overwriteFiles = config.get("overwrite", False)
        layout.addWidget(self.outputImagePathSettings, row, 3, 4, 1)

        row += 1
        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(export.INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area
        layout.addWidget(QtWidgets.QLabel("Interp Down:"), row, 0)
        layout.addWidget(self.cboInterpDown, row, 1)

        row += 1
        layout.addWidget(QtWidgets.QWidget(), row, 0)

        groupBox = QtWidgets.QGroupBox("Save Cropped Image")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, file: str):
        self.outputPathParser.setup(file)
        self.inputPathParser.setup(file)
        self.inputPathParser.setImageDimension(self.tab.imgview.image.pixmap())

        self.inputMaskPathSettings.updatePreview()
        self.outputMaskPathSettings.updatePreview()
        self.outputImagePathSettings.updatePreview()


    @Slot()
    def _onInputMaskModeChanged(self, index: int):
        mode = self.cboInputMaskMode.itemData(index)
        self.inputMaskPathSettings.setEnabled(mode == InputMaskType.File)

        macroEnabled = (mode == InputMaskType.Macro)
        for widget in (self.lblInputMacro, self.cboInputMacro, self.btnReloadMacros):
            widget.setEnabled(macroEnabled)

    @Slot()
    def _onOutputMaskModeChanged(self, index: int):
        mode = self.cboOutputMaskMode.itemData(index)
        enabled = (mode == OutputMaskType.File)
        self.outputMaskPathSettings.setEnabled(enabled)


    @Slot()
    def reloadMacros(self):
        with QSignalBlocker(self.cboInputMacro):
            selectedText = self.cboInputMacro.currentText()
            self.cboInputMacro.clear()
            for name, path in MaskingMacro.loadMacros():
                self.cboInputMacro.addItem(name, path)

            index = max(0, self.cboInputMacro.findText(selectedText))
            self.cboInputMacro.setCurrentIndex(index)


    def _confirmStart(self) -> bool:
        ops = []

        match self.cboInputMaskMode.currentData():
            case InputMaskType.Macro:
                ops.append(f"Generate masks using the '{self.cboInputMacro.currentText()}' macro")
            case InputMaskType.File:
                ops.append(f"Load existing masks from a separate file")
            case InputMaskType.Alpha:
                ops.append(f"Load the image's alpha channel as the mask")

        ops.append("Crop the images according to the regions defined in the mask, and try to fit the region into the closest size bucket")
        if self.chkMultipleOutputs.isChecked():
            ops.append("Save each cropped region into a separate image")
        else:
            ops.append("Combine all cropped regions into one image")

        if self.outputImagePathSettings.overwriteFiles:
            ops.append( qtlib.htmlRed("Save the cropped images and overwrite existing images!") )
        elif self.outputImagePathSettings.skipExistingFiles:
            ops.append("Save the cropped images using new filenames")
        else:
            ops.append("Save the cropped images using new filenames with an increasing counter")

        match self.cboOutputMaskMode.currentData():
            case OutputMaskType.Discard:
                ops.append("Discard the mask")
            case OutputMaskType.File:
                if self.outputMaskPathSettings.overwriteFiles:
                    ops.append( qtlib.htmlRed("Save the cropped mask as a separate image and overwrite existing images!") )
                else:
                    ops.append("Save the cropped mask as a separate image, using new filenames with an increasing counter")
            case OutputMaskType.Alpha:
                ops.append("Save the cropped mask as the alpha channel in the cropped images")

        return BatchUtil.confirmStart("Crop", self.tab.filelist.getNumFiles(), ops, self)


    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY_INMASK] = {
            "path_template": self.inputMaskPathSettings.pathTemplate,
            "overwrite": self.inputMaskPathSettings.overwriteFiles
        }

        Config.exportPresets[self.EXPORT_PRESET_KEY_OUTMASK] = {
            "path_template": self.outputMaskPathSettings.pathTemplate,
            "overwrite": self.outputMaskPathSettings.overwriteFiles
        }

        Config.exportPresets[self.EXPORT_PRESET_KEY_IMG] = {
            "path_template": self.outputImagePathSettings.pathTemplate,
            "overwrite": self.outputImagePathSettings.overwriteFiles
        }


    def createTask(self) -> BatchTask | None:
        if not self._confirmStart():
            return None

        self.saveExportPreset()

        taskClass = BatchCropTask
        match self.cboInputMaskMode.currentData():
            case InputMaskType.Macro:
                macroPath = self.cboInputMacro.currentData()
                macro = MaskingMacro()
                macro.loadFrom(macroPath)
                if macro.needsInference():
                    taskClass = BatchInferenceCropTask
                    maskSrcFunc = macro
                else:
                    maskSrcFunc = createMacroMaskSource(macroPath)
            case InputMaskType.File:
                maskSrcFunc = createFileMaskSource(self.inputMaskPathSettings.pathTemplate)
            case InputMaskType.Alpha:
                maskSrcFunc = createAlphaMaskSource()
            case _:
                raise ValueError("Invalid input mask type")

        match self.cboOutputMaskMode.currentData():
            case OutputMaskType.Discard:
                maskDestFunc = createDiscardMaskDest()
            case OutputMaskType.File:
                maskDestFunc = createFileMaskDest(self.outputMaskPathSettings)
            case OutputMaskType.Alpha:
                maskDestFunc = createAlphaMaskDest()
            case _:
                raise ValueError("Invalid output mask type")

        log = self.logWidget.addEntry("Crop")
        task = taskClass(log, self.tab.filelist, maskSrcFunc, maskDestFunc, self.outputImagePathSettings)

        task.combined      = not self.chkMultipleOutputs.isChecked()
        task.allowUpscale  = self.chkAllowUpscale.isChecked()
        task.sizeFactor    = self.spinCropSize.value()
        task.sizeBuckets   = self.sizePresets.parseSizeBuckets(self.chkInverseBuckets.isChecked())
        task.interpUp      = export.INTERP_MODES[ self.cboInterpUp.currentText() ]
        task.interpDown    = export.INTERP_MODES[ self.cboInterpDown.currentText() ]
        return task



class CropRegion:
    '`x1` and `y1` are the last included pixel coordinates. Offset them by +1 when slicing.'

    def __init__(self, xMin: int, yMin: int, xMax: int, yMax: int):
        self.x0 = xMin
        self.y0 = yMin
        self.x1 = xMax
        self.y1 = yMax

    def width(self):
        return self.x1 - self.x0 + 1

    def height(self):
        return self.y1 - self.y0 + 1

    def size(self):
        return self.width(), self.height()

    def toTuple(self):
        return self.x0, self.y0, self.x1, self.y1

    def copy(self):
        return CropRegion(self.x0, self.y0, self.x1, self.y1)

    def slice2D(self) -> tuple[slice, slice]:
        return slice(self.y0, self.y1+1), slice(self.x0, self.x1+1)

    def slice3D(self, start3: int, stop3: int) -> tuple[slice, slice, slice]:
        return slice(self.y0, self.y1+1), slice(self.x0, self.x1+1), slice(start3, stop3)

    def __str__(self) -> str:
        return f"CropRegion[x:{self.x0} to {self.x1}, y:{self.y0} to {self.y1}, {self.width()}x{self.height()}]"



MaskSource = Callable[[str, np.ndarray, Callable], list[np.ndarray] | None]

def createMacroMaskSource(macroPath: str) -> MaskSource:
    macro = MaskingMacro()
    macro.loadFrom(macroPath)

    def mask(imgPath: str, imgMat: np.ndarray, log):
        h, w = imgMat.shape[:2]
        layers = [ np.zeros((h, w), dtype=np.uint8) ]
        layers, layerChanged = macro.run(imgPath, layers)
        return layers

    return mask

def createFileMaskSource(pathTemplate: str) -> MaskSource:
    parser = export.ExportVariableParser()

    def loadMask(path: str, imgW: int, imgH: int, log):
        maskMat = imagerw.loadMatBGR(path, rgb=True)
        maskH, maskW = maskMat.shape[:2]
        if maskW != imgW or maskH != imgH:
            log(f"Mask size ({maskW}x{maskH}) doesn't match image size ({imgW}x{imgH})")
            return None

        layers = list(cv.split(maskMat))
        return layers

    def mask(imgPath: str, imgMat: np.ndarray, log):
        parser.setup(imgPath)
        h, w = imgMat.shape[:2]
        parser.width  = w
        parser.height = h

        path = parser.parsePath(pathTemplate, True)
        if os.path.exists(path):
            return loadMask(path, w, h, log)
        return None

    return mask

def createAlphaMaskSource() -> MaskSource:
    def mask(imgPath: str, imgMat: np.ndarray, log):
        h, w = imgMat.shape[:2]
        channels = imgMat.shape[2] if len(imgMat.shape) > 2 else 1
        if channels < 4:
            return [ np.zeros((h, w), dtype=np.uint8) ]
        else:
            return [ np.ascontiguousarray(imgMat[..., 3].copy()) ]

    return mask



MaskDest = Callable[[str, np.ndarray, list[np.ndarray], CropRegion, int, SizeBucket, Callable], np.ndarray]

def createDiscardMaskDest() -> MaskDest:
    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, regionIndex: int, targetSize: SizeBucket, log):
        return imgCropped
    return writeMask

def createFileMaskDest(pathSettings: export.PathSettings) -> MaskDest:
    pathTemplate   = pathSettings.pathTemplate
    overwriteFiles = pathSettings.overwriteFiles
    parser = export.ExportVariableParser()

    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, regionIndex: int, targetSize: SizeBucket, log):
        masks = list()
        for mask in maskLayers[:4]:
            masks.append( mask[region.slice2D()] )

        if len(masks) == 2:
            masks.append( np.zeros_like(masks[0]) )

        masks[:3] = masks[2::-1] # RGB(A) -> BGR(A)
        combined = np.dstack(masks)

        h, w = combined.shape[:2]
        interp = cv.INTER_CUBIC if (targetSize.w>w or targetSize.h>h) else cv.INTER_AREA
        scaled = cv.resize(combined, (targetSize.w, targetSize.h), interpolation=interp)

        parser.setup(imgPath)
        parser.width  = targetSize.w
        parser.height = targetSize.h
        parser.region = regionIndex

        path = parser.parsePath(pathTemplate, overwriteFiles)
        export.saveImage(path, scaled, log)

        return imgCropped

    return writeMask

def createAlphaMaskDest() -> MaskDest:
    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, regionIndex: int, targetSize: SizeBucket, log):
        channels = imgCropped.shape[2] if len(imgCropped.shape) > 2 else 1
        if channels == 1:
            imgChannels = [imgCropped] * 3
        else:
            imgChannels = list(cv.split(imgCropped))[:3]

        croppedMask = maskLayers[0][region.slice2D()] # Use first mask layer for alpha channel
        imgChannels.append(croppedMask)
        return np.dstack(imgChannels)

    return writeMask



class BaseBatchCropTask:
    log = print  # For ignoring error. Child classes will set the 'self.log' attribute.

    def __init__(self, maskDestFunc: MaskDest, imgPathSettings: export.PathSettings):
        self.maskDestFunc = maskDestFunc

        self.outPathTemplate   = imgPathSettings.pathTemplate
        self.outOverwriteFiles = imgPathSettings.overwriteFiles

        self.combined       = True
        self.allowUpscale   = False
        self.sizeFactor     = 1.0
        self.sizeBuckets: list[SizeBucket] = None
        self.interpUp       = -1
        self.interpDown     = -1

    def runPrepare(self):
        self.outPathParser = export.ExportVariableParser()

    def runCleanup(self):
        import gc
        gc.collect()


    def doCrop(self, maskLayers: list[np.ndarray], imgFile: str, imgMat: np.ndarray) -> str | None:
        cropRegions = self.findCropRegions(maskLayers[-1]) # Last mask layer defines crop regions
        if not cropRegions:
            self.log("No regions")
            return None

        imgH, imgW = imgMat.shape[:2]
        self.adjustCropRegions(imgW, imgH, cropRegions)

        # Prepare before writing files in saveCroppedImage()
        self.outPathParser.setup(imgFile)
        savePath = None

        for i, region in enumerate(cropRegions):
            fitRegion, targetSize = self.getTargetSize(imgW, imgH, region)
            if fitRegion and targetSize:
                self.log(f"Saving region {fitRegion.width()}x{fitRegion.height()} as {targetSize.w}x{targetSize.h}")
                cropped = imgMat[fitRegion.slice3D(0,3)] # Remove alpha
                cropped = self.maskDestFunc(imgFile, cropped, maskLayers, fitRegion, i, targetSize, self.log)
                savePath = self.saveCroppedImage(i, cropped, targetSize)
            else:
                self.log(f"No suitable target size found for region {i} ({region.width()}x{region.height()})")

        return savePath


    def findCropRegions(self, mat: np.ndarray) -> list[CropRegion]:
        contours, hierarchy = cv.findContours(mat, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []

        regions: list[CropRegion] = list()
        for c in contours:
            x, y, w, h = cv.boundingRect(c)
            regions.append(CropRegion(x, y, x+w-1, y+h-1))

        if not self.combined:
            return regions

        h, w = mat.shape[:2]
        xMin, xMax = w-1, 0
        yMin, yMax = h-1, 0

        for reg in regions:
            xMin = min(xMin, reg.x0)
            xMax = max(xMax, reg.x1)
            yMin = min(yMin, reg.y0)
            yMax = max(yMax, reg.y1)

        return [CropRegion(xMin, yMin, xMax, yMax)]

    def adjustCropRegions(self, imgW: int, imgH: int, regions: list[CropRegion]):
        for reg in regions:
            centerX = (reg.x0 + reg.x1) // 2
            centerY = (reg.y0 + reg.y1) // 2
            reg.x0 = max(0,      round(centerX - (centerX-reg.x0)*self.sizeFactor))
            reg.x1 = min(imgW-1, round(centerX + (reg.x1-centerX)*self.sizeFactor))
            reg.y0 = max(0,      round(centerY - (centerY-reg.y0)*self.sizeFactor))
            reg.y1 = min(imgH-1, round(centerY + (reg.y1-centerY)*self.sizeFactor))


    def getTargetSize(self, imgW: int, imgH: int, reg: CropRegion) -> tuple[CropRegion, SizeBucket] | tuple[None, None]:
        w, h = reg.size()
        regionAspect = w/h
        regionArea   = w*h

        def score(bucket: SizeBucket) -> tuple[float, float]:
            #aspectRatio = max(regionAspect/bucket.aspect, bucket.aspect/regionAspect)
            aspectDiff = round(abs(regionAspect - bucket.aspect), 2)
            areaRatio = np.sqrt( max(regionArea/bucket.area, bucket.area/regionArea) )
            return (aspectDiff, areaRatio)

        buckets = sorted(self.sizeBuckets, key=score)
        # print(f"Target size candidates for region {reg.width()}x{reg.height()}:")
        # for b in buckets:
        #     print(f" - {b.w}x{b.h} score: {score(b)}")

        # Adjust region to aspect ratio of target bucket
        for bucket in buckets:
            #print(f"Trying to fit region {reg.width()}x{reg.height()} in bucket {bucket.w}x{bucket.h}")
            if fitRegion := self.tryFitRegion(imgW, imgH, bucket, reg):
                #print(f"  Fit region: {fitRegion.width()}x{fitRegion.height()}")
                if self.allowUpscale or (fitRegion.width() >= bucket.w and fitRegion.height() >= bucket.h):
                    #print(f"  Chosen: {bucket.w}x{bucket.h} score: {score(bucket)}")
                    return fitRegion, bucket
                # else:
                #     print(f"  Upscale not allowed, bucket too big: {bucket.w}x{bucket.h} score: {score(bucket)}")
                #     # TODO: If no bucket was found, also try adjusting region in the other direction?

        return None, None

    @staticmethod
    def tryFitRegion(imgW: int, imgH: int, bucket: SizeBucket, reg: CropRegion) -> CropRegion | None:
        reg  = reg.copy()
        w, h = reg.size()
        regionAspect = w/h

        bucketAspect = bucket.w / bucket.h
        if bucketAspect > regionAspect:
            # Grow region width
            w = round(h * bucketAspect)
            if w > imgW:
                return None

            growLeft  = (w-1) // 2
            growRight = (w-1) - growLeft
            centerX   = (reg.x0 + reg.x1) // 2
            reg.x0    = centerX - growLeft
            reg.x1    = centerX + growRight

            if reg.x0 < 0:
                reg.x1 += -reg.x0
                reg.x0 = 0
            if reg.x1 >= imgW:
                reg.x0 -= reg.x1-imgW+1
                reg.x1 = imgW-1

            assert(reg.x0 >= 0 and reg.x1 < imgW)

        else:
            # Grow region height
            h = round(w / bucketAspect)
            if h > imgH:
                return None

            growTop = (h-1) // 2
            growBtm = (h-1) - growTop
            centerY = (reg.y0 + reg.y1) // 2
            reg.y0  = centerY - growTop
            reg.y1  = centerY + growBtm

            if reg.y0 < 0:
                reg.y1 += -reg.y0
                reg.y0 = 0
            if reg.y1 >= imgH:
                reg.y0 -= reg.y1-imgH+1
                reg.y1 = imgH-1

            assert(reg.y0 >= 0 and reg.y1 < imgH)

        return reg


    def saveCroppedImage(self, index: int, cropped: np.ndarray, targetSize: SizeBucket) -> str:
        h, w = cropped.shape[:2]
        interp = self.interpUp if (targetSize.w>w or targetSize.h>h) else self.interpDown
        scaled = cv.resize(cropped, (targetSize.w, targetSize.h), interpolation=interp)
        del cropped

        self.outPathParser.width  = targetSize.w
        self.outPathParser.height = targetSize.h
        self.outPathParser.region = index

        path = self.outPathParser.parsePath(self.outPathTemplate, self.outOverwriteFiles)
        export.saveImage(path, scaled, self.log)
        return path



class BatchCropTask(BaseBatchCropTask, BatchTask):
    def __init__(self, log, filelist, maskSrcFunc: MaskSource, maskDestFunc: Callable, imgPathSettings: export.PathSettings):
        BaseBatchCropTask.__init__(self, maskDestFunc, imgPathSettings)
        BatchTask.__init__(self, "crop", log, filelist)
        self.maskSrcFunc  = maskSrcFunc

    def runProcessFile(self, imgFile: str) -> str | None:
        imgMat = imagerw.loadMatBGR(imgFile)

        maskLayers = self.maskSrcFunc(imgFile, imgMat, self.log)
        if not maskLayers:
            self.log(f"Failed to load mask")
            return None

        return self.doCrop(maskLayers, imgFile, imgMat)



class BatchInferenceCropTask(BaseBatchCropTask, BatchInferenceTask):
    def __init__(self, log, filelist, macro: MaskingMacro, maskDestFunc: Callable, imgPathSettings: export.PathSettings):
        BaseBatchCropTask.__init__(self, maskDestFunc, imgPathSettings)
        BatchInferenceTask.__init__(self, "crop", log, filelist)
        self.macro = macro

    def runPrepare(self, proc):
        super().runPrepare()


    def runCheckFile(self, imgFile: str, proc) -> Callable | InferenceChain | None:
        imgW, imgH = imagerw.readSize(imgFile)
        layers = [ np.zeros((imgH, imgW), dtype=np.uint8) ]
        macroRunner = ChainedMacroRunner(self.macro, "", layers)
        return macroRunner(imgFile, proc)


    def runProcessFile(self, imgFile: str, results: list) -> str | None:
        if not results:
            self.log(f"Failed to load mask")
            return None

        _, maskLayers, layerChanged = results[0]

        imgMat = imagerw.loadMatBGR(imgFile)
        return self.doCrop(maskLayers, imgFile, imgMat)
