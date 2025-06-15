from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, QSignalBlocker
from config import Config
from infer.inference_proc import InferenceProcess
from infer.inference_settings import  InferencePresetWidget
from infer.tag_settings import TagPresetWidget
from infer.prompt import PromptWidget, PromptsHighlighter
from lib import qtlib
from lib.captionfile import CaptionFile, FileTypeSelector
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchInferenceTask, BatchTaskHandler, BatchUtil
from .batch_log import BatchLog


CAPTION_OVERWRITE_MODE_ALL     = "all"
CAPTION_OVERWRITE_MODE_MISSING = "missing"


class BatchCaption(QtWidgets.QWidget):
    def __init__(self, tab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler(bars, "Caption", self.createTask)

        self.inferSettings = InferencePresetWidget()
        self.tagSettings = TagPresetWidget()

        self.captionGroup = self._buildCaptionSettings()
        self.tagGroup = self._buildTagSettings()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.captionGroup)
        layout.addWidget(self.tagGroup)
        layout.addWidget(self.taskHandler.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()


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


    def createTask(self) -> BatchInferenceTask | None:
        if not self._confirmStart():
            return None

        log = self.logWidget.addEntry("Caption")
        task = BatchCaptionTask(log, self.tab.filelist)

        if self.captionGroup.isChecked():
            storeName = self.destCaption.name.strip()
            rounds = self.spinRounds.value()
            task.prompts = self.promptWidget.getParsedPrompts(storeName, rounds)

            task.systemPrompt  = self.promptWidget.systemPrompt.strip()
            task.config        = self.inferSettings.getInferenceConfig()
            task.overwriteMode = self.cboOverwriteMode.currentData()
            task.storePrompts  = self.chkStorePrompts.isChecked()
            task.stripAround   = self.chkStripAround.isChecked()
            task.stripMulti    = self.chkStripMulti.isChecked()

        if self.tagGroup.isChecked():
            task.tagConfig = self.tagSettings.getInferenceConfig()
            task.tagName = self.destTag.name.strip()
            task.tagSkipExisting = self.chkTagSkipExisting.isChecked()

        return task



class BatchCaptionTask(BatchInferenceTask):
    def __init__(self, log, filelist):
        super().__init__("caption", log, filelist)
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
        self.varParser = None
        self.writeKeys = None


    def runPrepare(self, proc: InferenceProcess):
        self.doCaption = self.prompts is not None
        self.doTag = self.tagConfig is not None

        models = []

        if self.doCaption:
            models.append("caption")
            proc.setupCaption(self.config)

            self.writeKeys = {k for conv in self.prompts for k in conv.keys() if not k.startswith('?')}

            self.varParser = TemplateVariableParser()
            self.varParser.stripAround = self.stripAround
            self.varParser.stripMultiWhitespace = self.stripMulti

        if self.doTag:
            models.append("tag")
            proc.setupTag(self.tagConfig)
            if not self.tagName:
                self.tagName = "tags"

        modelsText = " and ".join(models)
        self.signals.progressMessage.emit(f"Loading {modelsText} model ...")


    def runCheckFile(self, imgFile: str, proc: InferenceProcess) -> Callable | None:
        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Failed to load captions from {captionFile.jsonPath}")
            return None

        if self.checkCaption(captionFile):
            doCaption = True
            prompts = self.parsePrompts(imgFile, captionFile)
        else:
            doCaption = False
            prompts = None

        doTag = self.checkTag(captionFile)

        if not (doCaption or doTag):
            return None

        def queue():
            if doCaption:
                proc.caption(imgFile, prompts, self.systemPrompt)
            if doTag:
                proc.tag(imgFile)
        return queue

    def checkCaption(self, captionFile: CaptionFile) -> set:
        if not self.doCaption:
            return set()

        writeKeys = set(self.writeKeys)
        if self.overwriteMode == CAPTION_OVERWRITE_MODE_MISSING:
            writeKeys.difference_update(captionFile.captions.keys())
        return writeKeys

    def checkTag(self, captionFile: CaptionFile) -> bool:
        return self.doTag and not (self.tagSkipExisting and captionFile.getTags(self.tagName))


    def runProcessFile(self, imgFile: str, results: list) -> str | None:
        if not results:
            return None

        captionFile = CaptionFile(imgFile)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            self.log(f"WARNING: Failed to load captions from {captionFile.jsonPath}")
            return None

        changed = False
        it = iter(results)
        if writeKeys := self.checkCaption(captionFile):
            answers = next(it, {}).get("captions")
            changed |= self.storeCaptions(imgFile, captionFile, writeKeys, answers)
        if self.checkTag(captionFile):
            tags = next(it, {}).get("tags")
            changed |= self.storeTags(imgFile, captionFile, tags)

        if changed:
            captionFile.saveToJson()
            return captionFile.jsonPath
        return None


    def storeCaptions(self, imgFile: str, captionFile: CaptionFile, writeKeys: set, answers) -> bool:
        if not answers:
            self.log(f"WARNING: No captions returned for {imgFile}, skipping")
            return False

        prompts = self.parsePrompts(imgFile, captionFile)

        changed = False
        for name, caption in answers.items():
            if not caption:
                self.log(f"WARNING: Generated caption '{name}' is empty for {imgFile}, skipping key")
                continue
            if name not in writeKeys:
                continue

            captionFile.addCaption(name, caption)
            changed = True

            if self.storePrompts:
                prompt = next((conv[name] for conv in prompts if name in conv), None)
                captionFile.addPrompt(name, prompt)

        return changed

    def storeTags(self, imgFile: str, captionFile: CaptionFile, tags) -> bool:
        if not tags:
            self.log(f"WARNING: No tags returned for {imgFile}, skipping")
            return False

        captionFile.addTags(self.tagName, tags)
        return True


    def parsePrompts(self, imgFile: str, captionFile: CaptionFile) -> list[dict]:
        self.varParser.setup(imgFile, captionFile)

        prompts = list()
        missingVars = set()
        for conv in self.prompts:
            prompts.append( {name: self.varParser.parse(prompt) for name, prompt in conv.items()} )
            missingVars.update(self.varParser.missingVars)

        if missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(missingVars)}")

        return prompts
