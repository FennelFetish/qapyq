from PySide6.QtCore import Slot, QSignalBlocker, QTimer
from PySide6 import QtWidgets
import superqt
import numpy as np
import ui.export_settings as export
from config import Config
from infer.model_settings import ModelSettingsWindow
from .mask import MaskTool, MaskItem
from . import mask_ops
from lib.mask_macro import MaskingMacro, MacroOpItem
from lib.qtlib import MenuComboBox, SaveButton


class MaskToolBar(QtWidgets.QToolBar):
    def __init__(self, maskTool):
        super().__init__("Mask")
        self.maskTool: MaskTool = maskTool
        self.ops: dict[str, mask_ops.MaskOperation] = {}
        self.selectedOp: mask_ops.MaskOperation = None

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setRowStretch(2, 1)
        layout.addWidget(self._buildLayers())
        layout.addWidget(self._buildOps())
        layout.addWidget(self._buildHistory())
        layout.addWidget(self._buildMacro())

        self.exportWidget = export.ExportWidget("mask", maskTool.tab.filelist, showInterpolation=False, formats=["PNG","WEBP"])
        layout.addWidget(self.exportWidget)

        btnReload = SaveButton("Reload")
        btnReload.clicked.connect(self._reloadMask)
        layout.addWidget(btnReload)

        self.btnExport = SaveButton("Export")
        self.btnExport.clicked.connect(self.maskTool.exportMask)
        layout.addWidget(self.btnExport)

        self._recordBlinkTimer = QTimer()
        self._recordBlinkTimer.setInterval(500)
        self._recordBlinkTimer.timeout.connect(self._blinkRecordMacro)

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

        self.cboOperation = MenuComboBox("Operations")
        self.cboOperation.currentIndexChanged.connect(self.onOpChanged)
        self.opLayout.addWidget(self.cboOperation)
        self._reloadOps()
        ModelSettingsWindow.signals.presetListUpdated.connect(self._reloadOps)

        group = QtWidgets.QGroupBox("Operations")
        group.setLayout(self.opLayout)
        return group

    @Slot()
    def _reloadOps(self):
        opClasses = {
            "brush":        mask_ops.DrawMaskOperation,
            "brush_magic":  mask_ops.MagicDrawMaskOperation,
            "rect":         mask_ops.DrawRectangleMaskOperation,
            "fill":         mask_ops.FillMaskOperation,
            "clear":        mask_ops.ClearMaskOperation,
            "invert":       mask_ops.InvertMaskOperation,
            "threshold":    mask_ops.ThresholdMaskOperation,
            "normalize":    mask_ops.NormalizeMaskOperation,
            "morph":        mask_ops.MorphologyMaskOperation,
            "blur_gauss":   mask_ops.BlurMaskOperation,
            "blend_layers": mask_ops.BlendLayersMaskOperation,

            "cond_area":    mask_ops.AreaConditionMaskOperation,
            "cond_color":   mask_ops.ColorConditionMaskOperation,
            "cond_regions": mask_ops.RegionConditionMaskOperation
        }

        # Try to keep existing ops and their current settings.
        newOps = dict()
        for key, cls in opClasses.items():
            newOps[key] = self.ops.pop(key, None) or cls(self.maskTool)

        for op in self.ops.values():
            op.deleteLater()
        self.ops = newOps

        with QSignalBlocker(self.cboOperation):
            selectedKey = self.cboOperation.currentData()
            self.cboOperation.clear()

            # Add basic operations
            self.cboOperation.addItem("Brush", "brush")
            #self.cboOperation.addItem("Magic Brush", "brush_magic") # Flood fill from cursor position, keep inside brush circle (or GrabCut init with mask)
            self.cboOperation.addItem("Rectangle", "rect")
            self.cboOperation.addItem("Flood Fill", "fill")
            self.cboOperation.addItem("Clear", "clear")
            self.cboOperation.addItem("Invert", "invert")
            self.cboOperation.addItem("Threshold", "threshold")
            self.cboOperation.addItem("Normalize", "normalize")
            self.cboOperation.addItem("Morphology", "morph")
            #self.cboOperation.addItem("Linear Gradient", "gradient_linear")
            self.cboOperation.addItem("Gaussian Blur", "blur_gauss")
            self.cboOperation.addItem("Blend Layers", "blend_layers")

            # Add detect / segment operations
            self.cboOperation.addSeparator()
            detectMenu = self.cboOperation.addSubmenu("Detect")
            segmentMenu = self.cboOperation.addSubmenu("Segment")
            for preset in sorted(Config.inferMaskPresets.keys(), key=self._customOpSortKey):
                self._buildCustomOp(preset, detectMenu, segmentMenu)

            detectMenu.addSeparator()
            detectMenu.addAction("Model Settings...").triggered.connect(self._openModelSettings)

            segmentMenu.addSeparator()
            segmentMenu.addAction("Model Settings...").triggered.connect(self._openModelSettings)

            self.cboOperation.addSeparator()

            # Add conditions
            condMenu = self.cboOperation.addSubmenu("Conditions")
            self.cboOperation.addSubmenuItem(condMenu, "Color Range", "Condition: ", "cond_color")
            self.cboOperation.addSubmenuItem(condMenu, "Filled Area", "Condition: ", "cond_area")
            self.cboOperation.addSubmenuItem(condMenu, "Region Count", "Condition: ", "cond_regions")

            # Add macro operations
            macroMenu = self.cboOperation.addSubmenu("Macros")
            for name, path in MaskingMacro.loadMacros():
                self._buildMacroOp(macroMenu, name, path)

            macroMenu.addSeparator()
            actReloadMacros = macroMenu.addAction("Reload Macros")
            actReloadMacros.triggered.connect(self._reloadOps)

            # Restore selection
            index = max(0, self.cboOperation.findData(selectedKey))
            self.cboOperation.setCurrentIndex(index)
            self.onOpChanged(index)

    @staticmethod
    def _isDetectionPreset(preset: str) -> bool:
        return "-detect" in Config.inferMaskPresets[preset]["backend"]

    @classmethod
    def _customOpSortKey(cls, preset: str):
        segment = 0 if cls._isDetectionPreset(preset) else 1
        return (segment, preset.lower())

    def _buildCustomOp(self, preset: str, detectMenu, segmentMenu):
        if self._isDetectionPreset(preset):
            key = f"detect {preset}"
            self.ops[key] = mask_ops.DetectMaskOperation(self.maskTool, preset)
            self.cboOperation.addSubmenuItem(detectMenu, preset, "Detect: ", key)
        else:
            key = f"segment {preset}"
            self.ops[key] = mask_ops.SegmentMaskOperation(self.maskTool, preset)
            self.cboOperation.addSubmenuItem(segmentMenu, preset, "Segment: ", key)

    def _buildMacroOp(self, macroMenu, name, path):
        key = f"macro {name}"
        self.ops[key] = mask_ops.MacroMaskOperation(self.maskTool, name, path)
        self.cboOperation.addSubmenuItem(macroMenu, name, "Macro: ", key)

    @Slot()
    def _openModelSettings(self):
        ModelSettingsWindow.openInstance(self, "inferMaskPresets")


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
        collapsible = superqt.QCollapsible("Macro")
        collapsible.layout().setContentsMargins(2, 2, 2, 0)
        collapsible.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        collapsible.setLineWidth(0)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        self.btnStartStopMacro = QtWidgets.QPushButton("⚫ Start Recording")
        self.btnStartStopMacro.clicked.connect(self.startStopRecordMacro)
        layout.addWidget(self.btnStartStopMacro)

        btnClearMacro = QtWidgets.QPushButton("Stop && Clear")
        btnClearMacro.clicked.connect(self.clearMacro)
        layout.addWidget(btnClearMacro)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        collapsible.addWidget(widget)
        return collapsible


    def setLayers(self, layers: list[MaskItem], selectedIndex: int):
        with QSignalBlocker(self.cboLayer):
            self.cboLayer.clear()
            for mask in layers:
                self.cboLayer.addItem(mask.name, mask)
            self.cboLayer.setCurrentIndex(selectedIndex)

        numLayers = len(layers)
        self.btnAddLayer.setEnabled(numLayers < 4)
        self.layerGroup.setTitle(f"Layers ({numLayers})")

        self.ops["blend_layers"].setLayers(layers)

    @Slot()
    def renameLayer(self, name: str):
        index = self.cboLayer.currentIndex()
        self.cboLayer.setItemText(index, name)
        self.cboLayer.itemData(index).name = name

        self.ops["blend_layers"].setLayers(self.maskTool.layers)


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


    def addHistory(self, title: str, imgData: np.ndarray | None = None, macroItem: MacroOpItem | None = None):
        self.maskTool.maskItem.addHistory(title, imgData, macroItem)
        self.setHistory(self.maskTool.maskItem)

    def setHistory(self, maskItem: MaskItem):
        with QSignalBlocker(self.listHistory):
            self.listHistory.clear()
            for entry in maskItem.history:
                self.listHistory.addItem(entry.title)
            self.listHistory.setCurrentRow(maskItem.historyIndex)

    def setEdited(self, changed: bool):
        self.btnExport.setChanged(changed)


    def updateExport(self):
        if maskItem := self.maskTool.maskItem:
            self.exportWidget.setExportSize(maskItem.mask.width(), maskItem.mask.height())
        else:
            self.exportWidget.setExportSize(0, 0)

        self.exportWidget.updateSample()


    @Slot()
    def startStopRecordMacro(self):
        # TODO: Maybe don't allow pausing macro recording.
        #       Can weird things happen when layers are added/deleted/changed during pause?

        if self.maskTool.macro.recording:
            self.stopRecordMacro()
        else:
            self.startRecordMacro()

    def startRecordMacro(self):
        macro = self.maskTool.macro
        if not macro.recording:
            macro.recording = True
            self.btnStartStopMacro.setText("🔴 Stop && Save")
            self._recordBlinkTimer.start()

    def stopRecordMacro(self):
        macro = self.maskTool.macro
        if not macro.recording:
            return
        macro.recording = False
        self._recordBlinkTimer.stop()

        if self.saveMacro():
            self.clearMacro()
        else:
            self.btnStartStopMacro.setText("⚫ Continue Recording")

    def saveMacro(self) -> bool:
        path = Config.pathMaskMacros + "/macro.json"
        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save Macro", path, fileFilter)
        if path:
            self.maskTool.macro.saveTo(path)
            return True
        return False

    @Slot()
    def clearMacro(self):
        macro = self.maskTool.macro
        macro.recording = False
        self._recordBlinkTimer.stop()
        macro.clear()

        for maskItem in self.maskTool.layers:
            maskItem.clearHistoryMacroItems()

        self.btnStartStopMacro.setText("⚫ Start Recording")
        self._reloadOps()

    @Slot()
    def _blinkRecordMacro(self, disable=False):
        text = self.btnStartStopMacro.text()
        if disable or text[0] == "🔴":
            text = "⚫" + text[1:]
        else:
            text = "🔴" + text[1:]
        self.btnStartStopMacro.setText(text)


    @Slot()
    def _reloadMask(self):
        confirmText = f"Reloading the mask will discard all unsaved changes on all layers and clear the history for this file.\n\nDo you really want to reload the mask?"
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm reloading mask")
        dialog.setText(confirmText)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.maskTool.resetLayers()
