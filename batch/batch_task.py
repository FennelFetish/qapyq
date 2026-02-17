import traceback, time, enum
from typing import Iterable, Callable, Any
from typing_extensions import override
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker, QThreadPool
from infer.inference import Inference, InferenceChain, InferenceSetupException
from lib.filelist import FileList
import lib.qtlib as qtlib
from .batch_log import BatchLogEntry, BatchTaskAbortedException


class BatchTaskFileSelection(enum.IntEnum):
    All      = 0
    Selected = 1
    Current  = 2

    def getFiles(self, filelist: FileList) -> list[str]:
        match self:
            case self.All:
                files = filelist.getFiles().copy()
            case self.Selected:
                files = list(filelist.selection.sorted)
            case self.Current:
                files = []

        if (not files) and filelist.currentFile:
            files.append(filelist.currentFile)
        return files


class BatchTask(QRunnable):
    class Signals(QObject):
        progress = Signal(str, object)  # file, TimeUpdate
        progressMessage = Signal(str)   # message
        done = Signal(object)           # TimeUpdate
        fail = Signal(str, object)      # error message, TimeUpdate


    def __init__(self, name: str, log: BatchLogEntry, files: list[str]):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = BatchTask.Signals()

        self.name     = name
        self.log      = log
        self.files    = files

        self._mutex   = QMutex()
        self._aborted = False


    def abort(self):
        with QMutexLocker(self._mutex):
            self._aborted = True

    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._aborted


    @Slot()
    def run(self):
        try:
            self.log(f"=== Starting batch {self.name} ===")
            self.signals.progressMessage.emit(f"Starting batch {self.name} ...")
            self.signals.progress.emit(None, None)

            self.runPrepare()
            self.signals.progressMessage.emit("Processing ...")
            self.processAll(self.files)

        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            exString = str(ex)
            self.log(f"Error during batch {self.name}: {exString}")
            self.signals.fail.emit(exString, None)
        finally:
            self.runCleanup()
            self.log.releaseEntry()


    def _getFileArgs(self, args: Any) -> tuple:
        return args, None

    def processAll(self, processFileArgs: Iterable):
        numFiles = len(self.files)
        numFilesDone = 0
        numFilesSkipped = 0

        timeAvg = TimeAverage()
        update = BatchProgressUpdate(timeAvg, numFiles, 0, 0)
        self.signals.progress.emit(None, update)
        timeAvg.init()

        for fileNr, fileArgs in enumerate(processFileArgs):
            imgFile, exception, *args = self._getFileArgs(fileArgs)

            if self.isAborted():
                abortMessage = f"Batch {self.name} aborted after {fileNr} files{update.getSkippedText(numFiles-fileNr)}"
                self.log(abortMessage)
                self.signals.fail.emit(abortMessage, update.finalize())
                return

            self.log(f"Processing: {imgFile}")
            outputFile = None

            with self.log.indent():
                try:
                    if exception:
                        self.log(f"WARNING: {str(exception)}")
                    else:
                        outputFile = self.runProcessFile(imgFile, *args)

                    if not outputFile:
                        self.log(f"Skipped")
                        numFilesSkipped += 1
                except Exception as ex:
                    outputFile = None
                    self.log(f"WARNING: {str(ex)}")
                    traceback.print_exc()
                finally:
                    numFilesDone += 1
                    timeAvg.update()
                    update = BatchProgressUpdate(timeAvg, numFiles, numFilesDone, numFilesSkipped)
                    self.signals.progress.emit(outputFile, update)

        self.log(f"Batch {self.name} finished, processed {numFiles} files{update.getSkippedText()} in {update.timeSpent:.2f} seconds")
        self.signals.done.emit(update.finalize())


    def runPrepare(self):
        pass

    def runProcessFile(self, imgFile: str) -> str | None:
        return None

    def runCleanup(self):
        pass



class BatchInferenceTask(BatchTask):
    def __init__(self, name: str, log: BatchLogEntry, files: list[str]):
        super().__init__(name, log, files)
        self.session = None

    def abort(self):
        with QMutexLocker(self._mutex):
            self._aborted = True
            if self.session:
                self.session.abort()

    @Slot()
    def run(self):
        try:
            self.log(f"=== Starting batch {self.name} ===")
            self.signals.progressMessage.emit(f"Starting batch {self.name} ...")
            self.signals.progress.emit(None, None)

            with Inference().createSession() as session:
                with QMutexLocker(self._mutex):
                    self.session = session

                session.prepare(self.runPrepare, lambda: self.signals.progressMessage.emit("Processing ..."))
                self.processAll(session.queueFiles(self.files, self.runCheckFile, all=True))

        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            exString = str(ex)
            self.log(f"Error during batch {self.name}: {exString}")
            self.signals.fail.emit(exString, None)
        finally:
            with QMutexLocker(self._mutex):
                self.session = None

            self.runCleanup()
            self.log.releaseEntry()


    def _getFileArgs(self, args: tuple) -> tuple:
        imgFile, results, exception = args

        if exception and isinstance(exception, InferenceSetupException):
            raise exception

        return (imgFile, exception, results)


    def runPrepare(self, proc):
        pass

    def runCheckFile(self, imgFile: str, proc) -> Callable | InferenceChain | None:
        pass

    def runProcessFile(self, imgFile: str, results: list[Any]) -> str | None:
        return None



class TimeAverage:
    HISTORY_SIZE = 20
    NS_IN_S = 1_000_000_000.0

    def __init__(self):
        self.tStart = 0
        self.tLast = 0
        self.history: list[int] = [0] * self.HISTORY_SIZE
        self.idxHistory = 0

        self.num = 0
        self.sumNs = 0
        self.totalNs = 0

    def init(self):
        self.tLast = self.tStart = time.monotonic_ns()

    def update(self):
        now = time.monotonic_ns()
        tDiff = now - self.tLast
        self.totalNs = now - self.tStart
        self.tLast = now

        if self.num < self.HISTORY_SIZE:
            self.num += 1
        else:
            self.sumNs -= self.history[self.idxHistory]

        self.history[self.idxHistory] = tDiff
        self.sumNs += tDiff

        self.idxHistory += 1
        if self.idxHistory >= self.HISTORY_SIZE:
            self.idxHistory = 0

    def getAvgTime(self) -> float:
        if self.num == 0:
            return 0.0
        return self.sumNs / self.num / self.NS_IN_S

    def getTotalTime(self) -> float:
        return self.totalNs / self.NS_IN_S



class BatchProgressUpdate:
    def __init__(self, timeAvg: TimeAverage, numFilesTotal: int, numFilesProcessed: int, numFilesSkipped: int):
        self.filesTotal     = numFilesTotal
        self.filesProcessed = numFilesProcessed
        self.filesSkipped   = numFilesSkipped

        self.timePerFile    = timeAvg.getAvgTime()
        self.timeRemaining  = self.timePerFile * (numFilesTotal - numFilesProcessed)
        self.timeSpent      = timeAvg.getTotalTime()

    def getSkippedText(self, numRemaining=0) -> str:
        msgs = [f"{self.filesSkipped} skipped"] if self.filesSkipped > 0 else []
        if numRemaining > 0:
            msgs.append(f"{numRemaining} remaining")
        msgs = ", ".join(msgs)
        return f" ({msgs})" if msgs else ""

    def finalize(self):
        if self.filesProcessed > 0:
            self.timePerFile = self.timeSpent / self.filesProcessed
        self.timeRemaining = 0
        return self



class BatchProgressBar(qtlib.ProgressBar):
    def __init__(self):
        self._timeText = ""
        self._lastTime = None
        super().__init__()

    def setTime(self, time: BatchProgressUpdate | None):
        if time is None:
            return

        self._lastTime = time
        timeSpent      = self.formatSeconds(time.timeSpent)
        timeRemaining  = self.formatSeconds(time.timeRemaining)
        self._timeText = f"{time.filesProcessed}/{time.filesTotal} Files processed in {timeSpent}, " \
                       + f"{timeRemaining} remaining ({time.timePerFile:.2f}s per File)"

    def resetTime(self):
        self._lastTime = None
        self._timeText = ""
        self.update()

    @override
    def text(self) -> str:
        if text := super().text():
            if self._timeText:
                return f"{text}  -  {self._timeText}"
            return text
        return self._timeText

    @override
    def reset(self):
        super().reset()
        if self._lastTime:
            timeSpent = self.formatSeconds(self._lastTime.timeSpent)
            self._timeText = f"{self._lastTime.filesProcessed} Files processed in {timeSpent} ({self._lastTime.timePerFile:.2f}s per File)"
        else:
            self._timeText = ""

    @staticmethod
    def formatSeconds(seconds: float):
        s = round(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        seconds = s % 60

        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"



class BatchTaskHandler(QObject):
    started = Signal()
    finished = Signal()

    def __init__(
        self, name: str, bars: tuple,
        filelist: FileList,
        confirmOps: Callable[[], tuple[list[str], bool]],
        taskFactory: Callable[[list[str]], BatchTask]
    ):
        super().__init__()
        self.name = name.capitalize()
        self.filelist = filelist
        self.confirmOps = confirmOps
        self.taskFactory = taskFactory

        self.startButtonLayout = self._buildStartButtonLayout()

        self.progressBar: BatchProgressBar = bars[0]
        self.statusBar: qtlib.ColoredMessageStatusBar = bars[1]
        self.statusBar.addPermanentWidget(self.progressBar)

        self._task: BatchTask | None = None

        self._tabActive = False
        self._lastMessage: str | tuple[str, bool] | None = None
        self._lastUpdate: BatchProgressUpdate | None = None


    def _buildStartButtonLayout(self) -> QtWidgets.QLayout:
        layout = QtWidgets.QHBoxLayout()

        self.btnStart = QtWidgets.QPushButton(f"▶  Start Batch {self.name} (All Files)")
        self.btnStart.clicked.connect(lambda: self.startStop(BatchTaskFileSelection.All))
        layout.addWidget(self.btnStart, 2)

        self.btnStartSelected = QtWidgets.QPushButton(f"▷  Start (Selected Files)")
        self.btnStartSelected.setMinimumWidth(200)
        self.btnStartSelected.clicked.connect(lambda: self.startStop(BatchTaskFileSelection.Selected))
        layout.addWidget(self.btnStartSelected, 1)

        self.btnStartCurrent = QtWidgets.QPushButton(f"▷  Start (Current File)")
        self.btnStartCurrent.setMinimumWidth(200)
        self.btnStartCurrent.clicked.connect(lambda: self.startStop(BatchTaskFileSelection.Current))
        layout.addWidget(self.btnStartCurrent, 1)

        return layout


    def setTabActive(self, active: bool):
        if active == self._tabActive:
            return
        self._tabActive = active

        if active:
            if isinstance(self._lastMessage, str):
                self.statusBar.showMessage(self._lastMessage)
            elif isinstance(self._lastMessage, tuple):
                self.statusBar.showColoredMessage(self._lastMessage[0], self._lastMessage[1], 0)
            else:
                self.statusBar.clearMessage()

            if self._lastUpdate:
                self.progressBar.setTime(self._lastUpdate)
                if self._task:
                    self.progressBar.setRange(0, self._lastUpdate.filesTotal)
                    self.progressBar.setValue(self._lastUpdate.filesProcessed)
                else:
                    self.progressBar.setRange(0, 1)
                    self.progressBar.reset()
            else:
                self.progressBar.resetTime()
                self.progressBar.setRange(0, 1)
                self.progressBar.reset()


    def startStop(self, fileSelection: BatchTaskFileSelection):
        parent = self.btnStart.parentWidget()

        if self._task:
            if BatchUtil.confirmAbort(parent) and self._task: # Recheck task (may have finished in the meantime)
                self.btnStart.setText("Aborting...")
                self._task.abort()
            return

        try:
            confirmOps, needsInference = self.confirmOps()
        except Exception as ex:
            print(f"Batch confirmation failed: {ex}")
            return

        files = fileSelection.getFiles(self.filelist)
        if not files:
            return
        if not BatchUtil.confirmStart(self.name, len(files), confirmOps, needsInference, parent):
            return

        try:
            task = self.taskFactory(files)
        except BatchTaskAbortedException:
            return

        task.signals.progress.connect(self.onProgress, Qt.ConnectionType.QueuedConnection)
        task.signals.progressMessage.connect(self.onProgressMessage, Qt.ConnectionType.QueuedConnection)
        task.signals.done.connect(self.onFinished, Qt.ConnectionType.QueuedConnection)
        task.signals.fail.connect(self.onFail, Qt.ConnectionType.QueuedConnection)

        self.btnStart.setText("Abort")
        self.btnStartSelected.setEnabled(False)
        self.btnStartCurrent.setEnabled(False)

        self._task = task
        QThreadPool.globalInstance().start(task)
        self.started.emit()


    @Slot()
    def onFinished(self, update: BatchProgressUpdate):
        msg = f"Processed {update.filesTotal} files{update.getSkippedText()}"
        self._lastMessage = (msg, True)
        self._lastUpdate = update

        if self._tabActive:
            self.statusBar.showColoredMessage(msg, True, 0)
            self.progressBar.setTime(update)

        self.taskDone()

    @Slot()
    def onFail(self, reason, update: BatchProgressUpdate | None):
        self._lastMessage = (reason, False)
        self._lastUpdate = update

        if self._tabActive:
            self.statusBar.showColoredMessage(reason, False, 0)
            self.progressBar.setTime(update)

        self.taskDone()

    @Slot()
    def onProgress(self, filename: str | None, update: BatchProgressUpdate | None):
        self._lastUpdate = update
        if filename:
            self._lastMessage = f"Wrote {filename}"

        if self._tabActive:
            if filename:
                self.statusBar.showMessage(self._lastMessage)

            self.progressBar.setTime(update)
            if update:
                self.progressBar.setRange(0, update.filesTotal)
                self.progressBar.setValue(update.filesProcessed)
            else:
                self.progressBar.setRange(0, 0)
                self.progressBar.setValue(0)


    @Slot()
    def onProgressMessage(self, message):
        self._lastMessage = message
        if self._tabActive:
            self.statusBar.showMessage(message)

    def taskDone(self):
        if self._tabActive:
            self.progressBar.setRange(0, 1)
            self.progressBar.reset()

        self.finished.emit()
        self._task = None
        self.btnStart.setText(f"▶  Start Batch {self.name} (All Files)")
        self.btnStartSelected.setEnabled(True)
        self.btnStartCurrent.setEnabled(True)



class BatchUtil:
    @staticmethod
    def _getHostName(name: str, cfg: dict) -> str:
        count = cfg.get("proc_count", 1)
        return f"{name} (x{count})" if count > 1 else name

    @classmethod
    def confirmStart(cls, name: str, numFiles: int, operations: list[str], needsInference: bool, parent: QtWidgets.QWidget | None = None) -> bool:
        opText = ""
        for op in filter(None, operations):
            if op.startswith("<tab>"):
                opText += f"&nbsp;&nbsp;&nbsp;&nbsp; {op[5:]}<br>"
            else:
                opText += f"• {op}<br>"

        hostsText = ""
        if needsInference:
            hosts = ", ".join(cls._getHostName(name, cfg) for name, cfg in Inference.getHosts(False))
            hostsText = f"• Use hosts if available: {hosts}<br>"

        text = "This Batch will:<br><br>" \
             +f"• Process {numFiles} files<br>" \
             + opText \
             + hostsText \
             + "<br>Do you want to continue?"

        dialog = QtWidgets.QMessageBox(parent)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle(f"Confirm Batch {name}")
        dialog.setTextFormat(Qt.TextFormat.RichText)
        dialog.setText(text)
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        return dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes

    @staticmethod
    def confirmAbort(parent: QtWidgets.QWidget | None = None) -> bool:
        dialog = QtWidgets.QMessageBox(parent)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Confirm Abort")
        dialog.setText(f"Do you really want to abort batch processing?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        return dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes
