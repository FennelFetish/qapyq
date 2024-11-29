from PySide6.QtCore import Slot, QSignalBlocker
from PySide6 import QtWidgets
import numpy as np
import ui.export_settings as export
from config import Config
from infer.model_settings import ModelSettingsWindow
from .mask import MaskTool, MaskItem
from . import mask_ops
import lib.mask_macro as macro


class MaskToolBar(QtWidgets.QToolBar):
    def __init__(self, maskTool):
        super().__init__("Mask")
        self.maskTool: MaskTool = maskTool
        self.ops: dict[str, mask_ops.MaskOperation] = {}
        self.selectedOp: mask_ops.MaskOperation = None

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildLayers())
        layout.addWidget(self._buildOps())
        layout.addWidget(self._buildHistory())
        layout.addWidget(self._buildMacro())

        self.exportWidget = export.ExportWidget("mask", maskTool.tab.filelist, showInterpolation=False)
        layout.addWidget(self.exportWidget)

        btnExport = QtWidgets.QPushButton("Export")
        btnExport.clicked.connect(self.maskTool.exportMask)
        layout.addWidget(btnExport)

        # TODO: Also load from image's alpha channel
        #       Only if file is PNG/WEBP
        # btnApplyAlpha = QtWidgets.QPushButton("Set as Alpha Channel")
        # btnApplyAlpha.clicked.connect(self.maskTool.applyAlpha)
        # layout.addWidget(btnApplyAlpha)
        
        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def _buildLayers(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        row = 0
        self.cboLayer = QtWidgets.QComboBox()
        self.cboLayer.setEditable(True)
        self.cboLayer.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.cboLayer.currentIndexChanged.connect(self.maskTool.setLayer)
        self.cboLayer.editTextChanged.connect(self.renameLayer)
        layout.addWidget(self.cboLayer, row, 0, 1, 2)

        row += 1
        self.btnAddLayer = QtWidgets.QPushButton("Add")
        self.btnAddLayer.clicked.connect(self.maskTool.addLayer)
        layout.addWidget(self.btnAddLayer, row, 0)

        self.btnDeleteLayer = QtWidgets.QPushButton("Delete")
        self.btnDeleteLayer.clicked.connect(self.maskTool.deleteCurrentLayer)
        layout.addWidget(self.btnDeleteLayer, row, 1)

        self.layerGroup = QtWidgets.QGroupBox("Layers")
        self.layerGroup.setLayout(layout)
        return self.layerGroup

    def _buildOps(self):
        shortcutLayout = QtWidgets.QHBoxLayout()
        shortcutLayout.setContentsMargins(0, 0, 0, 0)

        btnBrush = QtWidgets.QPushButton("B")
        btnBrush.clicked.connect(lambda: self.selectOp("brush"))
        shortcutLayout.addWidget(btnBrush)

        btnFill = QtWidgets.QPushButton("F")
        btnFill.clicked.connect(lambda: self.selectOp("fill"))
        shortcutLayout.addWidget(btnFill)

        btnClear = QtWidgets.QPushButton("C")
        btnClear.clicked.connect(lambda: self.selectOp("clear"))
        shortcutLayout.addWidget(btnClear)

        btnInvert = QtWidgets.QPushButton("I")
        btnInvert.clicked.connect(lambda: self.selectOp("invert"))
        shortcutLayout.addWidget(btnInvert)

        btnMorph = QtWidgets.QPushButton("M")
        btnMorph.clicked.connect(lambda: self.selectOp("morph"))
        shortcutLayout.addWidget(btnMorph)

        btnGauss = QtWidgets.QPushButton("G")
        btnGauss.clicked.connect(lambda: self.selectOp("blur_gauss"))
        shortcutLayout.addWidget(btnGauss)

        self.opLayout = QtWidgets.QVBoxLayout()
        self.opLayout.setContentsMargins(1, 1, 1, 1)
        self.opLayout.addLayout(shortcutLayout)

        self.cboOperation = QtWidgets.QComboBox()
        self.cboOperation.currentIndexChanged.connect(self.onOpChanged)
        self.opLayout.addWidget(self.cboOperation)
        self._reloadOps()
        ModelSettingsWindow(self).signals.presetListUpdated.connect(self._reloadOps)
        
        group = QtWidgets.QGroupBox("Operations")
        group.setLayout(self.opLayout)
        return group

    @Slot()
    def _reloadOps(self):
        for op in self.ops.values():
            op.deleteLater()

        # TODO: Keep existing ops and their current settings.
        self.ops = {
            "brush": mask_ops.DrawMaskOperation(self.maskTool),
            "brush_magic": mask_ops.MagicDrawMaskOperation(self.maskTool),
            "fill": mask_ops.FillMaskOperation(self.maskTool),
            "clear": mask_ops.ClearMaskOperation(self.maskTool),
            "invert": mask_ops.InvertMaskOperation(self.maskTool),
            "morph": mask_ops.MorphologyMaskOperation(self.maskTool),
            "blur_gauss": mask_ops.BlurMaskOperation(self.maskTool),
        }

        with QSignalBlocker(self.cboOperation):
            selectedKey = self.cboOperation.currentData()
            self.cboOperation.clear()

            self.cboOperation.addItem("Brush", "brush")
            #self.cboOperation.addItem("Magic Brush", "brush_magic") # Flood fill from cursor position, keep inside brush circle (or GrabCut init with mask)
            #self.cboOperation.addItem("Rectangle", "rect")
            self.cboOperation.addItem("Flood Fill", "fill")
            self.cboOperation.addItem("Clear", "clear")
            self.cboOperation.addItem("Invert", "invert")
            self.cboOperation.addItem("Morphology", "morph")
            #self.cboOperation.addItem("Linear Gradient", "gradient_linear")
            self.cboOperation.addItem("Gaussian Blur", "blur_gauss")
            
            for name, config in Config.inferMaskPresets.items():
                self._buildCustomOp(name, config)

            index = max(0, self.cboOperation.findData(selectedKey))
            self.cboOperation.setCurrentIndex(index)
            self.onOpChanged(index)
    
    def _buildCustomOp(self, name: str, config: dict):
        match config.get("backend"):
            case "yolo-detect":
                key = f"detect {name}"
                self.ops[key] = mask_ops.DetectMaskOperation(self.maskTool, config)
                self.cboOperation.addItem(f"Detect: {name}", key)
            case "bria-rmbg":
                key = f"segment {name}"
                self.ops[key] = mask_ops.SegmentMaskOperation(self.maskTool, config)
                self.cboOperation.addItem(f"Segment: {name}", key)

    def _buildHistory(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        self.listHistory = QtWidgets.QListWidget()
        self.listHistory.currentRowChanged.connect(lambda index: self.maskTool.maskItem.jumpHistory(index))
        layout.addWidget(self.listHistory, 0, 0, 1, 2)

        group = QtWidgets.QGroupBox("History")
        group.setLayout(layout)
        return group

    def _buildMacro(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        # Pause/Continue?
        # Stop macro on image change
        # Save when? When stopping? Or add save button?
        # Set macro name before saving? Use filename as name?

        # Load macros into list of operations?
        # Provide default macros in subfolder

        self.btnStartStopMacro = QtWidgets.QPushButton("Start Recording")
        self.btnStartStopMacro.clicked.connect(self.startStopMacro)
        layout.addWidget(self.btnStartStopMacro)

        group = QtWidgets.QGroupBox("Macro")
        group.setLayout(layout)
        return group


    def setLayers(self, layers: list[MaskItem], selectedIndex: int):
        with QSignalBlocker(self.cboLayer):
            self.cboLayer.clear()
            for mask in layers:
                self.cboLayer.addItem(mask.name, mask)
            self.cboLayer.setCurrentIndex(selectedIndex)
        
        numLayers = len(layers)
        self.btnAddLayer.setEnabled(numLayers < 4)
        self.layerGroup.setTitle(f"Layers ({numLayers})")

    @Slot()
    def renameLayer(self, name: str):
        index = self.cboLayer.currentIndex()
        self.cboLayer.setItemText(index, name)
        self.cboLayer.itemData(index).name = name


    def selectOp(self, key: str):
        if (index := self.cboOperation.findData(key)) >= 0:
            self.cboOperation.setCurrentIndex(index)

    @Slot()
    def onOpChanged(self, index: int):
        # Updating the mask model settings updates the ops and calls this function.
        # ImgView is not available when MaskTool is not active (or during initialization).
        imgview = self.maskTool._imgview

        if self.selectedOp:
            if imgview:
                self.selectedOp.onDisabled(imgview)
            self.opLayout.removeWidget(self.selectedOp)
            self.selectedOp.hide()
        
        if not (opKey := self.cboOperation.itemData(index)):
            return
        if not (op := self.ops.get(opKey)):
            return
        
        self.selectedOp = op
        self.opLayout.addWidget(self.selectedOp)
        self.selectedOp.show()

        if imgview:
            self.selectedOp.onEnabled(imgview)


    def addHistory(self, title: str, imgData: np.ndarray | None = None):
        self.maskTool.maskItem.addHistory(title, imgData)
        self.setHistory(self.maskTool.maskItem)

    def setHistory(self, maskItem: MaskItem):
        with QSignalBlocker(self.listHistory):
            self.listHistory.clear()
            for entry in maskItem.history:
                self.listHistory.addItem(entry.title)
            self.listHistory.setCurrentRow(maskItem.historyIndex)


    def updateExport(self):
        if maskItem := self.maskTool.maskItem:
            self.exportWidget.setExportSize(maskItem.mask.width(), maskItem.mask.height())
        else:
            self.exportWidget.setExportSize(0, 0)
        
        self.exportWidget.updateSample()


    @Slot()
    def startStopMacro(self):
        # Stop recording
        if self.maskTool.macro:
            self.btnStartStopMacro.setText("Start Recording")
            self.maskTool.macro = None
        
        # Start recording
        else:
            self.btnStartStopMacro.setText("Stop Recording")
            self.maskTool.macro = macro.MaskingMacro()
