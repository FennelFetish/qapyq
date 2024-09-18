from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject
from .inference_settings import InferenceSettingsWidget
from config import Config


class BackendTypes:
    LLAMA_CPP    = "llama.cpp"
    TRANSFORMERS = "transformers"

BackendsCaption = {
    "MiniCPM-V-2.6": ("minicpm", BackendTypes.LLAMA_CPP),
    "InternVL2": ("internvl2", BackendTypes.TRANSFORMERS),
    "Qwen2-VL": ("qwen2vl", BackendTypes.TRANSFORMERS)
}

BackendsLLM = {
    "GGUF": ("gguf", BackendTypes.LLAMA_CPP)
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
        self.setWindowTitle("Model Settings")
        self.resize(800, self.height())

        captionSettings = CaptionModelSettings("inferCaptionPresets", BackendsCaption, True)
        llmSettings = CaptionModelSettings("inferLLMPresets", BackendsLLM, False)

        tabWidget = QtWidgets.QTabWidget()
        tabWidget.addTab(captionSettings, "Caption")
        tabWidget.addTab(QtWidgets.QWidget(), "Tags")
        tabWidget.addTab(llmSettings, "LLM")
        self.setCentralWidget(tabWidget)

    def closeEvent(self, event):
        super().closeEvent(event)
        ModelSettingsWindow._instance = None

    @classmethod
    def openInstance(cls, parent):
        win = ModelSettingsWindow(parent)
        win.show()
        win.activateWindow()

    @classmethod
    def closeInstance(cls):
        if isinstance(cls._instance, cls):
            cls._instance.close()



class CaptionModelSettings(QtWidgets.QWidget):
    def __init__(self, configAttr: str, backends: dict, projector: bool):
        super().__init__()
        self.configAttr = configAttr
        self.backends = backends
        self.projector = projector

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
        self.cboPreset.editTextChanged.connect(self._onPresetNameEdited)
        self.cboPreset.currentIndexChanged.connect(self.loadPreset)
        layout.addWidget(QtWidgets.QLabel("Preset Name:"), row, 0)
        layout.addWidget(self.cboPreset, row, 1, 1, 4)

        self.btnSave = QtWidgets.QPushButton("Save")
        #self.btnSave.setFixedWidth(100)
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 5, Qt.AlignRight)

        #row += 1
        self.btnDelete = QtWidgets.QPushButton("Delete")
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
        if self.projector:
            btnChooseModel.clicked.connect(lambda: self._choosePath(self.txtPath, self.txtProjectorPath))
        else:
            btnChooseModel.clicked.connect(lambda: self._choosePath(self.txtPath, None))
        layout.addWidget(btnChooseModel, row, 6)

        if self.projector:
            row += 1
            self.lblProjectorPath = QtWidgets.QLabel("Projector Path:")
            self.txtProjectorPath = QtWidgets.QLineEdit()
            layout.addWidget(self.lblProjectorPath, row, 0)
            layout.addWidget(self.txtProjectorPath, row, 1, 1, 5)

            self.btnChooseProjector = QtWidgets.QPushButton("Choose...")
            self.btnChooseProjector.clicked.connect(lambda: self._choosePath(self.txtProjectorPath, self.txtPath))
            layout.addWidget(self.btnChooseProjector, row, 6)

        row += 1
        self.spinGpuLayers = QtWidgets.QSpinBox()
        self.spinGpuLayers.setRange(-1, 999)
        self.spinGpuLayers.setSingleStep(1)
        layout.addWidget(QtWidgets.QLabel("GPU Layers:"), row, 0)
        layout.addWidget(self.spinGpuLayers, row, 1)

        self.spinCtxLen = QtWidgets.QSpinBox()
        self.spinCtxLen.setRange(512, 10_240_000)
        self.spinCtxLen.setSingleStep(512)
        layout.addWidget(QtWidgets.QLabel("Context Length:"), row, 3)
        layout.addWidget(self.spinCtxLen, row, 4, 1, 2)

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

        # TODO: Prompts?

        row += 1
        self.inferSettings = InferenceSettingsWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 7)

        self.setLayout(layout)

        self.fromDict({})
        self.reloadPresetList()


    def reloadPresetList(self, selectName: str = None):
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
    def savePreset(self):
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
    def deletePreset(self):
        name = self.cboPreset.currentText().strip()
        presets: dict = getattr(Config, self.configAttr)
        if name in presets:
            del presets[name]
            self.reloadPresetList()
            ModelSettingsWindow.signals.presetListUpdated.emit(self.configAttr)

    @Slot()
    def loadPreset(self, index):
        presets: dict = getattr(Config, self.configAttr)
        name = self.cboPreset.itemText(index)
        settings = presets.get(name, {})
        self.fromDict(settings)

    @Slot()
    def _onPresetNameEdited(self, text: str):
        presets: dict = getattr(Config, self.configAttr, None)
        if presets and text in presets:
            self.btnSave.setText("Overwrite")
            self.btnDelete.setEnabled(True)
        else:
            self.btnSave.setText("Create")
            self.btnDelete.setEnabled(False)


    @Slot()
    def _onBackendChanged(self, index):
        widgets = [
            self.lblBatchSize, self.spinBatchSize,
            self.lblThreadCount, self.spinThreadCount,
            self.btnChooseProjector
        ]

        if self.projector:
            widgets += [self.lblProjectorPath, self.txtProjectorPath]

        backend, backendType = self.cboBackend.currentData()
        enabled = (backendType == BackendTypes.LLAMA_CPP)
        for w in widgets:
            w.setEnabled(enabled)


    def _choosePath(self, target, otherPath):
        path = target.text()
        if not path and otherPath:
            path = otherPath.text()

        backend, backendType = self.cboBackend.currentData()
        if backendType == BackendTypes.LLAMA_CPP:
            path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Choose model file", path)
        else:
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose model directory", path)
        
        if path:
            target.setText(path)


    def fromDict(self, settings: dict):
        # Find backend index
        backend = settings.get("backend", "")
        for i in range(self.cboBackend.count()):
            if self.cboBackend.itemData(i)[0] == backend:
                self.cboBackend.setCurrentIndex(i)

        self.txtPath.setText(settings.get("model_path", ""))
        self.spinGpuLayers.setValue(settings.get("gpu_layers", -1))
        self.spinCtxLen.setValue(settings.get("ctx_length", 32768))

        if self.projector:
            self.txtProjectorPath.setText(settings.get("proj_path", ""))
        
        self.spinThreadCount.setValue(settings.get("num_threads", 15))
        self.spinBatchSize.setValue(settings.get("batch_size", 512))

        sampleSettings = settings.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.inferSettings.fromDict(sampleSettings)


    def toDict(self) -> dict:
        backend, backendType = self.cboBackend.currentData()
        settings = {
            "backend":      backend,
            "model_path":   self.txtPath.text(),
            "gpu_layers":   self.spinGpuLayers.value(),
            "ctx_length":   self.spinCtxLen.value()
        }

        if backendType == BackendTypes.LLAMA_CPP:
            if self.projector:
                settings["proj_path"] = self.txtProjectorPath.text()
            
            settings["num_threads"] = self.spinThreadCount.value()
            settings["batch_size"]  = self.spinBatchSize.value()
        
        settings[Config.INFER_PRESET_SAMPLECFG_KEY] = self.inferSettings.toDict()
        return settings
