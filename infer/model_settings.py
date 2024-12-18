from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject
from .inference_settings import InferenceSettingsWidget
from config import Config
from lib import qtlib

# TODO: Define GPU layers as percentage


class BackendTypes:
    LLAMA_CPP    = "llama.cpp"
    TRANSFORMERS = "transformers"
    ONNX         = "onnx"
    TORCH        = "torch"
    ULTRALYTICS  = "ultralytics"

class BackendPathModes:
    FILE   = "file"
    FOLDER = "folder"


BackendsCaption = {
    "Florence-2":       ("florence2", BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER),
    "InternVL2":        ("internvl2", BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER),
    "MiniCPM-V-2.6":    ("minicpm",   BackendTypes.LLAMA_CPP, BackendPathModes.FILE),
    "Molmo":            ("molmo",     BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER),
    "Ovis-1.6":         ("ovis16",    BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER),
    "Qwen2-VL":         ("qwen2vl",   BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER)
}

# TODO: Allow loading of caption models as LLM.
#       Set visual layers to 0? -> No, load as defined in config to prevent reloading.
BackendsLLM = {
    "GGUF": ("gguf", BackendTypes.LLAMA_CPP, BackendPathModes.FILE)
}

BackendsTag = {
    "WD":       ("wd",     BackendTypes.ONNX,  BackendPathModes.FILE),
    "JoyTag":   ("joytag", BackendTypes.TORCH, BackendPathModes.FOLDER)
}

# Last element defines whether the backend supports classes: bool
BackendsMask = {
    "BriaAI RMBG-2.0":      ("bria-rmbg",         BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER, False),
    "Florence-2 Detect":    ("florence2-detect",  BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER, True),
    "Florence-2 Segment":   ("florence2-segment", BackendTypes.TRANSFORMERS, BackendPathModes.FOLDER, True),
    "Inspyrenet RemBg":     ("inspyrenet",        BackendTypes.TORCH,        BackendPathModes.FILE,   False),
    "Yolo Detect":          ("yolo-detect",       BackendTypes.ULTRALYTICS,  BackendPathModes.FILE,   True)
}


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
        self.tagSettings = TagModelSettings("inferTagPresets", BackendsTag)
        self.llmSettings = LLMModelSettings("inferLLMPresets", BackendsLLM)
        self.maskSettings = MaskModelSettings("inferMaskPresets", BackendsMask)
        
        self.tabWidget = QtWidgets.QTabWidget()
        self.tabWidget.addTab(self.captionSettings, "Caption")
        self.tabWidget.addTab(self.tagSettings, "Tags")
        self.tabWidget.addTab(self.llmSettings, "LLM")
        self.tabWidget.addTab(self.maskSettings, "Mask")
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
            case "inferCaptionPresets": index, widget = 0, win.captionSettings
            case "inferTagPresets":     index, widget = 1, win.tagSettings
            case "inferLLMPresets":     index, widget = 2, win.llmSettings
            case "inferMaskPresets":    index, widget = 3, win.maskSettings
            case _: return

        win.tabWidget.setCurrentIndex(index)
        widget.reloadPresetList(presetName)

    @classmethod
    def closeInstance(cls):
        if isinstance(cls._instance, cls):
            cls._instance.close()



class BaseSettingsWidget(QtWidgets.QWidget):
    def __init__(self, configAttr: str, backends: dict):
        super().__init__()
        self.configAttr = configAttr
        self.backends = backends

        self._build()


    def _build(self) -> None:
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, 100)
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
        layout.addWidget(self.btnSave, row, 5, Qt.AlignRight)

        #row += 1
        self.btnDelete = QtWidgets.QPushButton("Delete")
        self.btnDelete.setEnabled(False)
        self.btnDelete.clicked.connect(self.deletePreset)
        layout.addWidget(self.btnDelete, row, 6)

        row += 1
        layout.setRowMinimumHeight(row, 16)

        row += 1
        self.cboBackend= QtWidgets.QComboBox()
        for name, data in self.backends.items():
            self.cboBackend.addItem(f"{name} ({data[1]})", userData=data)
        self.cboBackend.currentIndexChanged.connect(self._onBackendChanged)
        layout.addWidget(QtWidgets.QLabel("Backend:"), row, 0)
        layout.addWidget(self.cboBackend, row, 1, 1, 5)

        row += 1
        self.txtPath = QtWidgets.QLineEdit()
        layout.addWidget(QtWidgets.QLabel("Model Path:"), row, 0)
        layout.addWidget(self.txtPath, row, 1, 1, 5)

        btnChooseModel = QtWidgets.QPushButton("Choose...")
        btnChooseModel.clicked.connect(lambda: self._choosePath(self.txtPath))
        layout.addWidget(btnChooseModel, row, 6)

        self.build(layout, row+1)
        self.setLayout(layout)

        self.fromDict({})
        self.reloadPresetList()
        self._onBackendChanged(self.cboBackend.currentIndex())

    def build(self, layout: QtWidgets.QGridLayout, row: int) -> None:
        raise NotImplementedError()


    @property
    def backend(self) -> str:
        return self.cboBackend.currentData()[0]
    
    @property
    def backendType(self) -> str:
        return self.cboBackend.currentData()[1]
    
    @property
    def backendPathMode(self) -> str:
        return self.cboBackend.currentData()[2]


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

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None) -> None:
        path = target.text()
        if not path and altTarget:
            path = altTarget.text()

        if self.backendPathMode == BackendPathModes.FILE:
            path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Choose model file", path)
        else:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose model directory", path)
        
        if path:
            target.setText(path)


    def fromDict(self, settings: dict) -> None:
        # Find backend index
        backend = settings.get("backend", "")
        for i in range(self.cboBackend.count()):
            if self.cboBackend.itemData(i)[0] == backend:
                self.cboBackend.setCurrentIndex(i)

        self.txtPath.setText(settings.get("model_path", ""))

    def toDict(self) -> dict:
        return {
            "backend": self.backend,
            "model_path": self.txtPath.text()
        }


class LLMModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: dict):
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
    def __init__(self, configAttr: str, backends: dict):
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

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None):
        altTarget = self.txtProjectorPath if target == self.txtPath else self.txtPath
        super()._choosePath(target, altTarget)

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
    def __init__(self, configAttr: str, backends: dict):
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
        self.spinThreshold = QtWidgets.QDoubleSpinBox()
        self.spinThreshold.setRange(0.01, 1.0)
        self.spinThreshold.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Tag Threshold:"), row, 0)
        layout.addWidget(self.spinThreshold, row, 1)

    @Slot()
    def _onBackendChanged(self, index):
        super()._onBackendChanged(index)

        enabled = (self.backendType == BackendTypes.ONNX)
        for w in [self.lblTagListPath, self.txtTagListPath, self.btnChooseTagList]:
            w.setEnabled(enabled)

    def _choosePath(self, target: QtWidgets.QLineEdit, altTarget: QtWidgets.QLineEdit | None = None):
        altTarget = self.txtTagListPath if target == self.txtPath else self.txtPath
        super()._choosePath(target, altTarget)

    def fromDict(self, settings: dict) -> None:
        super().fromDict(settings)
        self.txtTagListPath.setText(settings.get("csv_path", ""))

        sampleSettings = settings.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.spinThreshold.setValue(sampleSettings.get("threshold", 0.35))

    def toDict(self) -> dict:
        settings = super().toDict()

        if self.backendType == BackendTypes.ONNX:
            settings["csv_path"] = self.txtTagListPath.text()

        settings[Config.INFER_PRESET_SAMPLECFG_KEY] = {
            "threshold": self.spinThreshold.value()
        }
        return settings



class MaskModelSettings(BaseSettingsWidget):
    def __init__(self, configAttr: str, backends: dict):
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
        return self.cboBackend.currentData()[3]


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
