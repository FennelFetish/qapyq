from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
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
            self.setDefaultValues()
            index = -1
        
        self.preset.setCurrentIndex(index)

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.configAttr:
            try:
                currentName = self.preset.currentText()
                self.preset.blockSignals(True)
                self.reloadPresetList(currentName)
            finally:
                self.preset.blockSignals(False)

    @Slot()
    def _onPresetChanged(self, name):
        self.loadFromConfig()
        Config.inferSelectedPresets[self.configAttr] = name


    @Slot()
    def loadFromConfig(self):
        empty    = {}
        presets: dict  = getattr(Config, self.configAttr, empty)
        preset: dict   = presets.get(self.preset.currentText(), empty)
        self.threshold.setValue(preset.get("threshold", 0.35))

    def getInferenceConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText(), {})
        preset = copy.deepcopy(preset)
        preset["threshold"] = self.threshold.value()
        return preset
