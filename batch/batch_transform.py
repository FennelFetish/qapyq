import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib, util
from config import Config
from infer import Inference, InferencePresetWidget
from .batch_task import BatchTask
from .captionfile import CaptionFile
from template_parser import TemplateParser


class BatchTransform(QtWidgets.QWidget):
    SYS_PROMPT = "Your task is to summarize image captions. I will provide multiple descriptions of the same image separated by empty lines. " \
               + "I will also include a list of booru tags that accurately categorize the image. " \
               + "Use your full knowledge about booru tags and use them to inform your summary.\n\n" \
               \
               + "You will summarize my descriptions and condense all provided information into one paragraph. " \
               + "The resulting description must encompass all the details provided in my original input. " \
               + "You may rephrase my input, but never invent anything new. Your output will never contain new information."

    PROMPT_TPL = "{{?captions.caption}}\n\n" \
               + "{{?captions.caption_round1}}\n\n" \
               + "{{?captions.caption_round2}}\n\n" \
               + "{{?captions.caption_round3}}\n\n" \
               + "Booru Tags: {{?tags}}"


    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: QtWidgets.QStatusBar = statusBar

        self.inferSettings = InferencePresetWidget("inferLLMPresets")

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildLLMSettings())
        #layout.addWidget(self._buildPreview())
        layout.addWidget(self._buildTransformSettings())
        self.setLayout(layout)

        self._parser = None
        self._task = None


    def _buildLLMSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        self.txtSystemPrompt = QtWidgets.QPlainTextEdit(BatchTransform.SYS_PROMPT)
        qtlib.setMonospace(self.txtSystemPrompt)
        qtlib.setTextEditHeight(self.txtSystemPrompt, 5, "min")
        qtlib.setShowWhitespace(self.txtSystemPrompt)
        layout.addWidget(QtWidgets.QLabel("System Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtSystemPrompt, 0, 1, 1, 2)
        layout.setRowStretch(0, 1)

        self.txtPromptTemplate = QtWidgets.QPlainTextEdit()
        self.txtPromptTemplate.setPlainText(BatchTransform.PROMPT_TPL)
        qtlib.setMonospace(self.txtPromptTemplate)
        qtlib.setTextEditHeight(self.txtPromptTemplate, 10, "min")
        qtlib.setShowWhitespace(self.txtPromptTemplate)
        self.txtPromptTemplate.textChanged.connect(self._updatePreview)
        layout.addWidget(QtWidgets.QLabel("Prompt(s) Template:"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPromptTemplate, 1, 1, 1, 2)
        layout.setRowStretch(1, 2)

        self.txtPromptPreview = QtWidgets.QPlainTextEdit()
        self.txtPromptPreview.setReadOnly(True)
        qtlib.setMonospace(self.txtPromptPreview)
        qtlib.setTextEditHeight(self.txtPromptPreview, 5, "min")
        qtlib.setShowWhitespace(self.txtPromptPreview)
        layout.addWidget(QtWidgets.QLabel("Prompt Preview:"), 2, 0, Qt.AlignTop)
        layout.addWidget(self.txtPromptPreview, 2, 1, 1, 2)
        layout.setRowStretch(2, 4)

        self.chkStripAround = QtWidgets.QCheckBox("Surrounding whitespace")
        self.chkStripAround.setChecked(True)
        self.chkStripAround.checkStateChanged.connect(self._updateParser)

        self.chkStripMulti = QtWidgets.QCheckBox("Repeating whitespace")
        self.chkStripMulti.setChecked(False)
        self.chkStripMulti.checkStateChanged.connect(self._updateParser)

        layout.addWidget(QtWidgets.QLabel("Strip:"), 3, 0, Qt.AlignTop)
        layout.addWidget(self.chkStripAround, 3, 1)
        layout.addWidget(self.chkStripMulti, 3, 2)

        self.txtTargetName = QtWidgets.QLineEdit("target")
        qtlib.setMonospace(self.txtTargetName)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), 4, 0, Qt.AlignTop)
        layout.addWidget(self.txtTargetName, 4, 1)

        self.spinRounds = QtWidgets.QSpinBox()
        self.spinRounds.setRange(1, 100)
        self.spinRounds.setValue(1)
        layout.addWidget(QtWidgets.QLabel("Rounds:"), 5, 0, Qt.AlignTop)
        layout.addWidget(self.spinRounds, 5, 1)

        layout.addWidget(self.inferSettings, 6, 0, 1, 3)

        groupBox = QtWidgets.QGroupBox("LLM")
        groupBox.setLayout(layout)
        return groupBox

    # def _buildPreview(self):
    #     layout = QtWidgets.QGridLayout()
    #     layout.setAlignment(Qt.AlignTop)
    #     layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
    #     layout.setColumnStretch(0, 0)

    #     self.txtPreview = QtWidgets.QPlainTextEdit()
    #     self.txtPreview.setReadOnly(True)
    #     qtlib.setMonospace(self.txtPreview)
    #     qtlib.setShowWhitespace(self.txtPreview)
    #     layout.addWidget(QtWidgets.QLabel("Preview:"), 0, 0, Qt.AlignTop)
    #     layout.addWidget(self.txtPreview, 0, 1, 1, 2)

    #     btnGeneratePreview = QtWidgets.QPushButton("Generate Preview")
    #     layout.addWidget(btnGeneratePreview, 1, 0, 1, 2)

    #     groupBox = QtWidgets.QGroupBox("Preview")
    #     groupBox.setLayout(layout)
    #     return groupBox


    def _buildTransformSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.btnStart = QtWidgets.QPushButton("Start Batch Transform")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 1, 0, 1, 2)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    def onFileChanged(self, currentFile):
        self._parser = TemplateParser(currentFile)
        self._updateParser()

    def _updateParser(self):
        if self._parser:
            self._parser.stripAround = self.chkStripAround.isChecked()
            self._parser.stripMultiWhitespace = self.chkStripMulti.isChecked()
            self._updatePreview()


    def _updatePreview(self):
        text = self.txtPromptTemplate.toPlainText()
        preview = self._parser.parse(text)
        self.txtPromptPreview.setPlainText(preview)


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            storeName = self.txtTargetName.text().strip()
            prompts   = util.parsePrompts(self.txtPromptTemplate.toPlainText(), storeName)
            sysPrompt = self.txtSystemPrompt.toPlainText()

            config = self.inferSettings.toDict()

            self._task = BatchTransformTask(self.log, self.tab.filelist, prompts, sysPrompt, config)
            self._task.stripAround = self.chkStripAround.isChecked()
            self._task.stripMulti = self.chkStripMulti.isChecked()
            self._task.rounds = self.spinRounds.value()
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
    def __init__(self, log, filelist, prompts, systemPrompt, config):
        super().__init__("transform", log, filelist)
        self.prompts      = prompts
        self.systemPrompt = systemPrompt
        self.config       = config

        self.stripAround  = True
        self.stripMulti   = False
        self.rounds: int  = 1


    def runPrepare(self):
        inference = Inference()
        self.inferProc = inference.proc
        self.inferProc.start()

        self.signals.progressMessage.emit("Loading LLM ...")
        if not self.inferProc.setupLLM(self.config):
            raise RuntimeError("Couldn't load LLM")

        self.parser = TemplateParser(None)
        self.parser.stripAround = self.stripAround
        self.parser.stripMultiWhitespace = self.stripMulti


    def runProcessFile(self, imgFile) -> str:
        captionFile = CaptionFile(imgFile)
        if not captionFile.loadFromJson():
            self.log(f"WARNING: Couldn't read captions from {captionFile.jsonPath}")
            return None

        self.parser.setup(imgFile, captionFile)
        prompts = {name: self.parser.parse(prompt) for name, prompt in self.prompts.items()}

        answers = self.inferProc.answer(prompts, self.systemPrompt, self.rounds)
        if answers:
            for name, caption in answers.items():
                if caption:
                    captionFile.addCaption(name, caption)
                else:
                    self.log(f"WARNING: Caption '{name}' is empty for {imgFile}, ignoring")
        else:
            self.log(f"WARNING: No answers returned for {imgFile}")

        if captionFile.updateToJson():
            return captionFile.jsonPath
        else:
            self.log(f"WARNING: Failed to save caption to {captionFile.jsonPath}")
            return None
