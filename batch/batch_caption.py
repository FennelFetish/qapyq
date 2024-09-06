from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker
from infer import Inference
from .captionfile import CaptionFile
import qtlib, util
from config import Config
import traceback


class BatchCaption(QtWidgets.QWidget):
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

        self.txtSystemPrompt = QtWidgets.QTextEdit(Config.inferSystemPrompt)
        qtlib.setMonospace(self.txtSystemPrompt)
        qtlib.setTextEditHeight(self.txtSystemPrompt, 5)
        qtlib.setShowWhitespace(self.txtSystemPrompt)
        layout.addWidget(QtWidgets.QLabel("System Prompt:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtSystemPrompt, 0, 1)

        self.txtPrompts = QtWidgets.QTextEdit(Config.inferPrompt)
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
        self.spinTagThreshold.setValue(Config.inferTagThreshold)
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
            self._task.rounds = self.spinRounds.value()
            self._task.tagThreshold = self.spinTagThreshold.value()
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

        self.rounds: int = 1
        self.tagThreshold: float = 0.4


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
            inference.proc.start()
            minicpm = False

            if self.prompts:
                inference.proc.setupCaption()
                minicpm = True
            if self.doTag:
                inference.proc.setupTag(threshold=self.tagThreshold)

            self.process(inference.proc, minicpm, self.doTag)
        except Exception as ex:
            print("Error during batch processing:")
            traceback.print_exc()
            self.signals.fail.emit(f"Error during batch processing: {str(ex)}")


    def process(self, inferProc, minicpm, joytag):
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
                answers = inferProc.caption(imgFile, self.prompts, self.systemPrompt, self.rounds)
                for name, caption in answers.items():
                    captionFile.addCaption(name, caption)

            if joytag:
                captionFile.tags = inferProc.tag(imgFile)

            captionFile.updateToJson()
            self.signals.progress.emit(fileNr+1, numFiles, captionFile.jsonPath)

        self.signals.done.emit(numFiles)
