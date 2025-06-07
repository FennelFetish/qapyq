#from typing import Generator, Callable
from PySide6.QtCore import Qt, QThreadPool, QThread, QRunnable, Signal, Slot, QObject, QMutex, QMutexLocker
from lib.util import Singleton
from config import Config
from .inference_proc import InferenceProcess, InferenceProcConfig


class Inference(metaclass=Singleton):
    class Signals(QObject):
        runTask = Signal(object)


    def __init__(self):
        self.signals = self.Signals()

        # All interaction with the interference process must happen inside this thread
        self.threadPool = QThreadPool()
        self.threadPool.setMaxThreadCount(1)

        self._procThread = QThread()
        self._procThread.setObjectName("inference")
        self._procThread.start()

        self._mutex = QMutex()
        self._proc = None


    def _createProc(self):
        host = None
        for hostName, hostCfg in Config.inferHosts.items():
            if bool(hostCfg.get("active")):
                host = hostName
                break
        else:
            raise RuntimeError("No active hosts")

        print(f"Using host: {host}")
        procCfg = InferenceProcConfig(host)
        self._proc = InferenceProcess(procCfg)
        #self._proc.processEnded.connect(self._onProcessEnded)
        self._proc.moveToThread(self._procThread)

    # @Slot()
    # def _onProcessEnded(self):
    #     with QMutexLocker(self._mutex):
    #         self._proc = None

    @property
    def proc(self):
        with QMutexLocker(self._mutex):
            if not self._proc:
                self._createProc()
            return self._proc


    def startProcess(self):
        task = InferenceTask(lambda: self.proc.start())
        self.queueTask(task)

    def quitProcess(self):
        task = InferenceTask(lambda: self.proc.stop())
        self.queueTask(task)

    def queueTask(self, task: QRunnable):
        self.threadPool.start(task)



# class ProcInfo:
#     def __init__(self, proc: InferenceProcess):
#         self.proc = proc
#         self.queuedFiles = 0
#         self.priority = 1.0

#         self.imgUploader = ImageUploader(proc)

#     def sortKey(self) -> float:
#         return self.queuedFiles * self.priority



# # Context manager?
# class InferenceSession:
#     def __init__(self, files: list[str]):
#         self.files = files
#         self.procs: list[ProcInfo] = list()
#         self.checkFunc: Callable[[str], bool] = None

#     def getFreeProc(self):
#         return min(self.procs, key=ProcInfo.sortKey)

#     def iterFiles(self) -> Generator[tuple[InferenceProcess, str]]:
#         for file in self.files:
#             if not self.checkFunc(file):
#                 continue

#             proc = self.getFreeProc()
#             proc.imgUploader.queueUpload(file)



class InferenceTask(QRunnable):
    def __init__(self, func):
        super().__init__()
        self.func = func

    @Slot()
    def run(self):
        try:
            self.func()
        except Exception as ex:
            print("Error in inference thread:")
            print(ex)



class ImageUploader(QObject):
    uploadChunk = Signal()
    imageDone = Signal(str)

    def __init__(self, files: list[str]) -> None:
        super().__init__()
        if not files:
            return

        self.files = files
        self.fileIndex = 0
        self.cachedFiles = 0
        self.cacheSize = 8

        self._currentFile = None

        self._thread = QThread()
        self._thread.setObjectName("image-uploader")
        self._thread.start()
        self._thread.finished.connect(lambda: print(">>>>>>>>>>>> upload thread finished"))
        self.moveToThread(self._thread)

        self.inferProc = Inference().proc
        self.inferProc.start()

        self.imageDone.connect(self._imageDone, Qt.ConnectionType.QueuedConnection)
        self.uploadChunk.connect(self._uploadChunk, Qt.ConnectionType.QueuedConnection)
        self._queueFile(direct=True)

    @Slot()
    def _queueFile(self, direct=False):
        if self._currentFile is not None:
            return
        if self.fileIndex >= len(self.files):
            return
        if self.cachedFiles >= self.cacheSize:
            return

        imgPath = self.files[self.fileIndex]
        self._currentFile = UploadState(imgPath)

        self.fileIndex += 1
        self.cachedFiles += 1

        if direct:
            self._uploadChunk()
        else:
            self.uploadChunk.emit()

    @Slot()
    def _uploadChunk(self):
        assert self._currentFile is not None
        chunk, finished = self._currentFile.getNextChunk()
        self.inferProc.cacheImage(self._currentFile.imgPath, chunk, len(self._currentFile._data))
        if finished:
            self._currentFile = None
            self._queueFile()
        else:
            self.uploadChunk.emit()

    @Slot()
    def _imageDone(self, file: str):
        self.cachedFiles -= 1
        self.inferProc.uncacheImage(file)
        if self.cachedFiles <= 0 and self.fileIndex >= len(self.files):
            print("ImageUploader: Exit thread")
            self._thread.quit()
        else:
            self._queueFile()


class UploadState:
    CHUNK_SIZE = 1024 * 128

    def __init__(self, imgPath: str):
        self.imgPath = imgPath
        self._end = 0

        with open(imgPath, "rb") as file:
            self._data = file.read()

    def getNextChunk(self) -> tuple[bytes, bool]:
        start = self._end
        self._end = start + self.CHUNK_SIZE
        chunk = self._data[start:self._end]
        finished = self._end >= len(self._data)
        return chunk, finished
