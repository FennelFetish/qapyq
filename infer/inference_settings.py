from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
import superqt
from config import Config


class InferenceSettingsWidget(superqt.QCollapsible):
    def __init__(self, configKey="minicpm"):
        super().__init__(f"Sample Settings ({configKey})")
        self.configKey = configKey

        self.layout().setContentsMargins(6, 4, 6, 0)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.Base)
        self.setStyleSheet("QCollapsible{border: 2px groove " + winColor.name() + "; border-radius: 3px}")

        layout = self._build()
        layout.setContentsMargins(0, 0, 0, 6)
        self.loadFromConfig()

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)


    def _build(self):
        spacerHeight = 8

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnMinimumWidth(2, 16)
        layout.setColumnMinimumWidth(3, Config.batchWinLegendWidth)
        layout.setColumnMinimumWidth(5, 16)
        layout.setColumnMinimumWidth(6, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 0)

        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)
        layout.setColumnStretch(5, 0)

        layout.setColumnStretch(6, 0)
        layout.setColumnStretch(7, 1)

        self.tokensMax = QtWidgets.QSpinBox()
        self.tokensMax.setRange(10, 5000)
        self.tokensMax.setSingleStep(10)
        layout.addWidget(QtWidgets.QLabel("Max Tokens:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.tokensMax, 0, 1)

        self.tokensContext = QtWidgets.QSpinBox()
        self.tokensContext.setRange(512, 1024000)
        self.tokensContext.setSingleStep(512)
        layout.addWidget(QtWidgets.QLabel("Context Tokens:"), 0, 3, Qt.AlignTop)
        layout.addWidget(self.tokensContext, 0, 4)

        self.gpuLayers = QtWidgets.QSpinBox()
        self.gpuLayers.setRange(-1, 999)
        self.gpuLayers.setSingleStep(1)
        layout.addWidget(QtWidgets.QLabel("GPU Layers:"), 0, 6, Qt.AlignTop)
        layout.addWidget(self.gpuLayers, 0, 7)

        layout.setRowMinimumHeight(1, spacerHeight)

        self.temperature = QtWidgets.QDoubleSpinBox()
        self.temperature.setRange(0.0, 5.0)
        self.temperature.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Temperature:"), 2, 0, Qt.AlignTop)
        layout.addWidget(self.temperature, 2, 1)

        self.topK = QtWidgets.QSpinBox()
        self.topK.setRange(0, 200)
        self.topK.setSingleStep(5)
        layout.addWidget(QtWidgets.QLabel("Top K:"), 2, 3, Qt.AlignTop)
        layout.addWidget(self.topK, 2, 4)


        self.minP = QtWidgets.QDoubleSpinBox()
        self.minP.setRange(0.0, 1.0)
        self.minP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Min P:"), 3, 0, Qt.AlignTop)
        layout.addWidget(self.minP, 3, 1)

        self.topP = QtWidgets.QDoubleSpinBox()
        self.topP.setRange(0.0, 1.0)
        self.topP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Top P:"), 3, 3, Qt.AlignTop)
        layout.addWidget(self.topP, 3, 4)

        self.typicalP = QtWidgets.QDoubleSpinBox()
        self.typicalP.setRange(0.0, 1.0)
        self.typicalP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Typical P:"), 3, 6, Qt.AlignTop)
        layout.addWidget(self.typicalP, 3, 7)

        layout.setRowMinimumHeight(4, spacerHeight)

        self.freqPenalty = QtWidgets.QDoubleSpinBox()
        self.freqPenalty.setRange(-2.0, 2.0)
        self.freqPenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Freqency Penalty:"), 5, 0, Qt.AlignTop)
        layout.addWidget(self.freqPenalty, 5, 1)

        self.presencePenalty = QtWidgets.QDoubleSpinBox()
        self.presencePenalty.setRange(-2.0, 2.0)
        self.presencePenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Presence Penalty:"), 5, 3, Qt.AlignTop)
        layout.addWidget(self.presencePenalty, 5, 4)

        self.repeatPenalty = QtWidgets.QDoubleSpinBox()
        self.repeatPenalty.setRange(1.0, 3.0)
        self.repeatPenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Repetition Penalty:"), 5, 6, Qt.AlignTop)
        layout.addWidget(self.repeatPenalty, 5, 7)


        self.microstatMode = QtWidgets.QSpinBox()
        self.microstatMode.setRange(0, 2)
        layout.addWidget(QtWidgets.QLabel("Microstat Mode:"), 7, 0, Qt.AlignTop)
        layout.addWidget(self.microstatMode, 7, 1)

        self.microstatTau = QtWidgets.QDoubleSpinBox()
        self.microstatTau.setRange(0.0, 20.0)
        self.microstatTau.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Microstat Tau:"), 7, 3, Qt.AlignTop)
        layout.addWidget(self.microstatTau, 7, 4)

        self.microstatEta = QtWidgets.QDoubleSpinBox()
        self.microstatEta.setRange(0.0, 1.0)
        self.microstatEta.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Microstat Eta:"), 7, 6, Qt.AlignTop)
        layout.addWidget(self.microstatEta, 7, 7)


        self.tfsZ = QtWidgets.QDoubleSpinBox()
        self.tfsZ.setRange(0.0, 1.0)
        self.tfsZ.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("TFS Z:"), 9, 0, Qt.AlignTop)
        layout.addWidget(self.tfsZ, 9, 1)

        layout.setRowMinimumHeight(10, spacerHeight)

        self.btnSave = QtWidgets.QPushButton("Save to Config")
        self.btnSave.clicked.connect(self.saveToConfig)
        layout.addWidget(self.btnSave, 11, 0, 1, 2)

        self.btnLoad = QtWidgets.QPushButton("Load from Config")
        self.btnLoad.clicked.connect(self.loadFromConfig)
        layout.addWidget(self.btnLoad, 11, 3, 1, 2)

        self.btnLoadDefaults = QtWidgets.QPushButton("Reset to Defaults")
        self.btnLoadDefaults.clicked.connect(self.defaultValues)
        layout.addWidget(self.btnLoadDefaults, 11, 6, 1, 2)

        return layout


    @Slot()
    def defaultValues(self):
        self.fromDict({})

    @Slot()
    def saveToConfig(self):
        Config.inferConfig[self.configKey] = self.toDict()

    @Slot()
    def loadFromConfig(self):
        self.fromDict( Config.inferConfig.get(self.configKey, {}) )

    
    def fromDict(self, settings: dict):
        self.tokensContext.setValue(settings.get("n_ctx", 32768))
        self.gpuLayers.setValue(settings.get("n_gpu_layers", -1))

        self.tokensMax.setValue(settings.get("max_tokens", 1000))
        self.temperature.setValue(settings.get("temperature", 0.1))
        self.topP.setValue(settings.get("top_p", 0.95))
        self.topK.setValue(settings.get("top_k", 40))
        self.minP.setValue(settings.get("min_p", 0.05))
        self.typicalP.setValue(settings.get("typical_p", 1.0))

        self.presencePenalty.setValue(settings.get("presence_penalty", 0.0))
        self.freqPenalty.setValue(settings.get("frequency_penalty", 0.0))
        self.repeatPenalty.setValue(settings.get("repeat_penalty", 1.05))

        self.microstatMode.setValue(settings.get("mirostat_mode", 0))
        self.microstatTau.setValue(settings.get("mirostat_tau", 5.0))
        self.microstatEta.setValue(settings.get("mirostat_eta", 0.1))

        self.tfsZ.setValue(settings.get("tfs_z", 1.0))


    def toDict(self):
        return {
            "n_ctx": self.tokensContext.value(),
            "n_gpu_layers": self.gpuLayers.value(),

            "max_tokens": self.tokensMax.value(),
            "temperature": self.temperature.value(),
            "top_p": self.topP.value(),
            "top_k": self.topK.value(),
            "min_p": self.minP.value(),
            "typical_p": self.typicalP.value(),

            "presence_penalty": self.presencePenalty.value(),
            "frequency_penalty": self.freqPenalty.value(),
            "repeat_penalty": self.repeatPenalty.value(),

            "mirostat_mode": self.microstatMode.value(),
            "mirostat_tau": self.microstatTau.value(),
            "mirostat_eta": self.microstatEta.value(),

            "tfs_z": self.tfsZ.value()
        }
