from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal, QObject, QSignalBlocker
from config import Config
from lib import qtlib
from lib.colorlib import ColorCharFormats
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from ui.autocomplete import TemplateTextEdit, AutoCompleteSource


class PromptSettingsSignals(QObject):
    presetListUpdated = Signal(str)


class PromptWidget(QtWidgets.QWidget):
    signals = PromptSettingsSignals()

    refreshPreviewClicked = Signal()


    def __init__(
        self,
        presetsAttr: str,
        defaultAttr: str,
        autoCompleteSources: list[AutoCompleteSource],
        showSystemPrompt: bool = True,
        parser: TemplateVariableParser | None = None
    ):
        super().__init__()
        self.presetsAttr = presetsAttr
        self.defaultAttr = defaultAttr

        self.parser = parser or TemplateVariableParser()
        self._highlighter = VariableHighlighter()

        self.setLayout(self._build(autoCompleteSources, showSystemPrompt))

        selectedPreset = Config.inferSelectedPresets.get(self.presetsAttr)
        self.reloadPresetList(selectedPreset)

        self.signals.presetListUpdated.connect(self._onPresetListChanged)


    def _build(self, autoCompleteSources: list[AutoCompleteSource], showSystemPrompt: bool):
        self.splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        self.splitter.setHandleWidth(8)

        presetLayout = self._buildPresetRow()

        # System prompt row
        self.lblSystemPrompt = QtWidgets.QLabel("System Prompt:")
        self.txtSystemPrompt = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtSystemPrompt)

        if showSystemPrompt:
            self._addSplitterRow(self.txtSystemPrompt, self.lblSystemPrompt)

        # Prompt row
        self.lblPrompts = QtWidgets.QLabel("Prompt Template:")
        self.txtPrompts = TemplateTextEdit(autoCompleteSources)
        qtlib.setMonospace(self.txtPrompts)
        self._addSplitterRow(self.txtPrompts, self.lblPrompts)

        # Preview row
        previewLayout = QtWidgets.QVBoxLayout()
        previewLayout.setContentsMargins(0, 0, 0, 0)
        previewLayout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lblPreview = QtWidgets.QLabel("Prompt Preview:")
        self.lblPreview.setMinimumWidth(Config.batchWinLegendWidth)
        previewLayout.addWidget(self.lblPreview)

        self.btnRefreshPreview = QtWidgets.QPushButton("Refresh")
        self.btnRefreshPreview.setMaximumHeight(22)
        self.btnRefreshPreview.clicked.connect(self.refreshPreviewClicked.emit)
        previewLayout.addWidget(self.btnRefreshPreview)

        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        self.txtPreview.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setShowWhitespace(self.txtPreview)

        self.previewWidget = self._addSplitterRow(self.txtPreview, None, previewLayout)

        # Compose main widget layout
        stretchFactors = (1, 4, 3) if showSystemPrompt else (4, 3)
        for i, stretch in enumerate(stretchFactors):
            self.splitter.setStretchFactor(i, stretch)

        mainLayout = QtWidgets.QVBoxLayout()
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addLayout(presetLayout)
        mainLayout.addWidget(self.splitter)
        return mainLayout

    def _buildPresetRow(self) -> QtWidgets.QLayout:
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(1, 1)

        self.lblPreset = QtWidgets.QLabel("Prompt Preset:")
        self.lblPreset.setMinimumWidth(Config.batchWinLegendWidth)
        layout.addWidget(self.lblPreset, 0, 0)

        self.preset = QtWidgets.QComboBox()
        self.preset.setEditable(True)
        self.preset.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.preset.editTextChanged.connect(self._onPresetNameEdited)
        self.preset.currentIndexChanged.connect(self.loadPreset)
        layout.addWidget(self.preset, 0, 1)

        self.btnSave = QtWidgets.QPushButton("Create")
        self.btnSave.setEnabled(False)
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, 0, 2)

        self.btnDelete = QtWidgets.QPushButton("Delete")
        self.btnDelete.setEnabled(False)
        self.btnDelete.clicked.connect(self.deletePreset)
        layout.addWidget(self.btnDelete, 0, 3)

        return layout

    def _addSplitterRow(self, widget: QtWidgets.QWidget, label: QtWidgets.QLabel | None, labelLayout: QtWidgets.QLayout | None = None) -> QtWidgets.QWidget:
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        if label:
            label.setMinimumWidth(Config.batchWinLegendWidth)
            layout.addWidget(label, 0, Qt.AlignmentFlag.AlignTop)
        else:
            layout.addLayout(labelLayout, 0)

        layout.addWidget(widget, 1)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.splitter.addWidget(widget)
        return widget


    def connectDefaultPreviewUpdate(self, promptSeperators: bool = True):
        self.txtPrompts.textChanged.connect(lambda: self.updatePreview(promptSeperators))

    def setPreviewVisible(self, visible: bool):
        parented = self.previewWidget.parent() is not None
        if parented == visible:
            return

        if visible:
            sizes = self.splitter.sizes()
            self.splitter.addWidget(self.previewWidget)
            if any(s > 10 for s in sizes):
                self.splitter.setSizes(sizes + [sizes[-1]//2])
        else:
            self.previewWidget.setParent(None)

    def updatePreview(self, promptSeperators: bool = True, disabledColors: bool = False) -> bool:
        text = self.prompts
        preview, varPositions = self.parser.parseWithPositions(text)
        self.txtPreview.setPlainText(preview)

        with QSignalBlocker(self.txtPrompts):
            self._highlighter.highlight(self.txtPrompts, self.txtPreview, varPositions, disabledColors)

            if promptSeperators:
                PromptsHighlighter.highlightPromptSeparators(self.txtPrompts)
                PromptsHighlighter.highlightPromptSeparators(self.txtPreview)

        return len(varPositions) > 0


    @property
    def systemPrompt(self) -> str:
        return self.txtSystemPrompt.toPlainText()

    @property
    def prompts(self) -> str:
        return self.txtPrompts.toPlainText()


    def getParsedPrompts(self, defaultName: str = None, rounds: int = 1) -> list[dict[str, str]]:
        if not defaultName:
            defaultName = "caption"

        currentName: str = defaultName
        allNames = set()

        currentPrompt: list[str] = list()               # List of text lines
        currentConversation: dict[str, str] = dict()    # Ordered list of prompts, name -> prompt
        conversations: list[dict[str, str]] = list()    # Ordered list of conversations

        text = self.txtPrompts.toPlainText()
        for line in text.splitlines():
            if line.startswith("---") or line.startswith("==="):
                # New prompt
                if currentPrompt:
                    currentConversation[currentName] = "\n".join(currentPrompt)
                    currentPrompt.clear()
                    allNames.add(currentName)
                currentName = self._getPromptName(line, defaultName, allNames)

                # New conversation
                if line[0] == '=' and currentConversation:
                    conversations.append(currentConversation)
                    currentConversation = dict()
            else:
                currentPrompt.append(line)

        if currentPrompt:
            currentConversation[currentName] = "\n".join(currentPrompt)
        if currentConversation:
            conversations.append(currentConversation)

        # Empty prompt
        if not conversations:
            conversations.append({defaultName: ""})

        # Apply rounds
        conversations.extend([
            {f"{name}_round{r}": prompt for name, prompt in conv.items()}
            for r in range(2, rounds+1)
            for conv in conversations
        ])
        return conversations

    @staticmethod
    def _getPromptName(line: str, defaultName: str, usedNames: set) -> str:
        newName = line.strip("-=").strip()
        newName = newName if newName else defaultName

        name = newName
        appendNr = 2
        while name in usedNames:
            name = f"{newName}_{appendNr}"
            appendNr += 1
        return name


    def reloadPresetList(self, selectName: str | None):
        self.preset.clear()

        presets: dict = getattr(Config, self.presetsAttr)
        for name in sorted(presets.keys()):
            self.preset.addItem(name)

        if not presets:
            defaults: dict = getattr(Config, self.defaultAttr)
            self.fromDict(defaults)
            index = -1
        elif selectName != None:
            index = self.preset.findText(selectName)
        else:
            index = 0

        self.preset.setCurrentIndex(index)

    @Slot()
    def _onPresetListChanged(self, attr):
        if attr == self.presetsAttr:
            with QSignalBlocker(self.preset):
                self.reloadPresetList(self.preset.currentText())
                self._onPresetNameEdited(self.preset.currentText()) # Preset name may change during reload

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.formats = ColorCharFormats()
        self.formats.addFormat(self.formats.defaultFormat)

    # Not used
    def highlightBlock(self, text: str) -> None:
        formatIndex = self.previousBlockState()
        if formatIndex < 0:
            formatIndex = 0

        isPromptTitle = False
        isConvTitle = False
        isHidden = False

        if isPromptTitle := text.startswith("---"):
            isHidden = text.lstrip("-").lstrip().startswith("?")
            formatIndex += 1
        elif isConvTitle := text.startswith("==="):
            isHidden = text.lstrip("=").lstrip().startswith("?")
            formatIndex += 1

        self.setCurrentBlockState(formatIndex)

        format = self.formats.getFormat(formatIndex)
        ColorCharFormats.setBoldFormat(format, isPromptTitle)
        format.setFontUnderline(isConvTitle)
        format.setFontItalic(isHidden)
        self.setFormat(0, len(text), format)


    @staticmethod
    def highlightPromptSeparators(textEdit: QtWidgets.QPlainTextEdit):
        doc = textEdit.document()
        for b in range(doc.blockCount()):
            block = doc.findBlockByNumber(b)
            line = block.text()

            if line.startswith("---") or line.startswith("==="):
                format = QtGui.QTextCharFormat()
                ColorCharFormats.setBoldFormat(format)

                isHidden = line.lstrip("-=").lstrip().startswith("?")
                format.setFontItalic(isHidden)
                format.setFontUnderline(line.startswith("="))

                formatRange = QtGui.QTextLayout.FormatRange()
                formatRange.format = format
                formatRange.start  = 0
                formatRange.length = len(line)

                layout = block.layout()
                formats = layout.formats()
                formats.append(formatRange)
                layout.setFormats(formats)
