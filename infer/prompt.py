from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QObject
from config import Config
import qtlib, util


class PromptSettingsSignals(QObject):
    presetListUpdated = Signal(str)


class PromptWidget(QtWidgets.QWidget):
    signals = PromptSettingsSignals()

    def __init__(self, presetsAttr: str, defaultAttr: str):
        super().__init__()
        self.presetsAttr = presetsAttr
        self.defaultAttr = defaultAttr

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)

        row = 0
        layout.addWidget(QtWidgets.QLabel("Prompt Preset:"), row, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.setEditable(True)
        self.preset.editTextChanged.connect(self._onPresetNameEdited)
        self.preset.currentIndexChanged.connect(self.loadPreset)
        layout.addWidget(self.preset, row, 1, 1, 2)

        self.btnSave = QtWidgets.QPushButton("Create")
        self.btnSave.setEnabled(False)
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 3, Qt.AlignRight)

        self.btnDelete = QtWidgets.QPushButton("Delete")
        self.btnDelete.setEnabled(False)
        self.btnDelete.clicked.connect(self.deletePreset)
        layout.addWidget(self.btnDelete, row, 4)

        row += 1
        self.txtSystemPrompt = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtSystemPrompt)
        qtlib.setShowWhitespace(self.txtSystemPrompt)
        layout.addWidget(QtWidgets.QLabel("System Prompt:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtSystemPrompt, row, 1, 1, 4)

        row += 1
        self.lblPrompts = QtWidgets.QLabel("Prompt(s):")
        layout.addWidget(self.lblPrompts, row, 0, Qt.AlignTop)

        self.txtPrompts = QtWidgets.QTextEdit()
        qtlib.setMonospace(self.txtPrompts)
        qtlib.setShowWhitespace(self.txtPrompts)
        layout.addWidget(self.txtPrompts, row, 1, 1, 4)

        self.setLayout(layout)


        selectedPreset = Config.inferSelectedPresets.get(self.presetsAttr)
        self.reloadPresetList(selectedPreset)

        self.signals.presetListUpdated.connect(self._onPresetListChanged)

    def enableHighlighting(self):
        self.promptsHighlighter = PromptsHighlighter(self.txtPrompts)


    @property
    def systemPrompt(self) -> str:
        return self.txtSystemPrompt.toPlainText()

    @property
    def prompts(self) -> str:
        return self.txtPrompts.toPlainText()

    def getParsedPrompts(self, defaultName=None) -> dict[str, str]:
        return util.parsePrompts(self.txtPrompts.toPlainText(), defaultName)


    def reloadPresetList(self, selectName: str | None):
        self.preset.clear()

        presets: dict = getattr(Config, self.presetsAttr)
        for name in sorted(presets.keys()):
            self.preset.addItem(name)
        
        if selectName != None:
            index = self.preset.findText(selectName)
        elif self.preset.count() > 0:
            index = 0
        else:
            defaults: dict = getattr(Config, self.defaultAttr)
            self.fromDict(defaults)
            index = -1
        
        self.preset.setCurrentIndex(index)

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.presetsAttr:
            try:
                self.preset.blockSignals(True)
                self.reloadPresetList(self.preset.currentText())
                self._onPresetNameEdited(self.preset.currentText()) # Preset name may change during reload
            finally:
                self.preset.blockSignals(False)

    @Slot()
    def _onPresetNameEdited(self, text: str) -> None:
        presets: dict = getattr(Config, self.presetsAttr, None)
        if presets and text in presets:
            self.btnSave.setText("Overwrite")
            self.btnDelete.setEnabled(True)
        else:
            self.btnSave.setText("Create")
            self.btnDelete.setEnabled(False)

        self.btnSave.setEnabled(bool(text))


    @Slot()
    def loadPreset(self, index: int):
        name = self.preset.itemText(index)

        empty: dict = {}
        presets: dict = getattr(Config, self.presetsAttr, empty)
        preset: dict = presets.get(name, empty)
        self.fromDict(preset)

        Config.inferSelectedPresets[self.presetsAttr] = name
    
    @Slot()
    def savePreset(self):
        if not (name := self.preset.currentText().strip()):
            return

        presets: dict = getattr(Config, self.presetsAttr)
        newPreset = (name not in presets)
        presets[name] = self.toDict()

        if newPreset:
            self.signals.presetListUpdated.emit(self.presetsAttr)

    @Slot()
    def deletePreset(self) -> None:
        name = self.preset.currentText().strip()
        presets: dict = getattr(Config, self.presetsAttr)
        if name in presets:
            del presets[name]
            del Config.inferSelectedPresets[self.presetsAttr]
            self.signals.presetListUpdated.emit(self.presetsAttr)


    def fromDict(self, preset: dict) -> None:
        self.txtSystemPrompt.setPlainText(preset.get("system_prompt", ""))
        self.txtPrompts.setPlainText(preset.get("prompts", ""))

    def toDict(self) -> dict:
        return {
            "system_prompt": self.txtSystemPrompt.toPlainText(),
            "prompts": self.txtPrompts.toPlainText()
        }



class PromptsHighlighter(QtGui.QSyntaxHighlighter):
    SEPARATOR = "---"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.formats = qtlib.ColorCharFormats()
        self.formats.addFormat(self.formats.defaultFormat)

    def highlightBlock(self, text: str) -> None:
        formatIndex = self.previousBlockState()
        if formatIndex < 0:
            formatIndex = 0
        if isTitle := text.startswith(self.SEPARATOR):
            formatIndex += 1
        self.setCurrentBlockState(formatIndex)

        format = self.formats.getFormat(formatIndex)
        if isTitle:
            format.setFontWeight(700)
        else:
            format.setFontWeight(200)
        self.setFormat(0, len(text), format)
