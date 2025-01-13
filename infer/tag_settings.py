from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import copy
from config import Config
from .model_settings import ModelSettingsWindow


class TagPresetWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.configAttr="inferTagPresets"

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        lblPreset = QtWidgets.QLabel("<a href='model_settings'>Tag Preset</a>:")
        lblPreset.linkActivated.connect(self.showModelSettings)
        layout.addWidget(lblPreset, 0, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.currentTextChanged.connect(self._onPresetChanged)
        layout.addWidget(self.preset, 0, 1, 1, 2)

        self.threshold = QtWidgets.QDoubleSpinBox()
        self.threshold.setRange(0.01, 1.0)
        self.threshold.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Threshold:"), 1, 0)
        layout.addWidget(self.threshold, 1, 1)

        self.setLayout(layout)

        selectedPreset = Config.inferSelectedPresets.get(self.configAttr)
        self.reloadPresetList(selectedPreset)

        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)


    def getSelectedPresetName(self) -> str:
        return self.preset.currentText()

    @Slot()
    def showModelSettings(self, link):
        ModelSettingsWindow.openInstance(self, self.configAttr, self.preset.currentText())


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
            self.fromDict({})
            index = -1
        
        self.preset.setCurrentIndex(index)

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.configAttr:
            currentName = self.preset.currentText()
            with QSignalBlocker(self.preset):
                self.reloadPresetList(currentName)

    @Slot()
    def _onPresetChanged(self, name):
        self.loadFromConfig()
        Config.inferSelectedPresets[self.configAttr] = name


    def fromDict(self, settings: dict) -> None:
        self.threshold.setValue(settings.get("threshold", 0.35))

    def toDict(self) -> dict:
        return {
            "threshold": self.threshold.value()
        }


    @Slot()
    def loadFromConfig(self):
        empty: dict    = {}
        presets: dict  = getattr(Config, self.configAttr, empty)
        preset: dict   = presets.get(self.preset.currentText(), empty)
        sampleSettings: dict = preset.get(Config.INFER_PRESET_SAMPLECFG_KEY, empty)
        self.fromDict(sampleSettings)

    def getInferenceConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText(), {})
        preset: dict = copy.deepcopy(preset)
        preset[Config.INFER_PRESET_SAMPLECFG_KEY] = self.toDict()
        return preset
