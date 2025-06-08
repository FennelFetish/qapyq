from __future__ import annotations
from typing import Iterable, Generator, Callable, Any
from collections import deque
from queue import Queue
from PySide6.QtCore import Qt, QThreadPool, QThread, QRunnable, Signal, Slot, QObject, QMutex, QMutexLocker
from lib.util import Singleton
from config import Config
from .inference_proc import InferenceProcess, InferenceProcConfig, ProcFuture


class Inference(metaclass=Singleton):
    class Signals(QObject):
        #runTask = Signal(object)
        pass


    def __init__(self):
        #self.signals = self.Signals()

        self._mutex = QMutex()
        self._procs: dict[str, InferenceProcess] = dict()
        self._procsInUse: set[InferenceProcess] = set()


    def createSession(self) -> InferenceSession:
        procs: list[InferenceProcess] = []
        with QMutexLocker(self._mutex):
            for hostName, hostCfg in Config.inferHosts.items():
                if not bool(hostCfg.get("active")):
                    continue

                proc = self._procs.get(hostName)
                if proc in self._procsInUse:
                    continue
                if not proc:
                    proc = self._procs[hostName] = self._createProc(hostName)

                # TODO: Update proc config / or remove process
                self._procsInUse.add(proc)
                procs.append(proc)

        if not procs:
            raise RuntimeError("No free inference processes available")

        hostnames = ", ".join(p.procCfg.hostName for p in procs)
        print(f"Starting inference session with hosts: {hostnames}")
        sess = InferenceSession(procs)
        return sess

    def releaseSession(self, session: InferenceSession):
        with QMutexLocker(self._mutex):
            for procState in session.procs:
                procState.shutdown()
                self._procsInUse.discard(procState.proc)


    def _createProc(self, hostName: str) -> InferenceProcess:
        procCfg = InferenceProcConfig(hostName)
        proc = InferenceProcess(procCfg)
        proc.processEnded.connect(self._onProcessEnded, Qt.ConnectionType.QueuedConnection)
        return proc

    @Slot()
    def _onProcessEnded(self, proc: InferenceProcess):
        with QMutexLocker(self._mutex):
            if proc in self._procsInUse:
                return

        def remove():
            proc.shutdown()
            with QMutexLocker(self._mutex):
                self._procs.pop(proc.procCfg.hostName, None)

        QThreadPool.globalInstance().start(remove)


    # TODO: Remove method
    @property
    def proc(self):
        from host.host_window import LOCAL_NAME
        with QMutexLocker(self._mutex):
            proc = self._procs.get(LOCAL_NAME)
            if not proc:
                self._procs[LOCAL_NAME] = proc = self._createProc(LOCAL_NAME)
            return proc

    # TODO: Remove method?
    def queueTask(self, task: QRunnable):
        QThreadPool.globalInstance().start(task)


    def quitProcesses(self) -> list[str]:
        names = []
        with QMutexLocker(self._mutex):
            for proc in filter(lambda p: p not in self._procsInUse, self._procs.values()):
                names.append(proc.procCfg.hostName)
                proc.execAwaitable.emit(lambda proc=proc: proc.stop())
        return names

    def killProcesses(self) -> list[str]:
        names = []
        with QMutexLocker(self._mutex):
            for proc in self._procs.values():
                names.append(proc.procCfg.hostName)
                proc.execAwaitable.emit(lambda proc=proc: proc.kill())
        return names



class ProcState:
    def __init__(self, proc: InferenceProcess):
        self.proc = proc
        self.queuedFiles = set()
        self.priority = 1.0

        if proc.procCfg.remote:
            self.imgUploader = ImageUploader(proc)
        else:
            self.imgUploader = None

    def sortKey(self):
        return len(self.queuedFiles), -self.priority

    def queueFile(self, file: str):
        print(f"ProcState.queueFile: {file} ({self.proc.procCfg.hostName})")
        self.queuedFiles.add(file)
        if self.imgUploader:
            self.imgUploader.queueFile.emit(file)

    def fileDone(self, file: str):
        self.queuedFiles.discard(file)
        if self.imgUploader:
            self.imgUploader.imageDone.emit(file)

    def shutdown(self):
        if self.imgUploader:
            for file in self.queuedFiles:
                self.imgUploader.imageDone.emit(file)
            self.imgUploader.shutdown()



# Only one thread may interact with each inference process at the same time.
class InferenceSession:
    def __init__(self, procs: list[InferenceProcess]):
        self.procs: list[ProcState] = [ProcState(proc) for proc in procs]
        self.queueSize = 16
        self._resultQueue = Queue[tuple[ProcState, str, list[Any], Exception | None]]()

        # TODO: Make a callback for setting status bar text when models are ready.
        # self.readyProcs: list[ProcState] = list()
        # self._condProc = Condition()

    def __enter__(self):
        return self

    def __exit__(self, excType, excVal, excTraceback):
        Inference().releaseSession(self)
        return False


    # def getFreeProc(self):
    #     with self._condProc:
    #         while not self.readyProcs:
    #             self._condProc.wait()
    #         return min(self.readyProcs, key=ProcState.sortKey)

    def getFreeProc(self):
        return min(self.procs, key=ProcState.sortKey)

    def prepareProcs(self, prepareFunc: Callable[[InferenceProcess], None]):
        for procState in self.procs:
            proc = procState.proc
            with proc:
                proc.start(wait=True)
                prepareFunc(proc)

                # for future in proc.getRecordedFutures():
                #     future.setCallback(lambda future, procState=procState: self._onProcReady(future, procState))

    # def _onProcReady(self, future: ProcFuture, procState: ProcState):
    #     with self._condProc:
    #         self.readyProcs.append(procState)
    #         self._condProc.notify_all()


    def _queueFile(self, file: str, queueFunc: Callable[[str, InferenceProcess], None]) -> bool:
        procState = self.getFreeProc()
        procState.queueFile(file)

        proc = procState.proc
        with proc:
            queueFunc(file, procState.proc)
            futures = proc.getRecordedFutures()
            if not futures:
                return False

            resultCb = ResultCallback(self, procState, file, len(futures))
            for future in futures:
                future.setCallback(resultCb)

        return True


    def iterFiles(self, files: Iterable[str], queueFunc: Callable[[str, InferenceProcess], None]) -> Generator[tuple[str, list[Any]]]:
        numQueued = 0
        it = iter(files)

        # Queue initial files
        for _ in range(len(self.procs) * self.queueSize):
            if (file := next(it, None)) and self._queueFile(file, queueFunc):
                numQueued += 1

        # Handle inference results
        while numQueued > 0 and (result := self._resultQueue.get()):
            numQueued -= 1
            procState, file, res, exception = result

            if exception:
                raise exception

            procState.fileDone(file)
            yield file, res

            if file := next(it, None):
                if self._queueFile(file, queueFunc):
                    numQueued += 1



class ResultCallback:
    def __init__(self, sess: InferenceSession, procState: ProcState, file: str, resultCount: int):
        self.sess = sess
        self.procState = procState
        self.file = file
        self.remaining = resultCount
        self.results = []

    def __call__(self, future: ProcFuture):
        exception = None
        try:
            result = future.result()
            self.results.append(result)
        except Exception as ex:
            exception = ex
            self.results.append(None)

        self.remaining -= 1
        if self.remaining <= 0:
            self.sess._resultQueue.put_nowait((self.procState, self.file, self.results, exception))



class ImageUploader(QObject):
    queueFile = Signal(str)
    imageDone = Signal(str)
    uploadChunk = Signal()

    def __init__(self, proc: InferenceProcess) -> None:
        super().__init__()

        self.queue = deque[str]()
        self._currentFile = None

        self._thread = QThread()
        self._thread.setObjectName("image-uploader")
        self._thread.start()
        self.moveToThread(self._thread)

        self.inferProc = proc

        self.queueFile.connect(self._queueFile, Qt.ConnectionType.QueuedConnection)
        self.imageDone.connect(self._imageDone, Qt.ConnectionType.QueuedConnection)
        self.uploadChunk.connect(self._uploadChunk, Qt.ConnectionType.QueuedConnection)

    @Slot()
    def _queueFile(self, file: str):
        self.queue.append(file)
        self._queueNextFile(direct=True)

    def _queueNextFile(self, direct=False):
        if self._currentFile is not None:
            return

        try:
            imgPath = self.queue.popleft()
            self._currentFile = UploadState(imgPath)
        except IndexError:
            return

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
            self._queueNextFile()
        else:
            self.uploadChunk.emit()

    @Slot()
    def _imageDone(self, file: str):
        self.inferProc.uncacheImage(file)

    def shutdown(self):
        self._thread.quit()
        self._thread.wait()


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
