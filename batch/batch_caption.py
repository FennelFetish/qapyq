from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from lib import qtlib
from lib.captionfile import CaptionFile
from config import Config
from infer import Inference, InferencePresetWidget, TagPresetWidget, PromptWidget
from .batch_task import BatchTask


# TODO: Loading of variables

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

        self._task = None


    def _buildCaptionSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnMinimumWidth(0, Config.batchWinLegendWidth)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)
        layout.setColumnStretch(3, 1)

        row = 0
        self.promptWidget = PromptWidget("promptCaptionPresets", "promptCaptionDefault")
        self.promptWidget.enableHighlighting()
        qtlib.setTextEditHeight(self.promptWidget.txtSystemPrompt, 5, "min")
        qtlib.setTextEditHeight(self.promptWidget.txtPrompts, 10, "min")
        self.promptWidget.layout().setRowStretch(1, 1)
        self.promptWidget.layout().setRowStretch(2, 6)
        layout.addWidget(self.promptWidget, row, 0, 1, 4)

        row += 1
        self.txtTargetName = QtWidgets.QLineEdit("caption")
        qtlib.setMonospace(self.txtTargetName)
        layout.addWidget(QtWidgets.QLabel("Default storage key:"), row, 0)
        layout.addWidget(self.txtTargetName, row, 1)

        self.cboOverwriteMode = QtWidgets.QComboBox()
        self.cboOverwriteMode.addItem("Overwrite all keys", "all")
        self.cboOverwriteMode.addItem("Only write missing keys", "missing")
        #self.cboOverwriteMode.addItem("Skip file if default key exists", "skip-default-exists")
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

        self.chkTagSkipExisting = QtWidgets.QCheckBox("Skip file if key exists")
        layout.addWidget(self.chkTagSkipExisting, 1, 2)

        # TODO: Apply rules. Or separate batch tab? Also: Merge tags from different models? (easy with the remove duplicate option)
        # Separate tab probably better

        groupBox = QtWidgets.QGroupBox("Generate Tags")
        groupBox.setCheckable(True)
        groupBox.setLayout(layout)
        return groupBox


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnStart.setText("Abort")

            self._task = BatchCaptionTask(self.log, self.tab.filelist)
            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.progressMessage.connect(self.onProgressMessage)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)

            if self.captionGroup.isChecked():
                storeName = self.txtTargetName.text().strip()
                rounds = self.spinRounds.value()
                self._task.prompts = self.promptWidget.getParsedPrompts(storeName, rounds)

                self._task.systemPrompt = self.promptWidget.systemPrompt.strip()
                self._task.config = self.inferSettings.getInferenceConfig()
                self._task.overwriteMode = self.cboOverwriteMode.currentData()
                self._task.storePrompts = self.chkStorePrompts.isChecked()

            if self.tagGroup.isChecked():
                self._task.tagConfig = self.tagSettings.getInferenceConfig()
                self._task.tagName = self.txtTagTargetName.text().strip()
                self._task.tagSkipExisting = self.chkTagSkipExisting.isChecked()

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
        self.overwriteMode = "all"
        self.storePrompts: bool = False

        self.tagConfig    = None
        self.tagName      = None
        self.tagSkipExisting = False

        self.doCaption = False
        self.doTag     = False
        self.inferProc = None
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
        if self.overwriteMode == "missing":
            for name in captionFile.captions.keys():
                writeKeys.discard(name)

        if not writeKeys:
            return False

        answers = self.inferProc.caption(imgFile, self.prompts, self.systemPrompt)
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
                prompt = next((conv[name] for conv in self.prompts if name in conv), None)
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
