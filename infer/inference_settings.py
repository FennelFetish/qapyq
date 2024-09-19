from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
import superqt, copy
from config import Config


class InferenceSettingsWidget(superqt.QCollapsible):
    TITLE      = "Sample Settings"

    def __init__(self):
        super().__init__(InferenceSettingsWidget.TITLE)
        self.layout().setContentsMargins(6, 4, 6, 0)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.Base)
        self.setStyleSheet("QCollapsible{border: 2px groove " + winColor.name() + "; border-radius: 3px}")

        layout = self._build()
        layout.setContentsMargins(0, 0, 0, 6)

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

        self._buildFirstRow(layout, QtWidgets.QLabel("Max Tokens:"), self.tokensMax)

        row = 1
        layout.setRowMinimumHeight(row, spacerHeight)

        row += 1
        self.temperature = QtWidgets.QDoubleSpinBox()
        self.temperature.setRange(0.0, 5.0)
        self.temperature.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Temperature:"), row, 0)
        layout.addWidget(self.temperature, row, 1)

        self.topK = QtWidgets.QSpinBox()
        self.topK.setRange(0, 200)
        self.topK.setSingleStep(5)
        layout.addWidget(QtWidgets.QLabel("Top K:"), row, 3)
        layout.addWidget(self.topK, row, 4)

        row += 1
        self.minP = QtWidgets.QDoubleSpinBox()
        self.minP.setRange(0.0, 1.0)
        self.minP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Min P:"), row, 0)
        layout.addWidget(self.minP, row, 1)

        self.topP = QtWidgets.QDoubleSpinBox()
        self.topP.setRange(0.0, 1.0)
        self.topP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Top P:"), row, 3)
        layout.addWidget(self.topP, row, 4)

        self.typicalP = QtWidgets.QDoubleSpinBox()
        self.typicalP.setRange(0.0, 1.0)
        self.typicalP.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Typical P:"), row, 6)
        layout.addWidget(self.typicalP, row, 7)

        row += 1
        layout.setRowMinimumHeight(row, spacerHeight)

        row += 1
        self.freqPenalty = QtWidgets.QDoubleSpinBox()
        self.freqPenalty.setRange(-2.0, 2.0)
        self.freqPenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Freqency Penalty:"), row, 0)
        layout.addWidget(self.freqPenalty, row, 1)

        self.presencePenalty = QtWidgets.QDoubleSpinBox()
        self.presencePenalty.setRange(-2.0, 2.0)
        self.presencePenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Presence Penalty:"), row, 3)
        layout.addWidget(self.presencePenalty, row, 4)

        self.repeatPenalty = QtWidgets.QDoubleSpinBox()
        self.repeatPenalty.setRange(1.0, 3.0)
        self.repeatPenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Repetition Penalty:"), row, 6)
        layout.addWidget(self.repeatPenalty, row, 7)

        row += 1
        self.microstatMode = QtWidgets.QSpinBox()
        self.microstatMode.setRange(0, 2)
        layout.addWidget(QtWidgets.QLabel("Microstat Mode:"), row, 0)
        layout.addWidget(self.microstatMode, row, 1)

        self.microstatTau = QtWidgets.QDoubleSpinBox()
        self.microstatTau.setRange(0.0, 20.0)
        self.microstatTau.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Microstat Tau:"), row, 3)
        layout.addWidget(self.microstatTau, row, 4)

        self.microstatEta = QtWidgets.QDoubleSpinBox()
        self.microstatEta.setRange(0.0, 1.0)
        self.microstatEta.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Microstat Eta:"), row, 6)
        layout.addWidget(self.microstatEta, row, 7)

        row += 1
        self.tfsZ = QtWidgets.QDoubleSpinBox()
        self.tfsZ.setRange(0.0, 1.0)
        self.tfsZ.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("TFS Z:"), row, 0)
        layout.addWidget(self.tfsZ, row, 1)

        row += 1
        layout.setRowMinimumHeight(row, spacerHeight)

        row += 1
        self._buildButtons(layout, row)

        self.btnLoadDefaults = QtWidgets.QPushButton("Reset to Defaults")
        self.btnLoadDefaults.clicked.connect(self.setDefaultValues)
        layout.addWidget(self.btnLoadDefaults, row, 6, 1, 2)

        return layout

    def _buildFirstRow(self, layout, lblTokensMax, tokensMax):
        layout.addWidget(lblTokensMax, 0, 0)
        layout.addWidget(tokensMax, 0, 1)

    def _buildButtons(self, layout, row: int):
        pass


    @Slot()
    def setDefaultValues(self):
        self.fromDict({})


    def fromDict(self, settings: dict):
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



# ModelSettingsWindow depends on InferenceSettingsWidget above
from .model_settings import ModelSettingsWindow

class InferencePresetWidget(InferenceSettingsWidget):
    def __init__(self, configAttr="inferCaptionPresets"):
        super().__init__()
        self.configAttr = configAttr

        selectedPreset = Config.inferSelectedPresets.get(configAttr)
        self.reloadPresetList(selectedPreset)

        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)


    def _buildFirstRow(self, layout, lblTokensMax, tokensMax):
        lblPreset = QtWidgets.QLabel("<a href='model_settings'>Preset</a>:")
        lblPreset.linkActivated.connect(self.showModelSettings)

        layout.addWidget(lblPreset, 0, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.currentTextChanged.connect(self._onPresetChanged)
        layout.addWidget(self.preset, 0, 1)

        layout.addWidget(lblTokensMax, 0, 3)
        layout.addWidget(tokensMax, 0, 4)

    def _buildButtons(self, layout, row: int):
        self.btnSave = QtWidgets.QPushButton("Save to Preset")
        self.btnSave.clicked.connect(self.saveToConfig)
        layout.addWidget(self.btnSave, row, 0, 1, 2)

        self.btnLoad = QtWidgets.QPushButton("Load from Preset")
        self.btnLoad.clicked.connect(self.loadFromConfig)
        layout.addWidget(self.btnLoad, row, 3, 1, 2)


    @Slot()
    def showModelSettings(self, link):
        ModelSettingsWindow.openInstance(self)

    def updateTitle(self, name):
        title = InferenceSettingsWidget.TITLE
        if name:
            title += f": {name}"
        self.setText(title)


    def reloadPresetList(self, selectName: str = None):
        self.preset.clear()

        presets: dict = getattr(Config, self.configAttr)
        for name in sorted(presets.keys()):
            self.preset.addItem(name)
        
        if selectName:
            index = self.preset.findText(selectName)
        elif self.preset.count() > 0:
            index = 0
        else:
            self.setDefaultValues()
            index = -1
        
        self.preset.setCurrentIndex(index)


    @Slot()
    def _onPresetChanged(self, name):
        self.updateTitle(name)
        self.loadFromConfig()
        Config.inferSelectedPresets[self.configAttr] = name

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.configAttr:
            try:
                currentName = self.preset.currentText()
                self.preset.blockSignals(True)
                self.reloadPresetList(currentName)
            finally:
                self.preset.blockSignals(False)

            self.updateTitle( self.preset.currentText() )


    @Slot()
    def loadFromConfig(self):
        empty    = {}
        presets: dict  = getattr(Config, self.configAttr, empty)
        preset: dict   = presets.get(self.preset.currentText(), empty)
        settings: dict = preset.get(Config.INFER_PRESET_SAMPLECFG_KEY, empty)
        self.fromDict(settings)

    @Slot()
    def saveToConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText())
        if preset != None:
            preset[Config.INFER_PRESET_SAMPLECFG_KEY] = self.toDict()


    def getInferenceConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText(), {})
        preset = copy.deepcopy(preset)
        preset[Config.INFER_PRESET_SAMPLECFG_KEY] = self.toDict()
        return preset
