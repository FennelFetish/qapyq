from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker
import qtlib
from config import Config
from infer import Inference, InferencePresetWidget, PromptWidget, PromptsHighlighter
from .batch_task import BatchTask
from .captionfile import CaptionFile
from template_parser import TemplateVariableParser, VariableHighlighter


class BatchTransform(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: qtlib.ColoredMessageStatusBar = statusBar

        self.inferSettings = InferencePresetWidget("inferLLMPresets")

        self.btnStart = QtWidgets.QPushButton("Start Batch Transform")
        self.btnStart.clicked.connect(self.startStop)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildLLMSettings())
        layout.addWidget(self.btnStart)
        self.setLayout(layout)

        self._parser = None
        self._highlighter = VariableHighlighter()
        self._task = None


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
        self.txtTargetName = QtWidgets.QLineEdit("refined")
        qtlib.setMonospace(self.txtTargetName)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), row, 0)
        layout.addWidget(self.txtTargetName, row, 1)

        self.cboOverwriteMode = QtWidgets.QComboBox()
        self.cboOverwriteMode.addItem("Overwrite all keys", "all")
        self.cboOverwriteMode.addItem("Only write missing keys", "missing")
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


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            storeName = self.txtTargetName.text().strip()
            rounds = self.spinRounds.value()
            prompts = self.promptWidget.getParsedPrompts(storeName, rounds)
            
            self._task = BatchTransformTask(self.log, self.tab.filelist)
            self._task.prompts = prompts
            self._task.systemPrompt = self.promptWidget.systemPrompt.strip()
            self._task.config = self.inferSettings.getInferenceConfig()

            self._task.overwriteMode = self.cboOverwriteMode.currentData()
            self._task.storePrompts  = self.chkStorePrompts.isChecked()
            self._task.stripAround   = self.chkStripAround.isChecked()
            self._task.stripMulti    = self.chkStripMulti.isChecked()

            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.progressMessage.connect(self.onProgressMessage)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)
            Inference().queueTask(self._task)

    @Slot()
    def onFinished(self, numFiles):
        self.statusBar.showColoredMessage(f"Processed {numFiles} files", True, 0)
        self.taskDone()

    @Slot()
    def onFail(self, reason):
        self.statusBar.showColoredMessage(reason, False, 0)
        self.taskDone()

    @Slot()
    def onProgress(self, numDone, numTotal, jsonFile):
        self.progressBar.setRange(0, numTotal)
        self.progressBar.setValue(numDone)

        if jsonFile:
            self.statusBar.showMessage("Wrote " + jsonFile)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.btnStart.setText("Start Batch Caption")
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self._task = None



class BatchTransformTask(BatchTask):
    def __init__(self, log, filelist):
        super().__init__("transform", log, filelist)
        self.prompts      = None
        self.systemPrompt = None
        self.config       = None

        self.overwriteMode = "all"
        self.storePrompts  = False
        self.stripAround = True
        self.stripMulti  = False

        self.inferProc = None
        self.varParser = None
        self.writeKeys = None


    def runPrepare(self):
        self.inferProc = Inference().proc
        self.inferProc.start()

        self.signals.progressMessage.emit("Loading LLM ...")
        if not self.inferProc.setupLLM(self.config):
            raise RuntimeError("Couldn't load LLM")

        self.writeKeys = {k for conv in self.prompts for k in conv.keys() if not k.startswith('?')}

        self.varParser = TemplateVariableParser()
        self.varParser.stripAround = self.stripAround
        self.varParser.stripMultiWhitespace = self.stripMulti


    def runProcessFile(self, imgFile) -> str:
        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        writeKeys = set(self.writeKeys)
        if self.overwriteMode == "missing":
            for name in captionFile.captions.keys():
                writeKeys.discard(name)
        
        if not writeKeys:
            return None

        if self.runAnswers(imgFile, captionFile, writeKeys):
            captionFile.saveToJson()
            return captionFile.jsonPath
        return None


    def runAnswers(self, imgFile, captionFile: CaptionFile, writeKeys) -> bool:
        prompts = self.parsePrompts(imgFile, captionFile)
        answers = self.inferProc.answer(prompts, self.systemPrompt)
        if not answers:
            self.log(f"WARNING: No answers returned for {imgFile}")
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


    def parsePrompts(self, imgFile: str, captionFile: CaptionFile) -> list:
        self.varParser.setup(imgFile, captionFile)

        prompts = list()
        missingVars = list()
        for conv in self.prompts:
            prompts.append( {name: self.varParser.parse(prompt) for name, prompt in conv.items()} )
            missingVars.extend(self.varParser.missingVars)

        if missingVars:
            self.log(f"WARNING: {captionFile.jsonPath} is missing values for variables: {', '.join(missingVars)}")

        return prompts
