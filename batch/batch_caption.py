from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
from config import Config
from infer import Inference, InferencePresetWidget, TagPresetWidget, PromptWidget, PromptsHighlighter
from lib import qtlib
from lib.captionfile import CaptionFile, FileTypeSelector
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchTask, BatchSignalHandler, BatchUtil


CAPTION_OVERWRITE_MODE_ALL     = "all"
CAPTION_OVERWRITE_MODE_MISSING = "missing"


class BatchCaption(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.inferSettings = InferencePresetWidget()
        self.tagSettings = TagPresetWidget()

        self.captionGroup = self._buildCaptionSettings()
        self.tagGroup = self._buildTagSettings()

        self.btnStart = QtWidgets.QPushButton("Start Batch Caption")
        self.btnStart.clicked.connect(self.startStop)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.captionGroup)
        layout.addWidget(self.tagGroup)
        layout.addWidget(self.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()

        self._task = None
        self._taskSignalHandler = None


    def _buildCaptionSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        row = 0
        self.promptWidget = PromptWidget("promptCaptionPresets", "promptCaptionDefault")
        qtlib.setTextEditHeight(self.promptWidget.txtSystemPrompt, 5, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 10, "min")
        self.promptWidget.lblPrompts.setText("Prompt(s) Template:")
        self.promptWidget.txtPrompts.textChanged.connect(self._updatePreview)
        self.promptWidget.layout().setRowStretch(1, 1)
        self.promptWidget.layout().setRowStretch(2, 2)
        layout.addWidget(self.promptWidget, row, 0, 1, 4)
        layout.setRowStretch(row, 3)

        row += 1
        self.txtPromptPreview = QtWidgets.QPlainTextEdit()
        self.txtPromptPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPromptPreview)
        qtlib.setTextEditHeight(self.txtPromptPreview, 5, "min")
        qtlib.setShowWhitespace(self.txtPromptPreview)
        layout.addWidget(QtWidgets.QLabel("Prompt(s) Preview:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPromptPreview, row, 1, 1, 3)
        layout.setRowStretch(row, 4)

        row += 1
        self.chkStripAround = QtWidgets.QCheckBox("Surrounding whitespace")
        self.chkStripAround.setChecked(True)
        self.chkStripAround.checkStateChanged.connect(self._updateParser)

        self.chkStripMulti = QtWidgets.QCheckBox("Repeating whitespace")
        self.chkStripMulti.setChecked(False)
        self.chkStripMulti.checkStateChanged.connect(self._updateParser)

        layout.addWidget(QtWidgets.QLabel("Strip:"), row, 0)
        layout.addWidget(self.chkStripAround, row, 1)
        layout.addWidget(self.chkStripMulti, row, 2)

        row += 1
        self.destCaption = FileTypeSelector()
        self.destCaption.setFixedType(FileTypeSelector.TYPE_CAPTIONS)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), row, 0)
        layout.addLayout(self.destCaption, row, 1)

        self.cboOverwriteMode = QtWidgets.QComboBox()
        self.cboOverwriteMode.addItem("Overwrite all keys", CAPTION_OVERWRITE_MODE_ALL)
        self.cboOverwriteMode.addItem("Only write missing keys", CAPTION_OVERWRITE_MODE_MISSING)
        layout.addWidget(self.cboOverwriteMode, row, 2)

        self.chkStorePrompts = QtWidgets.QCheckBox("Store Prompts")
        layout.addWidget(self.chkStorePrompts, row, 3)

        row += 1
        self.spinRounds = QtWidgets.QSpinBox()
        self.spinRounds.setRange(1, 100)
        self.spinRounds.setValue(1)
        layout.addWidget(QtWidgets.QLabel("Rounds:"), row, 0)
        layout.addWidget(self.spinRounds, row, 1)

        row += 1
        layout.addWidget(self.inferSettings, row, 0, 1, 4)

        groupBox = QtWidgets.QGroupBox("Generate Captions")
        groupBox.setCheckable(True)
        groupBox.setLayout(layout)
        return groupBox


    def _buildTagSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        layout.addWidget(self.tagSettings, 0, 0, 1, 2)

        self.destTag = FileTypeSelector()
        self.destTag.setFixedType(FileTypeSelector.TYPE_TAGS)
        layout.addWidget(QtWidgets.QLabel("Storage key:"), 1, 0)
        layout.addLayout(self.destTag, 1, 1)

        self.chkTagSkipExisting = QtWidgets.QCheckBox("Skip file if key exists")
        layout.addWidget(self.chkTagSkipExisting, 1, 2)

        groupBox = QtWidgets.QGroupBox("Generate Tags")
        groupBox.setCheckable(True)
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self._parser = TemplateVariableParser(currentFile)
        self._updateParser()

    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    def _updatePreview(self):
        text = self.promptWidget.prompts
        preview, varPositions = self._parser.parseWithPositions(text)
        self.txtPromptPreview.setPlainText(preview)

        with QSignalBlocker(self.promptWidget.txtPrompts):
            self._highlighter.highlight(self.promptWidget.txtPrompts, self.txtPromptPreview, varPositions)
            PromptsHighlighter.highlightPromptSeparators(self.promptWidget.txtPrompts)
            PromptsHighlighter.highlightPromptSeparators(self.txtPromptPreview)


    def _confirmStart(self) -> bool:
        ops = []

        targetName = self.destCaption.name.strip()
        if self.captionGroup.isChecked():
            ops.append(f"Use '{self.inferSettings.getSelectedPresetName()}' to generate new Captions")

            captionKey = f"captions.{targetName}"
            captionText = f"Write the Captions to .json files [{captionKey}]"
            if self.cboOverwriteMode.currentData() == CAPTION_OVERWRITE_MODE_MISSING:
                captionText += " if the key doesn't exist"
            else:
                captionText = qtlib.htmlRed(captionText + " and overwrite the content!")
            ops.append(captionText)

        if self.chkStorePrompts.isChecked():
            ops.append(f"Store the prompt in [prompts.{targetName}]")

        if self.spinRounds.value() > 1:
            ops.append(f"Do {self.spinRounds.value()} rounds of captioning")

        if self.tagGroup.isChecked():
            ops.append(f"Use '{self.tagSettings.getSelectedPresetName()}' to generate new Tags")

            tagKey = f"tags.{self.destTag.name.strip()}"
            tagText = f"Write the Tags to .json files [{tagKey}]"
            if self.chkTagSkipExisting.isChecked():
                tagText += " if the key doesn't exist"
            else:
                tagText = qtlib.htmlRed(tagText + " and overwrite the content!")
            ops.append(tagText)

        return BatchUtil.confirmStart("Caption", self.tab.filelist.getNumFiles(), ops, self)


    @Slot()
    def startStop(self):
        if self._task:
            if BatchUtil.confirmAbort(self):
                self._task.abort()
            return

        if not self._confirmStart():
            return

        self.btnStart.setText("Abort")

        self._task = BatchCaptionTask(self.log, self.tab.filelist)

        if self.captionGroup.isChecked():
            storeName = self.destCaption.name.strip()
            rounds = self.spinRounds.value()
            self._task.prompts = self.promptWidget.getParsedPrompts(storeName, rounds)

            self._task.systemPrompt  = self.promptWidget.systemPrompt.strip()
            self._task.config        = self.inferSettings.getInferenceConfig()
            self._task.overwriteMode = self.cboOverwriteMode.currentData()
            self._task.storePrompts  = self.chkStorePrompts.isChecked()
            self._task.stripAround   = self.chkStripAround.isChecked()
            self._task.stripMulti    = self.chkStripMulti.isChecked()

        if self.tagGroup.isChecked():
            self._task.tagConfig = self.tagSettings.getInferenceConfig()
            self._task.tagName = self.destTag.name.strip()
            self._task.tagSkipExisting = self.chkTagSkipExisting.isChecked()

        self._taskSignalHandler = BatchSignalHandler(self.statusBar, self.progressBar, self._task)
        self._taskSignalHandler.finished.connect(self.taskDone)
        Inference().queueTask(self._task)

    @Slot()
    def taskDone(self):
        self.btnStart.setText("Start Batch Caption")
        self._task = None
        self._taskSignalHandler = None



class BatchCaptionTask(BatchTask):
    def __init__(self, log, filelist):
        super().__init__("caption", log, filelist, uploadImages=True)
        self.prompts      = None
        self.systemPrompt = None
        self.config       = None
        self.overwriteMode = CAPTION_OVERWRITE_MODE_ALL
        self.storePrompts: bool = False
        self.stripAround  = True
        self.stripMulti   = False

        self.tagConfig    = None
        self.tagName      = None
        self.tagSkipExisting = False

        self.doCaption = False
        self.doTag     = False
        self.inferProc = None
        self.varParser = None
        self.writeKeys = None


    def runPrepare(self):
        self.doCaption = self.prompts is not None
        self.doTag = self.tagConfig is not None

        self.inferProc = Inference().proc
        self.inferProc.start()

        if self.doCaption:
            self.signals.progressMessage.emit("Loading caption model ...")
            self.inferProc.setupCaption(self.config)
            self.writeKeys = {k for conv in self.prompts for k in conv.keys() if not k.startswith('?')}

            self.varParser = TemplateVariableParser()
            self.varParser.stripAround = self.stripAround
            self.varParser.stripMultiWhitespace = self.stripMulti

        if self.doTag:
            self.signals.progressMessage.emit("Loading tag model ...")
            self.inferProc.setupTag(self.tagConfig)
            if not self.tagName:
                self.tagName = "tags"


    def runProcessFile(self, imgFile: str) -> str:
        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Failed to load captions from {captionFile.jsonPath}")
            return None

        changed = False
        if self.doCaption:
            changed |= self.runCaption(imgFile, captionFile)
        if self.doTag:
            changed |= self.runTags(imgFile, captionFile)

        if changed:
            captionFile.saveToJson()
            return captionFile.jsonPath
        return None


    def runCaption(self, imgFile: str, captionFile: CaptionFile) -> bool:
        writeKeys = set(self.writeKeys)
        if self.overwriteMode == CAPTION_OVERWRITE_MODE_MISSING:
            for name in captionFile.captions.keys():
                writeKeys.discard(name)

        if not writeKeys:
            return False

        prompts = self.parsePrompts(imgFile, captionFile)
        answers = self.inferProc.caption(imgFile, prompts, self.systemPrompt)
        if not answers:
            self.log(f"WARNING: No captions returned for {imgFile}")
            return False

        changed = False
        for name, caption in answers.items():
            if not caption:
                self.log(f"WARNING: Caption '{name}' is empty for {imgFile}, ignoring")
                continue
            if name not in writeKeys:
                continue

            captionFile.addCaption(name, caption)
            changed = True

            if self.storePrompts:
                prompt = next((conv[name] for conv in prompts if name in conv), None)
                captionFile.addPrompt(name, prompt)

        return changed


    def runTags(self, imgFile: str, captionFile: CaptionFile) -> bool:
        if self.tagSkipExisting and captionFile.getTags(self.tagName):
            return False

        tags = self.inferProc.tag(imgFile)
        if tags:
            captionFile.addTags(self.tagName, tags)
            return True
        else:
            self.log(f"WARNING: No tags returned for {imgFile}, ignoring")
            return False


    def parsePrompts(self, imgFile: str, captionFile: CaptionFile) -> list:
        self.varParser.setup(imgFile, captionFile)

        prompts = list()
        missingVars = set()
        for conv in self.prompts:
            prompts.append( {name: self.varParser.parse(prompt) for name, prompt in conv.items()} )
            missingVars.update(self.varParser.missingVars)

        if missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(missingVars)}")

        return prompts
