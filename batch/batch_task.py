from typing import Callable
from PySide6.QtCore import Signal, Slot, QRunnable, QObject, QMutex, QMutexLocker
import traceback
from filelist import FileList


class BatchTask(QRunnable):
    class Signals(QObject):
        progress = Signal(int, int, str)  # current, total, file
        progressMessage = Signal(str)     # message
        done = Signal(int)                # total
        fail = Signal(str)                # error message


    def __init__(self, name: str, log: Callable, filelist: FileList):
        super().__init__()
        self._mutex   = QMutex()
        self._aborted = False

        self.signals  = BatchTask.Signals()
        self.name     = name
        self.log      = log

        self.files = list(filelist.files)
        if len(self.files) == 0 and filelist.currentFile:
            self.files.append(filelist.currentFile)


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
            self.signals.progress.emit(0, 0, None)

            self.runPrepare()
            self.signals.progressMessage.emit("Processing ...")
            self.processAll()
        except Exception as ex:
            print(f"Error during batch {self.name}:")
            traceback.print_exc()

            errorMessage = f"Error during batch {self.name}: {str(ex)}"
            self.log(errorMessage)
            self.signals.fail.emit(errorMessage)


    def processAll(self):
        numFiles = len(self.files)
        self.signals.progress.emit(0, numFiles, None)

        for fileNr, imgFile in enumerate(self.files):
            if self.isAborted():
                abortMessage = f"Batch {self.name} aborted after {fileNr} files"
                self.log(abortMessage)
                self.signals.fail.emit(abortMessage)
                return

            self.log(f"Processing: {imgFile}")
            outputFile = self.runProcessFile(imgFile)
            self.signals.progress.emit(fileNr+1, numFiles, outputFile)

        self.log(f"Batch {self.name} finished, processed {numFiles} files")
        self.signals.done.emit(numFiles)


    def runPrepare(self):
        pass

    def runProcessFile(self, imgFile: str) -> str:
        pass
