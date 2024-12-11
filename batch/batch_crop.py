import os, re
from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import cv2 as cv
import numpy as np
from config import Config
from lib import qtlib
from lib.mask_macro import MaskingMacro
from infer import Inference
from .batch_task import BatchTask
import ui.export_settings as export


# TODO: Filter regions (only biggest, minimum size, etc...)

# TODO: When writing multiple regions into multiple files, when Size Factor is large, the regions may overlap.
#       Should this be handled when writing output mask is enabled? Remove other regions from mask?

# TODO: Florence detection/segmentation?


class SizeBucket:
    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.area = w*h
        self.aspect = w/h


class BatchCrop(QtWidgets.QWidget):
    EXPORT_PRESET_KEY = "batch-crop"
    BUCKET_SPLIT = re.compile(r'[ ,x]')

    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.parser = export.ExportVariableParser()
        self.parser.setup(self.tab.filelist.getCurrentFile(), None)

        self._task = None
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

        self.btnStart = QtWidgets.QPushButton("Start Batch Crop")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 4, 0, 1, 2)

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
        layout.addWidget(QtWidgets.QLabel("Width x Height, one per line:"), row, 0, 1, 2)

        row += 1
        self.txtBuckets = QtWidgets.QPlainTextEdit()
        self.loadSizeBuckets()
        layout.addWidget(self.txtBuckets, row, 0, 1, 2)

        row += 1
        self.chkInverseBuckets = QtWidgets.QCheckBox("Include Swapped (Height x Width)")
        self.chkInverseBuckets.setChecked(True)
        layout.addWidget(self.chkInverseBuckets, row, 0, 1, 2)

        row += 1
        btnSaveBuckets = QtWidgets.QPushButton("Save to Config")
        btnSaveBuckets.clicked.connect(self.saveSizeBuckets)
        layout.addWidget(btnSaveBuckets, row, 0)

        btnLoadBuckets = QtWidgets.QPushButton("Load from Config")
        btnLoadBuckets.clicked.connect(self.loadSizeBuckets)
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
        self.cboInputMaskMode.addItem("Macro", "macro")
        self.cboInputMaskMode.addItem("Separate Image", "file")
        self.cboInputMaskMode.addItem("Alpha Channel", "alpha")
        self.cboInputMaskMode.currentIndexChanged.connect(self._onInputMaskModeChanged)
        layout.addWidget(QtWidgets.QLabel("Mask Source:"), row, 0)
        layout.addWidget(self.cboInputMaskMode, row, 1)

        config = Config.exportPresets.get("batch-mask", {})
        self.inputMaskPathSettings = export.PathSettings(self.parser, showInfo=False)
        self.inputMaskPathSettings.pathTemplate   = config.get("path_template", "{{path}}-masklabel")
        self.inputMaskPathSettings.overwriteFiles = True # Set to true to suppress adding counter
        self.inputMaskPathSettings.chkOverwrite.hide()
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
        self.cboOutputMaskMode.addItem("Discard", "discard")
        self.cboOutputMaskMode.addItem("Separate Image", "file")
        self.cboOutputMaskMode.addItem("Alpha Channel", "alpha")
        self.cboOutputMaskMode.currentIndexChanged.connect(self._onOutputMaskModeChanged)
        layout.addWidget(QtWidgets.QLabel("Destination:"), row, 0)
        layout.addWidget(self.cboOutputMaskMode, row, 1)

        config = Config.exportPresets.get("batch-mask", {})
        self.outputMaskPathSettings = export.PathSettings(self.parser, showInfo=False)
        self.outputMaskPathSettings.pathTemplate   = config.get("path_template", "{{path}}-masklabel")
        self.outputMaskPathSettings.overwriteFiles = config.get("overwrite", True)
        layout.addWidget(self.outputMaskPathSettings, row, 3, 3, 1)

        row += 1
        self.lblOutputMaskFormat = QtWidgets.QLabel("Format:")
        layout.addWidget(self.lblOutputMaskFormat, row, 0)

        self.cboOutputMaskFormat = QtWidgets.QComboBox()
        self.cboOutputMaskFormat.addItems(("PNG", "WEBP"))
        self.cboOutputMaskFormat.currentTextChanged.connect(self._onOutputMaskExtensionChanged)
        self._onOutputMaskExtensionChanged(self.cboOutputMaskFormat.currentText())
        layout.addWidget(self.cboOutputMaskFormat, row, 1)

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

        config = Config.exportPresets.get(self.EXPORT_PRESET_KEY, {})
        self.outputImagePathSettings = export.PathSettings(self.parser, showInfo=False)
        self.outputImagePathSettings.pathTemplate   = config.get("path_template", "{{path}}_{{w}}x{{h}}")
        self.outputImagePathSettings.overwriteFiles = config.get("overwrite", False)
        layout.addWidget(self.outputImagePathSettings, row, 3, 4, 1)

        row += 1
        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(export.INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area
        layout.addWidget(QtWidgets.QLabel("Interp Down:"), row, 0)
        layout.addWidget(self.cboInterpDown, row, 1)

        row += 1
        self.cboOutputImageFormat = QtWidgets.QComboBox()
        self.cboOutputImageFormat.addItems(export.FORMATS.keys())
        self.cboOutputImageFormat.currentTextChanged.connect(self._onOutputImageExtensionChanged)
        self._onOutputImageExtensionChanged(self.cboOutputImageFormat.currentText())
        layout.addWidget(QtWidgets.QLabel("Format:"), row, 0)
        layout.addWidget(self.cboOutputImageFormat, row, 1)

        row += 1
        layout.addWidget(QtWidgets.QWidget(), row, 0)

        groupBox = QtWidgets.QGroupBox("Save Cropped Image")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, file: str):
        self.parser.setup(file)
        self.inputMaskPathSettings.updatePreview()
        self.outputMaskPathSettings.updatePreview()
        self.outputImagePathSettings.updatePreview()


    @Slot()
    def _onInputMaskModeChanged(self, index: int):
        mode = self.cboInputMaskMode.itemData(index)
        self.inputMaskPathSettings.setEnabled(mode == "file")

        macroEnabled = (mode == "macro")
        for widget in (self.lblInputMacro, self.cboInputMacro, self.btnReloadMacros):
            widget.setEnabled(macroEnabled)

    @Slot()
    def _onOutputMaskModeChanged(self, index: int):
        mode = self.cboOutputMaskMode.itemData(index)
        enabled = (mode == "file")
        for widget in (self.lblOutputMaskFormat, self.cboOutputMaskFormat, self.outputMaskPathSettings):
            widget.setEnabled(enabled)

    @Slot()
    def _onOutputMaskExtensionChanged(self, ext: str):
        self.outputMaskPathSettings.extension = ext
        self.outputMaskPathSettings.updatePreview()

    @Slot()
    def _onOutputImageExtensionChanged(self, ext: str):
        self.outputImagePathSettings.extension = ext
        self.outputImagePathSettings.updatePreview()

    @Slot()
    def reloadMacros(self):
        with QSignalBlocker(self.cboInputMacro):
            selectedText = self.cboInputMacro.currentText()
            self.cboInputMacro.clear()
            for name, path in MaskingMacro.loadMacros():
                self.cboInputMacro.addItem(name, path)

            index = max(0, self.cboInputMacro.findText(selectedText))
            self.cboInputMacro.setCurrentIndex(index)


    def parseSizeBuckets(self, includeSwapped: bool) -> list[SizeBucket]:
        lines = self.txtBuckets.toPlainText().splitlines()
        buckets = []
        for line in lines:
            elements = self.BUCKET_SPLIT.split(line)
            if len(elements) != 2:
                continue

            try:
                w = int(elements[0].strip())
                h = int(elements[1].strip())
                buckets.append(SizeBucket(w, h))

                if includeSwapped and w != h:
                    buckets.append(SizeBucket(h, w))
            except ValueError:
                print(f"Invalid bucket size: {line}")

        return buckets

    @Slot()
    def loadSizeBuckets(self):
        text = "\n".join(Config.cropSizePresets)
        self.txtBuckets.setPlainText(text)
    
    @Slot()
    def saveSizeBuckets(self):
        buckets = []
        for bucket in self.parseSizeBuckets(False):
            buckets.append(f"{bucket.w}x{bucket.h}")
        Config.cropSizePresets = buckets


    def saveExportPreset(self):
        Config.exportPresets[self.EXPORT_PRESET_KEY] = {
            "path_template": self.outputImagePathSettings.pathTemplate,
            "overwrite": self.outputImagePathSettings.overwriteFiles
        }

    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
            return

        self.saveExportPreset()
        self.btnStart.setText("Abort")

        match self.cboInputMaskMode.currentData():
            case "macro":
                macroPath = self.cboInputMacro.currentData()
                maskSrcFunc = createMacroMaskSource(macroPath)
            case "file":
                maskSrcFunc = createFileMaskSource(self.inputMaskPathSettings.pathTemplate)
            case "alpha":
                maskSrcFunc = createAlphaMaskSource()
        
        match self.cboOutputMaskMode.currentData():
            case "discard":
                maskDestFunc = createDiscardMaskDest()
            case "file":
                maskDestFunc = createFileMaskDest(self.outputMaskPathSettings, self.log)
            case "alpha":
                maskDestFunc = createAlphaMaskDest()

        self._task = BatchCropTask(self.log, self.tab.filelist, maskSrcFunc, maskDestFunc, self.outputImagePathSettings)
        self._task.combined      = not self.chkMultipleOutputs.isChecked()
        self._task.allowUpscale  = self.chkAllowUpscale.isChecked()
        self._task.sizeFactor    = self.spinCropSize.value()
        self._task.sizeBuckets   = self.parseSizeBuckets(self.chkInverseBuckets.isChecked())
        self._task.interpUp      = export.INTERP_MODES[ self.cboInterpUp.currentText() ]
        self._task.interpDown    = export.INTERP_MODES[ self.cboInterpDown.currentText() ]

        self._task.signals.progress.connect(self.onProgress)
        self._task.signals.progressMessage.connect(self.onProgressMessage)
        self._task.signals.done.connect(self.onFinished)
        self._task.signals.fail.connect(self.onFail)
        Inference().queueTask(self._task)

    @Slot()
    def onFinished(self, numFiles):
        self.statusBar.showColoredMessage(f"Processed {numFiles} files", True, 0)
        self.taskDone()

    @Slot()
    def onFail(self, reason):
        self.statusBar.showColoredMessage(reason, False, 0)
        self.taskDone()

    @Slot()
    def onProgress(self, numDone, numTotal, imgFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if imgFile:
            self.statusBar.showMessage("Wrote " + imgFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Crop")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



def createMacroMaskSource(macroPath: str) -> Callable[[str, np.ndarray], list[np.ndarray]]:
    macro = MaskingMacro()
    macro.loadFrom(macroPath)

    def mask(imgPath: str, imgMat: np.ndarray):
        h, w = imgMat.shape[:2]
        layers = [ np.zeros((h, w), dtype=np.uint8) ]
        layers, layerChanged = macro.run(imgPath, layers)
        return layers

    return mask

def createFileMaskSource(pathTemplate: str):
    extensions = ["png", "webp", "jpg", "jpeg"]
    parser = export.ExportVariableParser()

    def loadMask(path: str):
        maskMat = cv.imread(path, cv.IMREAD_UNCHANGED)
        layers = list(cv.split(maskMat))
        layers[:3] = layers[2::-1] # Convert BGR(A) -> RGB(A)
        return layers

    def mask(imgPath: str, imgMat: np.ndarray):
        parser.setup(imgPath)
        h, w = imgMat.shape[:2]
        parser.width  = w
        parser.height = h

        pathNoExt = parser.parsePath(pathTemplate, "", False)
        for path in (f"{pathNoExt}{ext}" for ext in extensions):
            if os.path.exists(path):
                return loadMask(path)
        return None

    return mask

def createAlphaMaskSource():
    def mask(imgPath: str, imgMat: np.ndarray):
        h, w = imgMat.shape[:2]
        channels = imgMat.shape[2] if len(imgMat.shape) > 2 else 1
        if channels < 4:
            return [ np.zeros((h, w), dtype=np.uint8) ]
        else:
            return [ np.ascontiguousarray(imgMat[..., 3].copy()) ]

    return mask



def createDiscardMaskDest():
    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, targetSize: SizeBucket):
        return imgCropped
    return writeMask

def createFileMaskDest(pathSettings: export.PathSettings, log):
    pathTemplate   = pathSettings.pathTemplate
    extension      = pathSettings.extension
    overwriteFiles = pathSettings.overwriteFiles
    parser = export.ExportVariableParser()

    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, targetSize: SizeBucket):
        masks = list()
        for mask in maskLayers[:4]:
            masks.append( mask[region.y0 : region.y1+1, region.x0 : region.x1+1] )

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

        path = parser.parsePath(pathTemplate, extension, overwriteFiles)
        export.saveImage(path, scaled, log)

        return imgCropped

    return writeMask

def createAlphaMaskDest():
    def writeMask(imgPath: str, imgCropped: np.ndarray, maskLayers: list[np.ndarray], region: CropRegion, targetSize: SizeBucket):
        channels = imgCropped.shape[2] if len(imgCropped.shape) > 2 else 1
        if channels == 1:
            imgChannels = [imgCropped] * 3
        else:
            imgChannels = list(cv.split(imgCropped))[:3]

        croppedMask = maskLayers[0][region.y0 : region.y1+1, region.x0 : region.x1+1] # Use first mask layer for alpha channel
        imgChannels.append(croppedMask)
        return np.dstack(imgChannels)

    return writeMask



class CropRegion:
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


class BatchCropTask(BatchTask):
    def __init__(self, log, filelist, maskSrcFunc, maskDestFunc, imgPathSettings: export.PathSettings):
        super().__init__("crop", log, filelist)
        self.maskSrcFunc  = maskSrcFunc
        self.maskDestFunc = maskDestFunc

        self.outPathTemplate   = imgPathSettings.pathTemplate
        self.outExtension      = imgPathSettings.extension
        self.outOverwriteFiles = imgPathSettings.overwriteFiles

        self.combined       = True
        self.allowUpscale   = False
        self.sizeFactor     = 1.0
        self.sizeBuckets: list[SizeBucket] = None
        self.interpUp       = -1
        self.interpDown     = -1

    def runPrepare(self):
        self.outPathParser = export.ExportVariableParser()

    def runProcessFile(self, imgFile: str) -> str | None:
        imgMat = cv.imread(imgFile, cv.IMREAD_UNCHANGED)
        imgH, imgW = imgMat.shape[:2]

        maskLayers = self.maskSrcFunc(imgFile, imgMat)
        if not maskLayers:
            self.log(f"Failed to load mask")
            return None

        cropRegions = self.findCropRegions(maskLayers[-1]) # Last layer defines crop regions
        if not cropRegions:
            self.log("No regions")
            return None
        self.adjustCropRegions(imgW, imgH, cropRegions)

        # Prepare before writing files in saveCroppedImage()
        self.outPathParser.setup(imgFile)
        savePath = None

        for i, region in enumerate(cropRegions):
            region, targetSize = self.getTargetSize(imgW, imgH, region)
            if region and targetSize:
                # Do Cropping
                cropped = imgMat[region.y0 : region.y1+1, region.x0 : region.x1+1, :3] # Remove alpha
                cropped = self.maskDestFunc(imgFile, cropped, maskLayers, region, targetSize)
                savePath = self.saveCroppedImage(i, cropped, targetSize)

        if not savePath:
            self.log("No suitable target size found for region")
        return savePath


    def findCropRegions(self, mat: np.ndarray) -> list[CropRegion]:
        contours, hierarchy = cv.findContours(mat, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []

        regions: list[CropRegion] = list()
        for c in contours:
            x, y, w, h = cv.boundingRect(c)
            regions.append(CropRegion(x, y, x+w, y+h))

        if not self.combined:
            return regions

        h, w = mat.shape[:2]
        xMin, xMax = w, 0
        yMin, yMax = h, 0

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

        path = self.outPathParser.parsePath(self.outPathTemplate, self.outExtension, self.outOverwriteFiles)
        export.saveImage(path, scaled, self.log)
        return path