from PySide6.QtCore import Qt, QThreadPool, QThread, QRunnable, Signal, Slot, QObject
from lib.util import Singleton


class Inference(metaclass=Singleton):
    class Signals(QObject):
        runTask = Signal(object)


    def __init__(self):
        # All interaction with the interference process must happen inside this thread
        # self.threadPool = QThreadPool()
        # self.threadPool.setMaxThreadCount(1)

        self.signals = self.Signals()

        self._thread = QThread()
        self._thread.setObjectName("inference")
        self._thread.start()

        from .inference_proc import InferenceProcess
        self.proc = InferenceProcess()
        self.proc.moveToThread(self._thread)

    def startProcess(self):
        task = InferenceTask(lambda: self.proc.start())
        self.queueTask(task)

    def quitProcess(self):
        task = InferenceTask(lambda: self.proc.stop())
        self.queueTask(task)

    def queueTask(self, task: QRunnable):
        #self.threadPool.start(task)
        QThreadPool.globalInstance().start(task)



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
