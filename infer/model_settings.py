from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, Signal, QObject
from .inference_settings import InferenceSettingsWidget
from config import Config


class BackendTypes:
    LLamaCpp = "llamacpp"
    Transformers = "transformers"

Backends = {
    "MiniCPM-V-2.6": ("minicpm", BackendTypes.LLamaCpp),
    "InternVL2": ("internvl2", BackendTypes.Transformers),
    "Qwen2-VL": ("qwen2vl", BackendTypes.Transformers)
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

        tabWidget = QtWidgets.QTabWidget()
        tabWidget.addTab(CaptionModelSettings(), "Caption")
        tabWidget.addTab(QtWidgets.QWidget(), "Tags")
        tabWidget.addTab(QtWidgets.QWidget(), "LLM")
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
    def __init__(self):
        super().__init__()

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

        row = 0
        self.cboPreset = QtWidgets.QComboBox()
        self.cboPreset.setEditable(True)
        self.cboPreset.editTextChanged.connect(self._onPresetNameEdited)
        self.cboPreset.currentIndexChanged.connect(self.loadPreset)
        layout.addWidget(QtWidgets.QLabel("Preset Name:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.cboPreset, row, 1, 1, 4)

        self.btnSave = QtWidgets.QPushButton("Save")
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 5)

        row += 1
        self.btnDelete = QtWidgets.QPushButton("Delete")
        self.btnDelete.clicked.connect(self.deletePreset)
        layout.addWidget(self.btnDelete, row, 5)

        row += 1
        layout.setRowMinimumHeight(row, 16)

        row += 1
        self.cboBackend= QtWidgets.QComboBox()
        for name, data in Backends.items():
            self.cboBackend.addItem(f"{name} ({data[1]})", userData=data)
        self.cboBackend.currentIndexChanged.connect(self._onBackendChanged)
        layout.addWidget(QtWidgets.QLabel("Backend:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.cboBackend, row, 1, 1, 4)

        row += 1
        self.txtPath = QtWidgets.QLineEdit()
        layout.addWidget(QtWidgets.QLabel("Model Path:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtPath, row, 1, 1, 4)

        btnChooseModel = QtWidgets.QPushButton("Choose...")
        btnChooseModel.clicked.connect(lambda: self._choosePath(self.txtPath, self.txtProjectorPath))
        layout.addWidget(btnChooseModel, row, 5)

        row += 1
        self.lblProjectorPath = QtWidgets.QLabel("Projector Path:")
        self.txtProjectorPath = QtWidgets.QLineEdit()
        layout.addWidget(self.lblProjectorPath, row, 0, Qt.AlignTop)
        layout.addWidget(self.txtProjectorPath, row, 1, 1, 4)

        self.btnChooseProjector = QtWidgets.QPushButton("Choose...")
        self.btnChooseProjector.clicked.connect(lambda: self._choosePath(self.txtProjectorPath, self.txtPath))
        layout.addWidget(self.btnChooseProjector, row, 5)


        row += 1
        self.spinGpuLayers = QtWidgets.QSpinBox()
        self.spinGpuLayers.setRange(-1, 999)
        self.spinGpuLayers.setSingleStep(1)
        layout.addWidget(QtWidgets.QLabel("GPU Layers:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.spinGpuLayers, row, 1)

        self.spinCtxLen = QtWidgets.QSpinBox()
        self.spinCtxLen.setRange(512, 10_240_000)
        self.spinCtxLen.setSingleStep(512)
        layout.addWidget(QtWidgets.QLabel("Context Length:"), row, 3, Qt.AlignTop)
        layout.addWidget(self.spinCtxLen, row, 4)

        row += 1
        self.lblThreadCount = QtWidgets.QLabel("Thread Count:")
        self.spinThreadCount = QtWidgets.QSpinBox()
        self.spinThreadCount.setRange(1, 128)
        self.spinThreadCount.setSingleStep(1)
        layout.addWidget(self.lblThreadCount, row, 0, Qt.AlignTop)
        layout.addWidget(self.spinThreadCount, row, 1)

        self.lblBatchSize = QtWidgets.QLabel("Batch Size:")
        self.spinBatchSize = QtWidgets.QSpinBox()
        self.spinBatchSize.setRange(1, 16384)
        self.spinBatchSize.setSingleStep(64)
        layout.addWidget(self.lblBatchSize, row, 3, Qt.AlignTop)
        layout.addWidget(self.spinBatchSize, row, 4)

        # TODO: Prompts?

        row += 1
        self.inferSettings = InferenceSettingsWidget()
        layout.addWidget(self.inferSettings, row, 0, 1, 6)

        self.setLayout(layout)

        self.fromDict({})
        self.reloadPresetList()


    def reloadPresetList(self, selectName: str = None):
        self.cboPreset.clear()
        for name in sorted(Config.inferCaptionPresets.keys()):
            self.cboPreset.addItem(name)
        
        if selectName:
            index = self.cboPreset.findText(selectName)
        elif self.cboPreset.count() > 0:
            index = 0
        self.cboPreset.setCurrentIndex(index)

    @Slot()
    def savePreset(self):
        name = self.cboPreset.currentText().strip()
        if name:
            newPreset = (name not in Config.inferCaptionPresets)
            Config.inferCaptionPresets[name] = self.toDict()
            self.reloadPresetList(name)
            if newPreset:
                ModelSettingsWindow.signals.presetListUpdated.emit("inferCaptionPresets")

    @Slot()
    def deletePreset(self):
        name = self.cboPreset.currentText().strip()
        if name in Config.inferCaptionPresets:
            del Config.inferCaptionPresets[name]
            self.reloadPresetList()
            ModelSettingsWindow.signals.presetListUpdated.emit("inferCaptionPresets")

    @Slot()
    def loadPreset(self, index):
        empty: dict = {}
        name = self.cboPreset.itemText(index)
        settings = Config.inferCaptionPresets.get(name, empty)
        self.fromDict(settings)

    @Slot()
    def _onPresetNameEdited(self, text: str):
        if text in Config.inferCaptionPresets:
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
            self.lblProjectorPath, self.txtProjectorPath,
            self.btnChooseProjector
        ]

        backend, backendType = self.cboBackend.currentData()
        enabled = (backendType == BackendTypes.LLamaCpp)
        for w in widgets:
            w.setEnabled(enabled)


    def _choosePath(self, target, otherPath):
        path = target.text()
        if not path:
            path = otherPath.text()

        backend, backendType = self.cboBackend.currentData()
        if backendType == BackendTypes.LLamaCpp:
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
        self.spinCtxLen.setValue(settings.get("ctx_length", 8192))

        self.txtProjectorPath.setText(settings.get("proj_path", ""))
        self.spinThreadCount.setValue(settings.get("num_threads", 12))
        self.spinBatchSize.setValue(settings.get("batch_size", 512))

        sampleSettings = settings.get(InferenceSettingsWidget.PRESET_KEY, {})
        self.inferSettings.fromDict(sampleSettings)


    def toDict(self) -> dict:
        backend, backendType = self.cboBackend.currentData()
        settings = {
            "backend":      backend,
            "model_path":   self.txtPath.text(),
            "gpu_layers":   self.spinGpuLayers.value(),
            "ctx_length":   self.spinCtxLen.value()
        }

        if backendType == BackendTypes.LLamaCpp:
            settings["proj_path"]   = self.txtProjectorPath.text()
            settings["num_threads"] = self.spinThreadCount.value()
            settings["batch_size"]  = self.spinBatchSize.value()
        
        settings[InferenceSettingsWidget.PRESET_KEY] = self.inferSettings.toDict()
        return settings
