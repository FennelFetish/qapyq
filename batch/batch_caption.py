from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker
from infer import Inference
from .captionfile import CaptionFile
import qtlib, util


class BatchCaption(QtWidgets.QWidget):
    DEFAULT_SYSPROMPT = "You are an assistant that perfectly describes scenes in concise English language. You're always certain and you don't guess. " \
                      + "You are never confused or distracted by semblance. You state facts. Refer to a person using gendered pronouns like she/he. " \
                      + "Don't format your response into numered lists or bullet points."

    DEFAULT_PROMPT = "What's to see here? Describe the image in detail."

    DEFAULT_TAG_THRESHOLD = 0.4


    def __init__(self, tab, progressBar, statusBar):
        super().__init__()
        self.tab = tab
        self.progressBar: QtWidgets.QProgressBar = progressBar
        self.statusBar: QtWidgets.QStatusBar = statusBar

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._buildCaptionSettings())
        layout.addWidget(self._buildTagSettings())
        layout.addWidget(self._buildGenerateSettings())
        self.setLayout(layout)

        self._task = None


    def _buildCaptionSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.txtSystemPrompt = QtWidgets.QTextEdit(BatchCaption.DEFAULT_SYSPROMPT)
        qtlib.setMonospace(self.txtSystemPrompt)
        qtlib.setTextEditHeight(self.txtSystemPrompt, 5)
        qtlib.setShowWhitespace(self.txtSystemPrompt)
        layout.addWidget(QtWidgets.QLabel("System Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtSystemPrompt, 0, 1)

        self.txtPrompts = QtWidgets.QTextEdit(BatchCaption.DEFAULT_PROMPT)
        qtlib.setMonospace(self.txtPrompts)
        qtlib.setTextEditHeight(self.txtPrompts, 10)
        qtlib.setShowWhitespace(self.txtPrompts)
        layout.addWidget(QtWidgets.QLabel("Prompt(s):"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrompts, 1, 1)

        self.spinRounds = QtWidgets.QSpinBox()
        self.spinRounds.setRange(1, 100)
        self.spinRounds.setValue(1)
        layout.addWidget(QtWidgets.QLabel("Rounds:"), 2, 0, Qt.AlignTop)
        layout.addWidget(self.spinRounds, 2, 1)

        self.chkCaption = QtWidgets.QCheckBox("Generate Caption")
        self.chkCaption.setChecked(True)
        layout.addWidget(self.chkCaption, 3, 1)

        groupBox = QtWidgets.QGroupBox("MiniCPM")
        groupBox.setLayout(layout)
        return groupBox


    def _buildTagSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        self.spinTagThreshold = QtWidgets.QDoubleSpinBox()
        self.spinTagThreshold.setValue(BatchCaption.DEFAULT_TAG_THRESHOLD)
        self.spinTagThreshold.setRange(0.0, 1.0)
        self.spinTagThreshold.setSingleStep(0.05)
        layout.addWidget(QtWidgets.QLabel("Threshold:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.spinTagThreshold, 0, 1)

        self.chkTag = QtWidgets.QCheckBox("Generate Tags")
        self.chkTag.setChecked(True)
        layout.addWidget(self.chkTag, 1, 1)

        groupBox = QtWidgets.QGroupBox("JoyTag")
        groupBox.setLayout(layout)
        return groupBox


    def _buildGenerateSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)

        self.btnGenerate = QtWidgets.QPushButton("Start")
        self.btnGenerate.clicked.connect(self.startStop)
        layout.addWidget(self.btnGenerate, 1, 0, 1, 2)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget


    @Slot()
    def startStop(self):
        if self._task:
            self._task.abort()
        else:
            self.btnGenerate.setText("Abort")
            self.statusBar.showMessage("Starting batch processing ...")

            files = list(self.tab.filelist.files)
            if len(files) == 0:
                files.append(self.tab.filelist.currentFile)

            if self.chkCaption.isChecked():
                prompts = util.parsePrompts(self.txtPrompts.toPlainText())
                sysPrompt = self.txtSystemPrompt.toPlainText()
            else:
                prompts, sysPrompt = None, None

            self._task = BatchCaptionTask(self.tab.filelist.files, prompts, sysPrompt, self.chkTag.isChecked())
            self._task.signals.progress.connect(self.onProgress)
            self._task.signals.done.connect(self.onFinished)
            self._task.signals.fail.connect(self.onFail)
            Inference().threadPool.start(self._task)

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

    def taskDone(self):
        self.btnGenerate.setText("Start")
        self.progressBar.reset()
        self._task = None



class BatchCaptionTask(QRunnable):
    class Signals(QObject):
        progress = Signal(int, int, str)
        done = Signal(int)
        fail = Signal(str)

    def __init__(self, files, prompts, systemPrompt, doTag):
        super().__init__()
        self.signals = BatchCaptionTask.Signals()
        self.mutex = QMutex()
        self.aborted = False

        self.files = files
        self.prompts = prompts
        self.systemPrompt = systemPrompt
        self.doTag = doTag

    def abort(self):
        with QMutexLocker(self.mutex):
            self.aborted = True

    def isAborted(self) -> bool:
        with QMutexLocker(self.mutex):
            return self.aborted

    @Slot()
    def run(self):
        try:
            print("Starting batch caption ...")
            self.signals.progress.emit(0, 0, "")

            inference = Inference()
            minicpm = inference.loadMiniCpm() if self.prompts else None
            joytag  = inference.loadJoytag() if self.doTag else None
            self.process(minicpm, joytag)
        except Exception as ex:
            print("Error during batch processing:")
            print(ex)
            self.signals.fail.emit("Error during batch processing")

    def process(self, minicpm, joytag):
        numFiles = len(self.files)
        self.signals.progress.emit(0, numFiles, "")

        for fileNr, imgFile in enumerate(self.files):
            if self.isAborted():
                print("Aborted")
                self.signals.fail.emit(f"Batch processing aborted after {fileNr} files")
                return

            print("Batch caption task:", imgFile)
            captionFile = CaptionFile(imgFile)

            if minicpm:
                answers = minicpm.captionMulti(imgFile, self.prompts, self.systemPrompt)
                for name, caption in answers.items():
                    captionFile.addCaption(name, caption)

            if joytag:
                captionFile.tags = joytag.caption(imgFile)

            captionFile.updateToJson()
            self.signals.progress.emit(fileNr+1, numFiles, captionFile.jsonPath)

        self.signals.done.emit(numFiles)
