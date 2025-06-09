import traceback, time
from typing import Iterable, Callable, Any
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker
from infer.inference import Inference
from lib.filelist import FileList


class BatchTask(QRunnable):
    class Signals(QObject):
        progress = Signal(str, object)  # file, TimeUpdate
        progressMessage = Signal(str)   # message
        done = Signal(object)           # TimeUpdate
        fail = Signal(str, object)      # error message, TimeUpdate


    def __init__(self, name: str, log: Callable, filelist: FileList):
        super().__init__()
        self.setAutoDelete(False)
        self.signals = BatchTask.Signals()

        self.name     = name
        self._mutex   = QMutex()
        self._aborted = False

        self._indentLogs = False
        self.log = self._wrapLogFunc(log)

        self.files = filelist.getFiles().copy()
        if len(self.files) == 0 and filelist.currentFile:
            self.files.append(filelist.currentFile)

    def _wrapLogFunc(self, log: Callable):
        def logIndent(line: str):
            if self._indentLogs:
                line = "  " + line
            log(line)

        return logIndent


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
            self.processAll((file,) for file in self.files)

        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            errorMessage = f"Error during batch {self.name}: {str(ex)}"
            self.log(errorMessage)
            self.signals.fail.emit(errorMessage, None)
        finally:
            self.runCleanup()


    def processAll(self, processFileArgs: Iterable[tuple]):
        numFiles = len(self.files)
        numFilesDone = 0
        numFilesSkipped = 0

        timeAvg = TimeAverage()
        update = BatchProgressUpdate(timeAvg, numFiles, 0, 0)
        self.signals.progress.emit(None, update)
        timeAvg.init()

        for fileNr, (imgFile, *args) in enumerate(processFileArgs):
            if self.isAborted():
                abortMessage = f"Batch {self.name} aborted after {fileNr} files{update.getSkippedText(numFiles-fileNr)}"
                self.log(abortMessage)
                self.signals.fail.emit(abortMessage, update.finalize())
                return

            self.log(f"Processing: {imgFile}")
            outputFile = None

            try:
                self._indentLogs = True
                outputFile = self.runProcessFile(imgFile, *args)
                if not outputFile:
                    self.log(f"Skipped")
                    numFilesSkipped += 1
            except Exception as ex:
                outputFile = None
                self.log(f"WARNING: {str(ex)}")
                traceback.print_exc()
            finally:
                self._indentLogs = False
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
    def __init__(self, name: str, log: Callable, filelist: FileList):
        super().__init__(name, log, filelist)

    @Slot()
    def run(self):
        try:
            self.log(f"=== Starting batch {self.name} ===")
            self.signals.progressMessage.emit(f"Starting batch {self.name} ...")
            self.signals.progress.emit(None, None)

            with Inference().createSession() as session:
                session.prepare(self.runPrepare, lambda: self.signals.progressMessage.emit("Processing ..."))
                self.processAll(session.queueFiles(self.files, self.runCheckFile, all=True))

        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            errorMessage = f"Error during batch {self.name}: {str(ex)}"
            self.log(errorMessage)
            self.signals.fail.emit(errorMessage, None)
        finally:
            self.runCleanup()


    def runPrepare(self, proc):
        pass

    def runCheckFile(self, imgFile: str, proc) -> Callable | None:
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



class BatchSignalHandler(QObject):
    finished = Signal()

    def __init__(self, statusBar, progressBar, task: BatchTask):
        super().__init__()

        from lib.qtlib import ColoredMessageStatusBar
        self.statusBar: ColoredMessageStatusBar = statusBar

        from .batch_container import BatchProgressBar
        self.progressBar: BatchProgressBar = progressBar
        self.progressBar.resetTime()

        task.signals.progress.connect(self.onProgress)
        task.signals.progressMessage.connect(self.onProgressMessage)
        task.signals.done.connect(self.onFinished)
        task.signals.fail.connect(self.onFail)

    @Slot()
    def onFinished(self, update: BatchProgressUpdate):
        self.statusBar.showColoredMessage(f"Processed {update.filesTotal} files{update.getSkippedText()}", True, 0)
        self.progressBar.setTime(update)
        self.taskDone()

    @Slot()
    def onFail(self, reason, update: BatchProgressUpdate | None):
        self.statusBar.showColoredMessage(reason, False, 0)
        self.progressBar.setTime(update)
        self.taskDone()

    @Slot()
    def onProgress(self, filename, update: BatchProgressUpdate | None):
        if update:
            self.progressBar.setRange(0, update.filesTotal)
            self.progressBar.setValue(update.filesProcessed)
        else:
            self.progressBar.setRange(0, 0)
            self.progressBar.setValue(0)

        self.progressBar.setTime(update)
        if filename:
            self.statusBar.showMessage("Wrote " + filename)

    @Slot()
    def onProgressMessage(self, message):
        self.statusBar.showMessage(message)

    def taskDone(self):
        self.progressBar.setRange(0, 1)
        self.progressBar.reset()
        self.finished.emit()



class BatchUtil:
    @staticmethod
    def confirmStart(name: str, numFiles: int, operations: list[str], parent: QtWidgets.QWidget | None = None) -> bool:
        opText = ""
        for op in filter(None, operations):
            if op.startswith("<tab>"):
                opText += f"&nbsp;&nbsp;&nbsp;&nbsp; {op[5:]}<br>"
            else:
                opText += f"• {op}<br>"

        text = f"This Batch will:<br><br>" \
               f"• Process {numFiles} files<br>" \
               + opText + \
                "<br>Do you want to continue?"

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
