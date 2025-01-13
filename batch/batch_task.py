from typing import Callable
from PySide6.QtCore import Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker
import traceback, time
from lib.filelist import FileList


class BatchTask(QRunnable):
    class Signals(QObject):
        progress = Signal(str, object)  # file, TimeUpdate
        progressMessage = Signal(str)   # message
        done = Signal(object)           # TimeUpdate
        fail = Signal(str, object)      # error message, TimeUpdate


    def __init__(self, name: str, log: Callable, filelist: FileList):
        super().__init__()
        self._mutex   = QMutex()
        self._aborted = False

        self.signals  = BatchTask.Signals()
        self.name     = name

        self._indentLogs = False
        self.log = self._wrapLogFunc(log)

        self.files = list(filelist.getFiles())
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
            self.processAll()
        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            errorMessage = f"Error during batch {self.name}: {str(ex)}"
            self.log(errorMessage)
            self.signals.fail.emit(errorMessage, None)
        finally:
            self.runCleanup()


    def processAll(self):
        numFiles = len(self.files)
        numFilesDone = 0

        timeAvg = TimeAverage()
        update = BatchProgressUpdate(timeAvg, numFiles, 0)
        self.signals.progress.emit(None, update)
        timeAvg.init()

        for fileNr, imgFile in enumerate(self.files):
            if self.isAborted():
                abortMessage = f"Batch {self.name} aborted after {fileNr} files"
                self.log(abortMessage)
                self.signals.fail.emit(abortMessage, update.finalize())
                return

            self.log(f"Processing: {imgFile}")

            try:
                self._indentLogs = True
                outputFile = self.runProcessFile(imgFile)
                if not outputFile:
                    self.log(f"Skipped")
            except Exception as ex:
                outputFile = None
                self.log(f"WARNING: {str(ex)}")
                traceback.print_exc()
            finally:
                self._indentLogs = False
                numFilesDone += 1
                timeAvg.update()
                update = BatchProgressUpdate(timeAvg, numFiles, numFilesDone)
                self.signals.progress.emit(outputFile, update)

        self.log(f"Batch {self.name} finished, processed {numFiles} files in {update.timeSpent:.2f} seconds")
        self.signals.done.emit(update.finalize())


    def runPrepare(self):
        pass

    def runProcessFile(self, imgFile: str) -> str | None:
        return None

    def runCleanup(self):
        pass



class TimeAverage:
    HISTORY_SIZE = 20
    NS_IN_MS = 1000000

    def __init__(self):
        self.tLast = 0
        self.history: list[int] = [0] * self.HISTORY_SIZE
        self.idxHistory = 0

        self.num = 0
        self.sumMs = 0
        self.totalMs = 0

    def init(self):
        self.tLast = time.monotonic_ns()

    def update(self):
        now = time.monotonic_ns()
        tDiff = (now - self.tLast) // self.NS_IN_MS
        self.tLast = now

        if self.num < self.HISTORY_SIZE:
            self.num += 1
        else:
            self.sumMs -= self.history[self.idxHistory]

        self.history[self.idxHistory] = tDiff
        self.sumMs += tDiff
        self.totalMs += tDiff

        self.idxHistory += 1
        if self.idxHistory >= self.HISTORY_SIZE:
            self.idxHistory = 0

    def getAvgTime(self) -> float:
        if self.num == 0:
            return 0.0
        return self.sumMs / self.num / 1000.0

    def getTotalTime(self) -> float:
        return self.totalMs / 1000.0



class BatchProgressUpdate:
    def __init__(self, timeAvg: TimeAverage, numFilesTotal: int, numFilesProcessed: int):
        self.filesTotal     = numFilesTotal
        self.filesProcessed = numFilesProcessed

        self.timePerFile    = timeAvg.getAvgTime()
        self.timeRemaining  = self.timePerFile * (numFilesTotal - numFilesProcessed)
        self.timeSpent      = timeAvg.getTotalTime()

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
        self.statusBar.showColoredMessage(f"Processed {update.filesTotal} files", True, 0)
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
