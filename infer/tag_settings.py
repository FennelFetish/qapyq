from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import copy, superqt
from config import Config
from .model_settings import ModelSettingsWindow


class TagSettingsWidget(superqt.QCollapsible):
    TITLE = "Tag Settings"

    THRESHOLD_MODES = (
        ("Fixed Threshold", "fixed"),
        ("Adaptive Strict", "adapt_strict"),
        ("Adaptive Lax", "adapt_lax")
    )

    DEFAULT_THRESHOLD_MODE = THRESHOLD_MODES[0][1]


    def __init__(self):
        super().__init__(self.TITLE)
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnMinimumWidth(1, 100)
        layout.setColumnStretch(6, 1)

        self._buildFirstRow(layout)

        row = 1
        self.lblRating = QtWidgets.QLabel("Rating:")
        layout.addWidget(self.lblRating, row, 0)

        self.chkIncludeRating = QtWidgets.QCheckBox("Include")
        self.chkIncludeRating.setChecked(False)
        layout.addWidget(self.chkIncludeRating, row, 1)

        row += 1
        self.lblChars = QtWidgets.QLabel("Characters:")
        layout.addWidget(self.lblChars, row, 0)

        self.chkIncludeChar = QtWidgets.QCheckBox("Include")
        self.chkIncludeChar.setChecked(True)
        layout.addWidget(self.chkIncludeChar, row, 1)

        self.lblCharsThreshold = QtWidgets.QLabel("Threshold:")
        layout.addWidget(self.lblCharsThreshold, row, 2)

        self.spinCharThreshold = QtWidgets.QDoubleSpinBox()
        self.spinCharThreshold.setRange(0.01, 1.0)
        self.spinCharThreshold.setSingleStep(0.05)
        layout.addWidget(self.spinCharThreshold, row, 3)

        self.cboCharThresholdMode = QtWidgets.QComboBox()
        for name, mode in self.THRESHOLD_MODES:
            self.cboCharThresholdMode.addItem(name, mode)
        layout.addWidget(self.cboCharThresholdMode, row, 4)

        self.chkCharOnlyMax = QtWidgets.QCheckBox("Only Best Match")
        self.chkCharOnlyMax.setChecked(True)
        self.chkCharOnlyMax.toggled.connect(self._onCharOnlyMaxToggled)
        layout.addWidget(self.chkCharOnlyMax, row, 5)

        row += 1
        layout.addWidget(QtWidgets.QLabel("General Tags:"), row, 0)
        self.chkIncludeGeneral = QtWidgets.QCheckBox("Include")
        self.chkIncludeGeneral.setChecked(True)
        layout.addWidget(self.chkIncludeGeneral, row, 1)

        layout.addWidget(QtWidgets.QLabel("Threshold:"), row, 2)
        self.spinThreshold = QtWidgets.QDoubleSpinBox()
        self.spinThreshold.setRange(0.01, 1.0)
        self.spinThreshold.setSingleStep(0.05)
        layout.addWidget(self.spinThreshold, row, 3)

        self.cboThresholdMode = QtWidgets.QComboBox()
        for name, mode in self.THRESHOLD_MODES:
            self.cboThresholdMode.addItem(name, mode)
        layout.addWidget(self.cboThresholdMode, row, 4)
        self._onCharOnlyMaxToggled()

        row += 1
        layout.addLayout(self._buildButtons(), row, 0, 1, 6)

        return layout

    def _buildFirstRow(self, layout: QtWidgets.QGridLayout):
        pass

    def _buildButtons(self) -> QtWidgets.QGridLayout:
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.btnLoadDefaults = QtWidgets.QPushButton("Reset to Defaults")
        self.btnLoadDefaults.clicked.connect(self.setDefaultValues)
        layout.addWidget(self.btnLoadDefaults, 0, 2)

        return layout


    @Slot()
    def _onCharOnlyMaxToggled(self):
        if self.chkCharOnlyMax.isChecked():
            self.cboCharThresholdMode.setCurrentIndex(0)
            self.cboCharThresholdMode.setEnabled(False)
        else:
            self.cboCharThresholdMode.setEnabled(True)


    def setSupportsRatingAndChars(self, support: bool):
        widgets = (
            self.lblRating, self.chkIncludeRating, self.lblChars, self.chkIncludeChar, self.lblCharsThreshold,
            self.spinCharThreshold, self.cboCharThresholdMode, self.chkCharOnlyMax, self.chkIncludeGeneral
        )

        for widget in widgets:
            widget.setEnabled(support)
        self._onCharOnlyMaxToggled()


    @Slot()
    def setDefaultValues(self):
        if self.chkIncludeRating.isEnabled() and self.chkIncludeChar.isEnabled():
            self.fromDict({"include_ratings": False, "include_characters": True})
        else:
            self.fromDict({})

    def fromDict(self, settings: dict) -> None:
        self.chkIncludeRating.setChecked(settings.get("include_ratings", False))

        self.chkIncludeChar.setChecked(settings.get("include_characters", True))
        self.spinCharThreshold.setValue(settings.get("character_threshold", 0.85))
        charThresholdMode = settings.get("character_threshold_mode", self.DEFAULT_THRESHOLD_MODE)
        self.cboCharThresholdMode.setCurrentIndex(self.cboCharThresholdMode.findData(charThresholdMode))
        self.chkCharOnlyMax.setChecked(settings.get("character_only_max", True))

        self.chkIncludeGeneral.setChecked(settings.get("include_general", True))
        self.spinThreshold.setValue(settings.get("threshold", 0.35))
        thresholdmode = settings.get("threshold_mode", self.DEFAULT_THRESHOLD_MODE)
        self.cboThresholdMode.setCurrentIndex(self.cboThresholdMode.findData(thresholdmode))

        supportsRatingAndChars = ("include_ratings" in settings) and ("include_characters" in settings)
        self.setSupportsRatingAndChars(supportsRatingAndChars)

    def toDict(self) -> dict:
        settings = {
            "include_general": self.chkIncludeGeneral.isChecked(),
            "threshold": self.spinThreshold.value(),
            "threshold_mode": self.cboThresholdMode.currentData()
        }

        if self.chkIncludeRating.isEnabled() and self.chkIncludeChar.isEnabled():
            settings.update({
                "include_ratings": self.chkIncludeRating.isChecked(),

                "include_characters": self.chkIncludeChar.isChecked(),
                "character_only_max": self.chkCharOnlyMax.isChecked(),
                "character_threshold": self.spinCharThreshold.value(),
                "character_threshold_mode": self.cboCharThresholdMode.currentData(),
            })

        return settings



class TagPresetWidget(TagSettingsWidget):
    def __init__(self):
        super().__init__()
        self.configAttr="inferTagPresets"

        selectedPreset = Config.inferSelectedPresets.get(self.configAttr)
        self.reloadPresetList(selectedPreset)

        ModelSettingsWindow.signals.presetListUpdated.connect(self._onPresetListChanged)


    def _buildFirstRow(self, layout: QtWidgets.QGridLayout):
        lblPreset = QtWidgets.QLabel("<a href='model_settings'>Tag Preset</a>:")
        lblPreset.linkActivated.connect(self.showModelSettings)
        layout.addWidget(lblPreset, 0, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.currentTextChanged.connect(self._onPresetChanged)
        layout.addWidget(self.preset, 0, 1, 1, 3)

    def _buildButtons(self) -> QtWidgets.QGridLayout:
        layout = super()._buildButtons()

        self.btnSave = QtWidgets.QPushButton("Save to Preset")
        self.btnSave.clicked.connect(self.saveToConfig)
        layout.addWidget(self.btnSave, 0, 0)

        self.btnLoad = QtWidgets.QPushButton("Load from Preset")
        self.btnLoad.clicked.connect(self.loadFromConfig)
        layout.addWidget(self.btnLoad, 0, 1)

        return layout


    def getSelectedPresetName(self) -> str:
        return self.preset.currentText()

    @Slot()
    def showModelSettings(self, link):
        ModelSettingsWindow.openInstance(self, self.configAttr, self.preset.currentText())

    def updateTitle(self, name):
        title = self.TITLE
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
    def _onPresetListChanged(self, attr):
        if attr == self.configAttr:
            currentName = self.preset.currentText()
            with QSignalBlocker(self.preset):
                self.reloadPresetList(currentName)

    @Slot()
    def _onPresetChanged(self, name):
        self.updateTitle(name)
        self.loadFromConfig()
        Config.inferSelectedPresets[self.configAttr] = name


    @Slot()
    def loadFromConfig(self):
        empty: dict    = {}
        presets: dict  = getattr(Config, self.configAttr, empty)
        preset: dict   = presets.get(self.preset.currentText(), empty)
        sampleSettings: dict = preset.get(Config.INFER_PRESET_SAMPLECFG_KEY, empty)
        self.fromDict(sampleSettings)

    @Slot()
    def saveToConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText())
        if preset != None:
            preset[Config.INFER_PRESET_SAMPLECFG_KEY] = self.toDict()


    def getInferenceConfig(self):
        presets: dict = getattr(Config, self.configAttr)
        preset: dict = presets.get(self.preset.currentText(), {})
        preset: dict = copy.deepcopy(preset)
        preset[Config.INFER_PRESET_SAMPLECFG_KEY] = self.toDict()
        return preset
