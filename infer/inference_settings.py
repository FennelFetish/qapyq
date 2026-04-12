from __future__ import annotations
import superqt, copy
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSignalBlocker
from .model_settings import ModelSettingsWindow
from .backend_config import BackendTypes, BackendDef, BackendsCaption, backendDefForName
from config import Config


class InferenceSettingsWidget(superqt.QCollapsible):
    TITLE = "Sample Settings"

    def __init__(self, backends: dict[str, BackendDef]):
        super().__init__(InferenceSettingsWidget.TITLE)
        self.backends = backends

        self.layout().setContentsMargins(6, 4, 6, 0)

        winColor = QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Base)
        self.setStyleSheet("QCollapsible{border: 2px groove " + winColor.name() + "; border-radius: 3px}")

        layout = self._build()
        layout.setContentsMargins(0, 0, 0, 6)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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

        row = 0
        col = self._buildFirstRow(layout)

        self.tokensMax = QtWidgets.QSpinBox()
        self.tokensMax.setRange(10, 100000)
        self.tokensMax.setSingleStep(10)
        layout.addWidget(QtWidgets.QLabel("Max Tokens:"), row, col)
        layout.addWidget(self.tokensMax, row, col+1)

        self.lblFps = QtWidgets.QLabel("Video FPS:")
        self.fps = QtWidgets.QDoubleSpinBox()
        self.fps.setRange(1.0, 999.0)
        self.fps.setSingleStep(1.0)

        if self.backends is not BackendsCaption:
            self.lblFps.setVisible(False)
            self.fps.setVisible(False)

        layout.addWidget(self.lblFps, row, col+3)
        layout.addWidget(self.fps, row, col+4)

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

        # row += 1
        # layout.setRowMinimumHeight(row, spacerHeight)

        row += 1
        self.repeatPenalty = QtWidgets.QDoubleSpinBox()
        self.repeatPenalty.setRange(1.0, 3.0)
        self.repeatPenalty.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Repetition Penalty:"), row, 0)
        layout.addWidget(self.repeatPenalty, row, 1)

        self.lblFreqPenalty = QtWidgets.QLabel("Freqency Penalty:")
        layout.addWidget(self.lblFreqPenalty, row, 3)
        self.freqPenalty = QtWidgets.QDoubleSpinBox()
        self.freqPenalty.setRange(-2.0, 2.0)
        self.freqPenalty.setSingleStep(0.05)
        layout.addWidget(self.freqPenalty, row, 4)

        self.lblPresencePenalty = QtWidgets.QLabel("Presence Penalty:")
        layout.addWidget(self.lblPresencePenalty, row, 6)
        self.presencePenalty = QtWidgets.QDoubleSpinBox()
        self.presencePenalty.setRange(-2.0, 2.0)
        self.presencePenalty.setSingleStep(0.05)
        layout.addWidget(self.presencePenalty, row, 7)

        row += 1
        self._buildButtons(layout, row)

        self.btnLoadDefaults = QtWidgets.QPushButton("Reset to Defaults")
        self.btnLoadDefaults.clicked.connect(self.setDefaultValues)
        layout.addWidget(self.btnLoadDefaults, row, 6, 1, 2)

        return layout

    def _buildFirstRow(self, layout: QtWidgets.QGridLayout) -> int:
        return 0

    def _buildButtons(self, layout: QtWidgets.QGridLayout, row: int):
        pass


    def updateFields(self, backendDef: BackendDef | None):
        if backendDef is not None:
            supportsPenalty = (backendDef.type == BackendTypes.LLAMA_CPP)
            supportsVideo   = ("video" in backendDef.features)
        else:
            supportsPenalty = False
            supportsVideo   = False

        for widget in (self.lblFreqPenalty, self.freqPenalty, self.lblPresencePenalty, self.presencePenalty):
            widget.setEnabled(supportsPenalty)

        for widget in (self.lblFps, self.fps):
            widget.setEnabled(supportsVideo)


    @Slot()
    def setDefaultValues(self):
        self.fromDict({})

    def fromDict(self, settings: dict):
        self.tokensMax.setValue(settings.get("max_tokens", 1000))
        self.fps.setValue(settings.get("fps", 2.0))
        self.temperature.setValue(settings.get("temperature", 0.1))
        self.topP.setValue(settings.get("top_p", 0.95))
        self.topK.setValue(settings.get("top_k", 40))
        self.minP.setValue(settings.get("min_p", 0.05))
        self.typicalP.setValue(settings.get("typical_p", 1.0))

        self.repeatPenalty.setValue(settings.get("repeat_penalty", 1.05))
        self.freqPenalty.setValue(settings.get("frequency_penalty", 0.0))
        self.presencePenalty.setValue(settings.get("presence_penalty", 0.0))

    def toDict(self):
        settings = {
            "max_tokens": self.tokensMax.value(),
            "temperature": self.temperature.value(),
            "top_p": self.topP.value(),
            "top_k": self.topK.value(),
            "min_p": self.minP.value(),
            "typical_p": self.typicalP.value(),

            "repeat_penalty": self.repeatPenalty.value(),
        }

        if self.freqPenalty.isEnabled() and self.presencePenalty.isEnabled():
            settings["frequency_penalty"] = self.freqPenalty.value()
            settings["presence_penalty"] = self.presencePenalty.value()

        if self.fps.isEnabled():
            settings["fps"] = self.fps.value()

        return settings



class InferencePresetWidget(InferenceSettingsWidget):
    def __init__(self, configAttr="inferCaptionPresets", backends: dict[str, BackendDef] = BackendsCaption):
        super().__init__(backends)
        self.configAttr = configAttr

        selectedPreset = Config.inferSelectedPresets.get(configAttr)
        self.reloadPresetList(selectedPreset)

        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)


    def _buildFirstRow(self, layout: QtWidgets.QGridLayout) -> int:
        lblPreset = QtWidgets.QLabel("<a href='model_settings'>Preset</a>:")
        lblPreset.linkActivated.connect(self.showModelSettings)
        layout.addWidget(lblPreset, 0, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.currentTextChanged.connect(self._onPresetChanged)
        layout.addWidget(self.preset, 0, 1)
        return 3

    def _buildButtons(self, layout: QtWidgets.QGridLayout, row: int):
        self.btnSave = QtWidgets.QPushButton("Save to Preset")
        self.btnSave.clicked.connect(self.saveToConfig)
        layout.addWidget(self.btnSave, row, 0, 1, 2)

        self.btnLoad = QtWidgets.QPushButton("Load from Preset")
        self.btnLoad.clicked.connect(self.loadFromConfig)
        layout.addWidget(self.btnLoad, row, 3, 1, 2)


    def getSelectedPresetName(self) -> str:
        return self.preset.currentText()

    @Slot(str)
    def showModelSettings(self, link: str):
        ModelSettingsWindow.openInstance(self, self.configAttr, self.preset.currentText())

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


    @Slot(str)
    def _onPresetChanged(self, name: str):
        self.updateTitle(name)
        self.loadFromConfig()
        Config.inferSelectedPresets[self.configAttr] = name

    @Slot(str)
    def _onPresetListChanged(self, attr: str):
        if attr == self.configAttr:
            currentName = self.preset.currentText()
            with QSignalBlocker(self.preset):
                self.reloadPresetList(currentName)
            self.updateTitle( self.preset.currentText() )


    @Slot()
    def loadFromConfig(self):
        empty = {}
        presets: dict  = getattr(Config, self.configAttr, empty)
        preset: dict   = presets.get(self.preset.currentText(), empty)
        settings: dict = preset.get(Config.INFER_PRESET_SAMPLECFG_KEY, empty)

        self.updateFields(backendDefForName(self.backends, preset["backend"]))
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

    def getRemoteInferenceConfig(self) -> RemoteInferenceConfig:
        presetName = self.preset.currentText()
        return RemoteInferenceConfig(self.configAttr, presetName, self.toDict())



class RemoteInferenceConfig:
    def __init__(self, configAttr: str, presetName: str, inferConfig: dict):
        presets: dict = getattr(Config, configAttr)

        self.defaultConfig: dict = copy.deepcopy( presets.get(presetName, {}) )
        self.defaultConfig[Config.INFER_PRESET_SAMPLECFG_KEY] = inferConfig

        self.hostConfigs = self._loadHostConfigs(presets, presetName, inferConfig)

    @staticmethod
    def _loadHostConfigs(presets: dict, presetName: str, inferConfig: dict) -> dict[str, tuple[str, dict]]:
        import re
        pattern = re.compile(rf"{presetName}\s*\[(.+)\]")
        hostConfigs = dict[str, tuple[str, dict]]()

        for name, cfg in sorted(presets.items(), key=lambda x: x[0]):
            if match := pattern.match(name):
                hostName = match.group(1)
                cfg = copy.deepcopy(cfg)
                cfg[Config.INFER_PRESET_SAMPLECFG_KEY] = inferConfig
                hostConfigs[hostName.strip()] = (name, cfg)

        return hostConfigs

    def getHostConfig(self, hostName: str) -> dict:
        if configEntry := self.hostConfigs.get(hostName):
            presetName, config = configEntry
            print(f"Using preset '{presetName}' for host '{hostName}'")
            return config
        return self.defaultConfig
