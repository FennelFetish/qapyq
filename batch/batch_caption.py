from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib, util
from config import Config
from infer import Inference, InferencePresetWidget, TagPresetWidget
from .batch_task import BatchTask
from .captionfile import CaptionFile


class BatchCaption(QtWidgets.QWidget):
    def __init__(self, tab, logSlot, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.log = logSlot
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: QtWidgets.QStatusBar = statusBar

        self.inferSettings = InferencePresetWidget()
        self.tagSettings = TagPresetWidget()

        self.captionGroup = self._buildCaptionSettings()
        self.tagGroup = self._buildTagSettings()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.captionGroup)
        layout.addWidget(self.tagGroup)
        layout.addWidget(self._buildGenerateSettings())
        self.setLayout(layout)

        self._task = None


    def _buildCaptionSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        self.txtSystemPrompt = QtWidgets.QPlainTextEdit(Config.inferSystemPrompt)
        qtlib.setMonospace(self.txtSystemPrompt)
        qtlib.setTextEditHeight(self.txtSystemPrompt, 5, "min")
        qtlib.setShowWhitespace(self.txtSystemPrompt)
        layout.addWidget(QtWidgets.QLabel("System Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtSystemPrompt, 0, 1, 1, 2)
        layout.setRowStretch(0, 1)

        self.txtPrompts = QtWidgets.QPlainTextEdit(Config.inferPrompt)
        qtlib.setMonospace(self.txtPrompts)
        qtlib.setTextEditHeight(self.txtPrompts, 10, "min")
        qtlib.setShowWhitespace(self.txtPrompts)
        layout.addWidget(QtWidgets.QLabel("Prompt(s):"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrompts, 1, 1, 1, 2)
        layout.setRowStretch(1, 6)

        self.txtTargetName = QtWidgets.QLineEdit("caption")
        qtlib.setMonospace(self.txtTargetName)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), 2, 0)
        layout.addWidget(self.txtTargetName, 2, 1)

        self.chkStorePrompts = QtWidgets.QCheckBox("Store Prompts")
        layout.addWidget(self.chkStorePrompts, 2, 2)

        self.spinRounds = QtWidgets.QSpinBox()
        self.spinRounds.setRange(1, 100)
        self.spinRounds.setValue(1)
        layout.addWidget(QtWidgets.QLabel("Rounds:"), 3, 0)
        layout.addWidget(self.spinRounds, 3, 1)

        layout.addWidget(self.inferSettings, 4, 0, 1, 3)

        groupBox = QtWidgets.QGroupBox("Generate Captions")
        groupBox.setCheckable(True)
        groupBox.setLayout(layout)
        return groupBox


    def _buildTagSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)

        layout.addWidget(self.tagSettings, 0, 0, 1, 2)

        self.txtTagTargetName = QtWidgets.QLineEdit("tags")
        qtlib.setMonospace(self.txtTagTargetName)
        layout.addWidget(QtWidgets.QLabel("Storage key:"), 1, 0)
        layout.addWidget(self.txtTagTargetName, 1, 1)

        # TODO: Apply rules. Or separate batch tab? Also: Merge tags from different models? (easy with the remove duplicate option)
        # Separate tab probably better

        groupBox = QtWidgets.QGroupBox("Generate Tags")
        groupBox.setCheckable(True)
        groupBox.setLayout(layout)
        return groupBox


    def _buildGenerateSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.btnStart = QtWidgets.QPushButton("Start Batch Caption")
        self.btnStart.clicked.connect(self.startStop)
        layout.addWidget(self.btnStart, 1, 0, 1, 2)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            self._task = BatchCaptionTask(self.log, self.tab.filelist)
            self._task.rounds = self.spinRounds.value()
            self._task.storePrompts = self.chkStorePrompts.isChecked()

            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.progressMessage.connect(self.onProgressMessage)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)

            if self.captionGroup.isChecked():
                storeName = self.txtTargetName.text().strip()
                self._task.prompts = util.parsePrompts(self.txtPrompts.toPlainText(), storeName)
                self._task.systemPrompt = self.txtSystemPrompt.toPlainText()
                self._task.config = self.inferSettings.getInferenceConfig()

            if self.tagGroup.isChecked():
                self._task.tagConfig = self.tagSettings.getInferenceConfig()
                self._task.tagName = self.txtTagTargetName.text().strip()

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



class BatchCaptionTask(BatchTask):
    def __init__(self, log, filelist):
        super().__init__("caption", log, filelist)
        self.prompts      = None
        self.systemPrompt = None
        self.config       = None

        self.tagConfig    = None
        self.tagName      = None

        self.rounds: int = 1
        self.storePrompts: bool = False

        self.doCaption = False
        self.doTag = False
        self.inferProc = None


    def runPrepare(self):
        self.doCaption = self.prompts is not None
        self.doTag = self.tagConfig is not None

        self.inferProc = Inference().proc
        self.inferProc.start()

        if self.doCaption:
            self.signals.progressMessage.emit("Loading caption model ...")
            if not self.inferProc.setupCaption(self.config):
                raise RuntimeError("Couldn't load caption model")
        if self.doTag:
            self.signals.progressMessage.emit("Loading tag model ...")
            if not self.inferProc.setupTag(self.tagConfig):
                raise RuntimeError("Couldn't load tag model")
            if not self.tagName:
                self.tagName = "tags"


    def runProcessFile(self, imgFile: str) -> str:
        captionFile = CaptionFile(imgFile)

        if self.doCaption:
            self.runCaption(imgFile, captionFile)

        if self.doTag:
            self.runTags(imgFile, captionFile)

        if captionFile.updateToJson():
            return captionFile.jsonPath
        else:
            self.log(f"WARNING: Failed to save captions to {captionFile.jsonPath}")
            return None

    def runCaption(self, imgFile: str, captionFile: CaptionFile):
        answers = self.inferProc.caption(imgFile, self.prompts, self.systemPrompt, self.rounds)
        if not answers:
            self.log(f"WARNING: No captions returned for {imgFile}")
            return

        for name, caption in answers.items():
            if caption:
                captionFile.addCaption(name, caption)
                if self.storePrompts:
                    captionFile.addPrompt(name, self.prompts.get(name))
            else:
                self.log(f"WARNING: Caption '{name}' is empty for {imgFile}, ignoring")
        
    def runTags(self, imgFile: str, captionFile: CaptionFile):
        tags = self.inferProc.tag(imgFile)
        if tags:
            captionFile.addTags(self.tagName, tags)
        else:
            self.log(f"WARNING: No tags returned for {imgFile}, ignoring")
