import os.path
from typing import Mapping
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject, QSignalBlocker
from config import Config
from lib import qtlib

from .embedding import embedding_common as embed
from .backend_config import (
    BackendDef, BackendTypes, BackendPathModes,
    BackendsCaption, BackendsTag, BackendsLLM, BackendsMask, BackendsUpscale, BackendsEmbedding
)


class ModelSettingsSignals(QObject):
    presetListUpdated = Signal(str)


class ModelSettingsWindow(QtWidgets.QMainWindow):
    _instance = None
    signals = ModelSettingsSignals()

    def __new__(cls, *args, **kwargs):
        if not isinstance(cls._instance, cls):
            cls._instance = super(ModelSettingsWindow, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, parent):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        super().__init__(parent)
        self.setWindowTitle(f"Model Settings - {Config.windowTitle}")
        self.resize(800, self.height())

        self.captionSettings = CaptionModelSettings("inferCaptionPresets", BackendsCaption)
        self.tagSettings     = TagModelSettings("inferTagPresets", BackendsTag)
        self.llmSettings     = LLMModelSettings("inferLLMPresets", BackendsLLM)
        self.scaleSettings   = ScaleModelSettings("inferScalePresets", BackendsUpscale)
        self.maskSettings    = MaskModelSettings("inferMaskPresets", BackendsMask)
        self.embedSettings   = EmbeddingModelSettings("inferEmbeddingPresets", BackendsEmbedding)

        self.tabWidget = QtWidgets.QTabWidget()
        self.tabWidget.addTab(self.captionSettings, "Caption")
        self.tabWidget.addTab(self.tagSettings, "Tags")
        self.tabWidget.addTab(self.llmSettings, "LLM")
        self.tabWidget.addTab(self.scaleSettings, "Scale")
        self.tabWidget.addTab(self.maskSettings, "Mask")
        self.tabWidget.addTab(self.embedSettings, "Embedding")
        self.setCentralWidget(self.tabWidget)

    def closeEvent(self, event):
        super().closeEvent(event)
        ModelSettingsWindow._instance = None

    @classmethod
    def openInstance(cls, parent, configAttr=None, presetName=None):
        justOpened = (cls._instance is None)

        win = ModelSettingsWindow(parent)
        win.show()
        win.activateWindow()

        if not justOpened:
            return

        match configAttr:
            case "inferCaptionPresets":     index, widget = 0, win.captionSettings
            case "inferTagPresets":         index, widget = 1, win.tagSettings
            case "inferLLMPresets":         index, widget = 2, win.llmSettings
            case "inferScalePresets":       index, widget = 3, win.scaleSettings
            case "inferMaskPresets":        index, widget = 4, win.maskSettings
            case "inferEmbeddingPresets":   index, widget = 5, win.embedSettings
            case _: return

        win.tabWidget.setCurrentIndex(index)
        widget.reloadPresetList(presetName)

    @classmethod
    def closeInstance(cls):
        if isinstance(cls._instance, cls):
            cls._instance.close()



class BaseSettingsWidget(QtWidgets.QWidget):
    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__()
        self.configAttr = configAttr
        self.backends = backends

        self._build()


    def _build(self) -> None:
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, 120)
        layout.setColumnMinimumWidth(2, 20)
        layout.setColumnMinimumWidth(3, 100)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0) # Spacing
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)
        layout.setColumnStretch(5, 0)
        layout.setColumnStretch(6, 0)

        row = 0
        self.cboPreset = QtWidgets.QComboBox()
        self.cboPreset.setEditable(True)
        self.cboPreset.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.cboPreset.editTextChanged.connect(self._onPresetNameEdited)
        self.cboPreset.currentIndexChanged.connect(self.loadPreset)
        layout.addWidget(QtWidgets.QLabel("Preset Name:"), row, 0)
        layout.addWidget(self.cboPreset, row, 1, 1, 4)

        self.btnSave = QtWidgets.QPushButton("Create")
        self.btnSave.setEnabled(False)
        #self.btnSave.setFixedWidth(100)
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 5, Qt.AlignmentFlag.AlignRight)

        self.btnDelete = QtWidgets.QPushButton("Delete")
        self.btnDelete.setEnabled(False)
        self.btnDelete.clicked.connect(self.deletePreset)
        layout.addWidget(self.btnDelete, row, 6)

        row += 1
        layout.setRowMinimumHeight(row, 16)

        row += 1
        self.cboBackend= QtWidgets.QComboBox()
        for name, backend in self.backends.items():
            self.cboBackend.addItem(f"{name} ({backend.type.value})", userData=backend)
        self.cboBackend.currentIndexChanged.connect(self._onBackendChanged)
        layout.addWidget(QtWidgets.QLabel("Backend:"), row, 0)
        layout.addWidget(self.cboBackend, row, 1, 1, 5)

        row = self._buildBase(layout, row+1)
        self.build(layout, row+1)
        self.setLayout(layout)

        self.fromDict({})
        self.reloadPresetList()
        self._onBackendChanged(self.cboBackend.currentIndex())

    def _buildBase(self, layout: QtWidgets.QGridLayout, row: int) -> int:
        self.lblPath = QtWidgets.QLabel("Model Path:")
        layout.addWidget(self.lblPath, row, 0)

        self.txtPath = QtWidgets.QLineEdit()
        layout.addWidget(self.txtPath, row, 1, 1, 5)

        btnChooseModel = QtWidgets.QPushButton("Choose...")
        btnChooseModel.clicked.connect(lambda: self._choosePath(self.txtPath))
        layout.addWidget(btnChooseModel, row, 6)
        return row

    def build(self, layout: QtWidgets.QGridLayout, row: int) -> None:
        raise NotImplementedError()


    @property
    def backend(self) -> str:
        return self.cboBackend.currentData().name

    @property
    def backendType(self) -> str:
        return self.cboBackend.currentData().type

    @property
    def backendPathMode(self) -> str:
        return self.cboBackend.currentData().pathMode


    def reloadPresetList(self, selectName: str | None = None) -> None:
        self.cboPreset.clear()

        presets: dict = getattr(Config, self.configAttr)
        for name in sorted(presets.keys()):
            self.cboPreset.addItem(name)

        if selectName:
            index = self.cboPreset.findText(selectName)
        elif self.cboPreset.count() > 0:
            index = 0
        else:
            self.fromDict({})
            index = -1

        self.cboPreset.setCurrentIndex(index)

    @Slot()
    def savePreset(self) -> None:
        if not (name := self.cboPreset.currentText().strip()):
            return

        presets: dict = getattr(Config, self.configAttr)
        newPreset = (name not in presets)
        presets[name] = self.toDict()
        self.reloadPresetList(name)
        self._onPresetNameEdited(name)
        if newPreset:
            ModelSettingsWindow.signals.presetListUpdated.emit(self.configAttr)

    @Slot()
    def deletePreset(self) -> None:
        name = self.cboPreset.currentText().strip()
        presets: dict = getattr(Config, self.configAttr)
        if name in presets:
            del presets[name]
            self.reloadPresetList()
            ModelSettingsWindow.signals.presetListUpdated.emit(self.configAttr)

    @Slot()
    def loadPreset(self, index: int) -> None:
        presets: dict = getattr(Config, self.configAttr)
        name = self.cboPreset.itemText(index)
        settings = presets.get(name, {})
        self.fromDict(settings)

    @Slot()
    def _onPresetNameEdited(self, text: str) -> None:
        presets: dict = getattr(Config, self.configAttr, None)
        if presets and text in presets:
            self.btnSave.setText("Overwrite")
            self.btnDelete.setEnabled(True)
        else:
            self.btnSave.setText("Create")
            self.btnDelete.setEnabled(False)

        self.btnSave.setEnabled(bool(text))

    @Slot()
    def _onBackendChanged(self, index) -> None:
        pass

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None, pathModeOverride=None) -> None:
        path = target.text()
        if not path and altTarget:
            path = altTarget.text()

        pathMode = pathModeOverride or self.backendPathMode
        if pathMode == BackendPathModes.FILE:
            path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Choose model file", path)
        else:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose model directory", path)

        if path:
            path = os.path.abspath(path)
            target.setText(path)


    def fromDict(self, settings: dict) -> None:
        # Find backend index
        backend = settings.get("backend", "")
        for i in range(self.cboBackend.count()):
            if self.cboBackend.itemData(i).name == backend:
                self.cboBackend.setCurrentIndex(i)
                break

        self.txtPath.setText(settings.get("model_path", ""))

    def toDict(self) -> dict:
        return {
            "backend": self.backend,
            "model_path": self.txtPath.text()
        }


class LLMModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__(configAttr, backends)

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        self.lblQuant = QtWidgets.QLabel("Quantization:")
        layout.addWidget(self.lblQuant, row, 0)
        self.cboQuant = QtWidgets.QComboBox()
        self.cboQuant.addItem("None", "none")
        self.cboQuant.addItem("bnb NF4", "nf4")
        self.cboQuant.addItem("bnb INT8", "int8")
        layout.addWidget(self.cboQuant, row, 1)

        self.lblCtxLen = QtWidgets.QLabel("Context Length:")
        self.spinCtxLen = QtWidgets.QSpinBox()
        self.spinCtxLen.setRange(512, 10_240_000)
        self.spinCtxLen.setSingleStep(512)
        layout.addWidget(self.lblCtxLen, row, 3)
        layout.addWidget(self.spinCtxLen, row, 4, 1, 2)

        row += 1
        self.lblGpuLayers = QtWidgets.QLabel("GPU Layers:")
        layout.addWidget(self.lblGpuLayers, row, 0)
        self.spinGpuLayers = qtlib.PercentageSpinBox()
        layout.addWidget(self.spinGpuLayers, row, 1)

        row += 1
        self.lblThreadCount = QtWidgets.QLabel("Thread Count:")
        self.spinThreadCount = QtWidgets.QSpinBox()
        self.spinThreadCount.setRange(1, 128)
        self.spinThreadCount.setSingleStep(1)
        layout.addWidget(self.lblThreadCount, row, 0)
        layout.addWidget(self.spinThreadCount, row, 1)

        self.lblBatchSize = QtWidgets.QLabel("Batch Size:")
        self.spinBatchSize = QtWidgets.QSpinBox()
        self.spinBatchSize.setRange(1, 16384)
        self.spinBatchSize.setSingleStep(64)
        layout.addWidget(self.lblBatchSize, row, 3)
        layout.addWidget(self.spinBatchSize, row, 4, 1, 2)

        row += 1
        from .inference_settings import InferenceSettingsWidget
        self.inferSettings = InferenceSettingsWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 7)

    @Slot()
    def _onBackendChanged(self, index):
        widgets = (
            self.lblCtxLen, self.spinCtxLen,
            self.lblBatchSize, self.spinBatchSize,
            self.lblThreadCount, self.spinThreadCount
        )

        enabled = (self.backendType == BackendTypes.LLAMA_CPP)
        self.inferSettings.setSupportsPenalty(enabled)
        for w in widgets:
            w.setEnabled(enabled)

        for w in (self.lblQuant, self.cboQuant):
            w.setEnabled(not enabled)

    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)

        quantIndex = self.cboQuant.findData(settings.get("quantization", ""))
        self.cboQuant.setCurrentIndex(max(quantIndex, 0))
        self.spinCtxLen.setValue(settings.get("ctx_length", 32768))

        gpuLayers = settings.get("gpu_layers", 100)
        if gpuLayers < 0:
            gpuLayers = 100
        self.spinGpuLayers.setValue(gpuLayers)

        self.spinThreadCount.setValue(settings.get("num_threads", 11))
        self.spinBatchSize.setValue(settings.get("batch_size", 512))

        sampleSettings = settings.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.inferSettings.fromDict(sampleSettings)
        self.inferSettings.setSupportsPenalty(self.backendType == BackendTypes.LLAMA_CPP)


    def toDict(self) -> dict:
        settings = super().toDict()
        settings["gpu_layers"] = self.spinGpuLayers.value()

        if self.backendType == BackendTypes.LLAMA_CPP:
            settings["ctx_length"]  = self.spinCtxLen.value()
            settings["num_threads"] = self.spinThreadCount.value()
            settings["batch_size"]  = self.spinBatchSize.value()
        else:
            settings["quantization"] = self.cboQuant.currentData()

        settings[Config.INFER_PRESET_SAMPLECFG_KEY] = self.inferSettings.toDict()
        return settings



class CaptionModelSettings(LLMModelSettings):
    def __init__(self, configAttr: str, backends: dict[str, BackendDef]):
        super().__init__(configAttr, backends)

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        self.lblProjectorPath = QtWidgets.QLabel("Projector Path:")
        self.txtProjectorPath = QtWidgets.QLineEdit()
        layout.addWidget(self.lblProjectorPath, row, 0)
        layout.addWidget(self.txtProjectorPath, row, 1, 1, 5)

        self.btnChooseProjector = QtWidgets.QPushButton("Choose...")
        self.btnChooseProjector.clicked.connect(lambda: self._choosePath(self.txtProjectorPath, self.txtPath))
        layout.addWidget(self.btnChooseProjector, row, 6)

        row += 1
        super().build(layout, row)

        row += 1
        self.lblVisGpuLayers = QtWidgets.QLabel("Vis GPU Layers:")
        layout.addWidget(self.lblVisGpuLayers, row, 3)
        self.spinVisGpuLayers = qtlib.PercentageSpinBox()
        layout.addWidget(self.spinVisGpuLayers, row, 4, 1, 2)

        self.lblGpuLayers.setText("LLM GPU Layers:")

    @Slot()
    def _onBackendChanged(self, index):
        super()._onBackendChanged(index)

        enabled = (self.backendType == BackendTypes.LLAMA_CPP)
        for w in (self.lblProjectorPath, self.txtProjectorPath, self.btnChooseProjector):
            w.setEnabled(enabled)

        for w in (self.lblVisGpuLayers, self.spinVisGpuLayers):
            w.setEnabled(not enabled)

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None, pathModeOverride=None):
        altTarget = self.txtProjectorPath if target == self.txtPath else self.txtPath
        super()._choosePath(target, altTarget, pathModeOverride)

    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)
        self.txtProjectorPath.setText(settings.get("proj_path", ""))

        visGpuLayers = settings.get("vis_gpu_layers", 100)
        if visGpuLayers < 0:
            visGpuLayers = 100
        self.spinVisGpuLayers.setValue(visGpuLayers)

    def toDict(self) -> dict:
        settings = super().toDict()
        if self.backendType == BackendTypes.LLAMA_CPP:
            settings["proj_path"] = self.txtProjectorPath.text()
        else:
            settings["vis_gpu_layers"] = self.spinVisGpuLayers.value()

        return settings



class TagModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__(configAttr, backends)

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        self.lblTagListPath = QtWidgets.QLabel("Tag List Path:")
        self.txtTagListPath = QtWidgets.QLineEdit()
        layout.addWidget(self.lblTagListPath, row, 0)
        layout.addWidget(self.txtTagListPath, row, 1, 1, 5)

        self.btnChooseTagList = QtWidgets.QPushButton("Choose...")
        self.btnChooseTagList.clicked.connect(lambda: self._choosePath(self.txtTagListPath, self.txtPath))
        layout.addWidget(self.btnChooseTagList, row, 6)

        row += 1
        from .tag_settings import TagSettingsWidget
        self.tagSettings = TagSettingsWidget()
        self.tagSettings.expand(animate=False)
        layout.addWidget(self.tagSettings, row, 0, 1, 7)

    @Slot()
    def _onBackendChanged(self, index):
        super()._onBackendChanged(index)

        enabled = (self.backendType == BackendTypes.ONNX)
        self.tagSettings.setSupportsRatingAndChars(enabled)
        for w in [self.lblTagListPath, self.txtTagListPath, self.btnChooseTagList]:
            w.setEnabled(enabled)

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None, pathModeOverride=None):
        altTarget = self.txtTagListPath if target == self.txtPath else self.txtPath
        super()._choosePath(target, altTarget, pathModeOverride)


    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)
        self.txtTagListPath.setText(settings.get("csv_path", ""))

        sampleSettings = settings.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.tagSettings.fromDict(sampleSettings)
        self.tagSettings.setSupportsRatingAndChars(self.backendType == BackendTypes.ONNX)

    def toDict(self) -> dict:
        settings = super().toDict()

        if self.backendType == BackendTypes.ONNX:
            settings["csv_path"] = self.txtTagListPath.text()

        settings[Config.INFER_PRESET_SAMPLECFG_KEY] = self.tagSettings.toDict()
        return settings



class MaskModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__(configAttr, backends)

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        self.lblClasses = QtWidgets.QLabel("Classes:")
        self.txtClasses = QtWidgets.QPlainTextEdit()
        self.txtClasses.setPlaceholderText("Comma-separated. If empty, all detected classes are applied.")
        qtlib.setMonospace(self.txtClasses)
        qtlib.setTextEditHeight(self.txtClasses, 3)
        layout.addWidget(self.lblClasses, row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtClasses, row, 1, 1, 5)

    @property
    def backendNeedsClasses(self) -> bool:
        return self.cboBackend.currentData().supportsClasses


    @Slot()
    def _onBackendChanged(self, index):
        super()._onBackendChanged(index)
        enabled = self.backendNeedsClasses
        for widget in (self.lblClasses, self.txtClasses):
            widget.setEnabled(enabled)


    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)
        if self.backendNeedsClasses:
            classes = ", ".join(settings.get("classes", []))
            self.txtClasses.setPlainText(classes)

    def toDict(self) -> dict:
        settings = super().toDict()

        if self.backendNeedsClasses:
            classes = (name.strip() for name in self.txtClasses.toPlainText().split(","))
            exist = {""}
            settings["classes"] = [ name for name in classes if not (name in exist or exist.add(name)) ]

        return settings



class ScaleModelSettings(BaseSettingsWidget):
    KEY_BACKEND        = "backend"
    KEY_INTERP_UP      = "interp_up"
    KEY_INTERP_DOWN    = "interp_down"
    KEY_LPFILTER       = "filter_lowpass"
    KEY_LEVELS         = "levels"
    LEVELKEY_THRESHOLD = "threshold"
    LEVELKEY_MODELPATH = "model_path"

    DEFAULT_BACKEND     = "upscale"
    DEFAULT_INTERP_UP   = "Lanczos"
    DEFAULT_INTERP_DOWN = "Area"
    DEFAULT_LPFILTER    = True

    @classmethod
    def getInterpUp(cls, preset: dict) -> str:
        return preset.get(cls.KEY_INTERP_UP, cls.DEFAULT_INTERP_UP)

    @classmethod
    def getInterpDown(cls, preset: dict) -> str:
        return preset.get(cls.KEY_INTERP_DOWN, cls.DEFAULT_INTERP_DOWN)

    @classmethod
    def getLowPassFilter(cls, preset: dict) -> bool:
        return preset.get(cls.KEY_LPFILTER, cls.DEFAULT_LPFILTER)


    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__(configAttr, backends)

    def _buildBase(self, layout: QtWidgets.QGridLayout, row: int) -> int:
        return row

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        layout.setColumnStretch(1, 0)
        layout.setColumnMinimumWidth(3, 12)

        from ui.export_settings import INTERP_MODES
        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area

        self.chkLpFilter = QtWidgets.QCheckBox("Anti-Aliasing (prevents artifacts when downscaling large images, but might blur)")
        self.chkLpFilter.setChecked(True)

        layout.addWidget(QtWidgets.QLabel("Downscale:"), row, 0)
        layout.addWidget(QtWidgets.QLabel("Interpolation:"), row, 1)
        layout.addWidget(self.cboInterpDown, row, 2)
        layout.addWidget(self.chkLpFilter, row, 4, 1, 3)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Upscale:"), row, 0)

        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos

        layout.addWidget(QtWidgets.QLabel("Interpolation:"), row, 1)
        layout.addWidget(self.cboInterpUp, row, 2)
        layout.addWidget(QtWidgets.QLabel("Will use simple interpolation when upscaling until the first threshold defined below."), row, 4, 1, 3)

        row += 1
        layout.setRowMinimumHeight(row, 12)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Upscale Levels:"), row, 0)
        layout.addWidget(QtWidgets.QLabel("Select model by upscale factor:"), row, 1, 1, 4)

        row += 1
        self.scaleLevels: list[tuple[QtWidgets.QDoubleSpinBox, QtWidgets.QLineEdit]] = list()
        altPathTarget = None
        for i in range(3):
            spinScaleThreshold = QtWidgets.QDoubleSpinBox()
            spinScaleThreshold.setPrefix("> ")
            spinScaleThreshold.setRange(1.0, 1024.0)
            spinScaleThreshold.setSingleStep(0.05)
            spinScaleThreshold.valueChanged.connect(lambda value, index=i: self._onThresholdChanged(value, index))
            layout.addWidget(spinScaleThreshold, row+i, 1)

            txtModelPath = QtWidgets.QLineEdit()
            txtModelPath.setPlaceholderText("Leave empty to disable")
            layout.addWidget(txtModelPath, row+i, 2, 1, 4)

            btnChoosePath = QtWidgets.QPushButton("Choose...")
            btnChoosePath.clicked.connect(lambda checked, textfield=txtModelPath: self._choosePath(textfield, altPathTarget))
            layout.addWidget(btnChoosePath, row+i, 6)

            self.scaleLevels.append((spinScaleThreshold, txtModelPath))
            altPathTarget = self.scaleLevels[0][1]

        self._resetValues()


    def _onThresholdChanged(self, value: float, index: int):
        minVal = self.scaleLevels[index-1][0].value() if index > 0 else 1.0
        if value < minVal:
            self.scaleLevels[index][0].setValue(minVal)

        maxVal = self.scaleLevels[index+1][0].value() if index < len(self.scaleLevels)-1 else 1024
        if value > maxVal:
            self.scaleLevels[index][0].setValue(maxVal)

    def _resetValues(self):
        values = [1.25, 2.0, 4.0]
        for val, level in zip(values, self.scaleLevels):
            with QSignalBlocker(level[0]):
                level[0].setValue(val)
                level[1].setText("")


    def fromDict(self, settings: dict) -> None:
        # Ignore backend since there's only one

        self._resetValues()

        interpDownIndex = self.cboInterpDown.findText( self.getInterpDown(settings) )
        self.cboInterpDown.setCurrentIndex(interpDownIndex)

        interpUpIndex = self.cboInterpDown.findText( self.getInterpUp(settings) )
        self.cboInterpUp.setCurrentIndex(interpUpIndex)

        self.chkLpFilter.setChecked(self.getLowPassFilter(settings))

        levels: list[dict] = settings.get(self.KEY_LEVELS, [])
        for i, level in zip((0, 1, 2), levels):
            with QSignalBlocker(self.scaleLevels[i][0]):
                self.scaleLevels[i][0].setValue(level.get(self.LEVELKEY_THRESHOLD, 1.0))
            self.scaleLevels[i][1].setText(level.get(self.LEVELKEY_MODELPATH, ""))


    def toDict(self) -> dict:
        levels = list()
        for spinThreshold, txtModelPath in self.scaleLevels:
            if path := txtModelPath.text():
                levels.append({
                    self.LEVELKEY_THRESHOLD: round(spinThreshold.value(), 2),
                    self.LEVELKEY_MODELPATH: path
                })

        return {
            self.KEY_BACKEND:     self.DEFAULT_BACKEND,
            self.KEY_INTERP_UP:   self.cboInterpUp.currentText(),
            self.KEY_INTERP_DOWN: self.cboInterpDown.currentText(),
            self.KEY_LPFILTER:    self.chkLpFilter.isChecked(),
            self.KEY_LEVELS:      levels
        }



class EmbeddingModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: Mapping[str, BackendDef]):
        super().__init__(configAttr, backends)

    def build(self, layout: QtWidgets.QGridLayout, row: int):
        row += 1
        layout.setRowMinimumHeight(row, 12)

        row += 1
        self.lblTextModel = QtWidgets.QLabel("Text Model:")
        layout.addWidget(self.lblTextModel, row, 0)

        self.txtTextModel = QtWidgets.QLineEdit()
        layout.addWidget(self.txtTextModel, row, 1, 1, 5)

        self.btnChooseTextModel = QtWidgets.QPushButton("Choose...")
        self.btnChooseTextModel.clicked.connect(lambda: self._choosePath(self.txtTextModel, self.txtVisionModel, BackendPathModes.FILE))
        layout.addWidget(self.btnChooseTextModel, row, 6)

        row += 1
        self.lblVisionModel = QtWidgets.QLabel("Vision Model:")
        layout.addWidget(self.lblVisionModel, row, 0)

        self.txtVisionModel = QtWidgets.QLineEdit()
        layout.addWidget(self.txtVisionModel, row, 1, 1, 5)

        self.btnChooseVisionModel = QtWidgets.QPushButton("Choose...")
        self.btnChooseVisionModel.clicked.connect(lambda: self._choosePath(self.txtVisionModel, self.txtTextModel, BackendPathModes.FILE))
        layout.addWidget(self.btnChooseVisionModel, row, 6)

        row += 1
        layout.setRowMinimumHeight(row, 12)

        row += 1
        self.lblProcessing = QtWidgets.QLabel("Image Processing:")
        layout.addWidget(self.lblProcessing, row, 0)

        self.cboProcessing = QtWidgets.QComboBox()
        for key, method in embed.PROCESSING.items():
            self.cboProcessing.addItem(method.name, key)
        layout.addWidget(self.cboProcessing, row, 1, 1, 5)

        row += 1
        self.lblAggregate = QtWidgets.QLabel("Patch Aggregate:")
        layout.addWidget(self.lblAggregate, row, 0)

        self.cboAggregate = QtWidgets.QComboBox()
        for key, aggregate in embed.AGGREGATE.items():
            self.cboAggregate.addItem(aggregate.name, key)
        layout.addWidget(self.cboAggregate, row, 1, 1, 5)


    @property
    def backendNeedsSeparateModels(self):
        return self.backendType == BackendTypes.ONNX

    @Slot()
    def _onBackendChanged(self, index):
        super()._onBackendChanged(index)
        enabled = self.backendNeedsSeparateModels
        self.lblPath.setText("Config Folder:" if enabled else "Model Path:")

        widgets = (
            self.lblTextModel, self.txtTextModel, self.btnChooseTextModel,
            self.lblVisionModel, self.txtVisionModel, self.btnChooseVisionModel,
            self.lblProcessing, self.cboProcessing, self.lblAggregate, self.cboAggregate
        )
        for widget in widgets:
            widget.setEnabled(enabled)


    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)
        if self.backendNeedsSeparateModels:
            self.txtTextModel.setText(settings.get("text_model_path", ""))
            self.txtVisionModel.setText(settings.get("vision_model_path", ""))

            sampleCfg: dict = settings.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})

            processing = sampleCfg.get(embed.CONFIG_KEY_PROCESSING, embed.DEFAULT_PROCESSING)
            processingIndex = self.cboProcessing.findData(processing)
            self.cboProcessing.setCurrentIndex(max(processingIndex, 0))

            aggregate = sampleCfg.get(embed.CONFIG_KEY_AGGREGATE, embed.DEFAULT_AGGREGATE)
            aggregateIndex = self.cboAggregate.findData(aggregate)
            self.cboAggregate.setCurrentIndex(max(aggregateIndex, 0))

        else:
            self.txtTextModel.setText("")
            self.txtVisionModel.setText("")
            self.cboProcessing.setCurrentIndex(0)
            self.cboAggregate.setCurrentIndex(0)


    def toDict(self) -> dict:
        settings = super().toDict()

        if self.backendNeedsSeparateModels:
            settings["text_model_path"] = self.txtTextModel.text().strip()
            settings["vision_model_path"] = self.txtVisionModel.text().strip()

            settings[Config.INFER_PRESET_SAMPLECFG_KEY] = {
                embed.CONFIG_KEY_PROCESSING: self.cboProcessing.currentData(),
                embed.CONFIG_KEY_AGGREGATE:  self.cboAggregate.currentData()
            }

        return settings
