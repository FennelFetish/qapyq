from typing import Callable
from PySide6 import QtWidgets
from PySide6.QtCore import QSignalBlocker, Qt, Slot
from config import Config
from infer.inference_proc import InferenceProcess
from infer.inference_settings import InferencePresetWidget
from infer.prompt import PromptWidget, PromptsHighlighter
from lib import qtlib
from lib.captionfile import CaptionFile, FileTypeSelector
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from .batch_task import BatchInferenceTask, BatchTaskHandler, BatchUtil
from .batch_log import BatchLog


TRANSFORM_OVERWRITE_MODE_ALL     = "all"
TRANSFORM_OVERWRITE_MODE_MISSING = "missing"


class BatchTransform(QtWidgets.QWidget):
    def __init__(self, tab, logWidget: BatchLog, bars):
        super().__init__()
        self.tab = tab
        self.logWidget = logWidget
        self.taskHandler = BatchTaskHandler(bars, "Transform", self.createTask)

        self.inferSettings = InferencePresetWidget("inferLLMPresets")

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildLLMSettings())
        layout.addWidget(self.taskHandler.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()


    def _buildLLMSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        row = 0
        self.promptWidget = PromptWidget("promptLLMPresets", "promptLLMDefault")
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
        layout.addWidget(QtWidgets.QLabel("Prompt(s) Preview:"), row, 0, Qt.AlignTop)
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
        self.destSelector = FileTypeSelector(defaultValue="refined")
        self.destSelector.setFixedType(FileTypeSelector.TYPE_CAPTIONS)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), row, 0)
        layout.addLayout(self.destSelector, row, 1)

        self.cboOverwriteMode = QtWidgets.QComboBox()
        self.cboOverwriteMode.addItem("Overwrite all keys", TRANSFORM_OVERWRITE_MODE_ALL)
        self.cboOverwriteMode.addItem("Only write missing keys", TRANSFORM_OVERWRITE_MODE_MISSING)
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

        groupBox = QtWidgets.QGroupBox("Transform Captions with LLM")
        groupBox.setLayout(layout)
        return groupBox


    def onFileChanged(self, currentFile):
        self._parser = TemplateVariableParser(currentFile)
        self._updateParser()

    @Slot()
    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()

    @Slot()
    def _updatePreview(self):
        text = self.promptWidget.prompts
        preview, varPositions = self._parser.parseWithPositions(text)
        self.txtPromptPreview.setPlainText(preview)

        with QSignalBlocker(self.promptWidget.txtPrompts):
            self._highlighter.highlight(self.promptWidget.txtPrompts, self.txtPromptPreview, varPositions)
            PromptsHighlighter.highlightPromptSeparators(self.promptWidget.txtPrompts)
            PromptsHighlighter.highlightPromptSeparators(self.txtPromptPreview)


    def _confirmStart(self) -> bool:
        ops = [f"Use '{self.inferSettings.getSelectedPresetName()}' to transform Captions"]

        targetName = self.destSelector.name.strip()
        targetKey = f"captions.{targetName}"
        targetText = f"Write the Captions to .json files [{targetKey}]"
        if self.cboOverwriteMode.currentData() == TRANSFORM_OVERWRITE_MODE_MISSING:
            targetText += " if the key doesn't exist"
        else:
            targetText = qtlib.htmlRed(targetText + " and overwrite the content!")
        ops.append(targetText)

        if self.chkStorePrompts.isChecked():
            ops.append(f"Store the prompt in [prompts.{targetName}]")

        if self.spinRounds.value() > 1:
            ops.append(f"Do {self.spinRounds.value()} rounds of transformations")

        return BatchUtil.confirmStart("Transform", self.tab.filelist.getNumFiles(), ops, self)


    def createTask(self) -> BatchInferenceTask | None:
        if not self._confirmStart():
            return None

        storeName = self.destSelector.name.strip()
        rounds = self.spinRounds.value()
        prompts = self.promptWidget.getParsedPrompts(storeName, rounds)

        log = self.logWidget.addEntry("Transform")
        task = BatchTransformTask(log, self.tab.filelist)
        task.prompts = prompts
        task.systemPrompt = self.promptWidget.systemPrompt.strip()
        task.config = self.inferSettings.getInferenceConfig()

        task.overwriteMode = self.cboOverwriteMode.currentData()
        task.storePrompts  = self.chkStorePrompts.isChecked()
        task.stripAround   = self.chkStripAround.isChecked()
        task.stripMulti    = self.chkStripMulti.isChecked()
        return task



class BatchTransformTask(BatchInferenceTask):
    def __init__(self, log, filelist):
        super().__init__("transform", log, filelist)
        self.prompts      = None
        self.systemPrompt = None
        self.config       = None

        self.overwriteMode = TRANSFORM_OVERWRITE_MODE_ALL
        self.storePrompts  = False
        self.stripAround = True
        self.stripMulti  = False

        self.varParser = None
        self.writeKeys = None


    def runPrepare(self, proc: InferenceProcess):
        self.signals.progressMessage.emit("Loading LLM ...")
        proc.setupLLM(self.config)

        self.writeKeys = {k for conv in self.prompts for k in conv.keys() if not k.startswith('?')}

        self.varParser = TemplateVariableParser()
        self.varParser.stripAround = self.stripAround
        self.varParser.stripMultiWhitespace = self.stripMulti


    def runCheckFile(self, imgFile: str, proc: InferenceProcess) -> Callable | None:
        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        if not self.check(captionFile):
            return None

        prompts = self.parsePrompts(imgFile, captionFile)
        def queue():
            proc.answer(prompts, self.systemPrompt)
        return queue

    def check(self, captionFile: CaptionFile) -> set:
        writeKeys = set(self.writeKeys)
        if self.overwriteMode == TRANSFORM_OVERWRITE_MODE_MISSING:
            writeKeys.difference_update(captionFile.captions.keys())
        return writeKeys


    def runProcessFile(self, imgFile, results: list) -> str | None:
        if not results:
            return None

        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        writeKeys = self.check(captionFile)
        if not writeKeys:
            return None

        answers = results[0].get("answers")
        if self.storeAnswers(imgFile, captionFile, writeKeys, answers):
            captionFile.saveToJson()
            return captionFile.jsonPath
        return None


    def storeAnswers(self, imgFile, captionFile: CaptionFile, writeKeys: set, answers) -> bool:
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
