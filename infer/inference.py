from __future__ import annotations
from enum import Enum
from typing import Iterable, Generator, Callable, Any
from collections import deque
from queue import Queue, Empty
from threading import Condition
from PySide6.QtCore import Qt, QThreadPool, QThread, Signal, Slot, QObject, QMutex, QMutexLocker
from lib.util import Singleton
from config import Config
from .inference_proc import InferenceProcess, InferenceProcConfig, ProcFuture, InferenceException


class Inference(metaclass=Singleton):
    def __init__(self):
        self._mutex = QMutex()
        self._procs: dict[str, InferenceProcess] = dict()
        self._procsInUse: set[InferenceProcess] = set()


    def createSession(self, maxProcesses: int = -1) -> InferenceSession:
        prioHosts = sorted(Config.inferHosts.items(), key=lambda item: item[1].get("priority", 1.0), reverse=True)

        procStates: list[ProcState] = []
        hostnames = []
        with QMutexLocker(self._mutex):
            for hostName, hostCfg in prioHosts:
                if not bool(hostCfg.get("active")):
                    continue

                proc = self._procs.get(hostName)
                if proc in self._procsInUse:
                    continue
                if not proc:
                    proc = self._procs[hostName] = self._createProc(hostName)

                self._procsInUse.add(proc)

                priority = float(hostCfg.get("priority", 1.0))
                queueSize = max(int(hostCfg.get("queue_size", 1)), 1)

                procState = ProcState(proc, priority, queueSize)
                procStates.append(procState)
                hostnames.append(hostName)

                maxProcesses -= 1
                if maxProcesses == 0:
                    break

        if not procStates:
            raise RuntimeError("No free inference hosts available")

        hostnames = ", ".join(hostnames)
        print(f"Starting inference session with hosts: {hostnames}")
        sess = InferenceSession(procStates)
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
        proc.processStartFailed.connect(self._onProcessStartFailed, Qt.ConnectionType.QueuedConnection)
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

    @Slot()
    def _onProcessStartFailed(self, proc: InferenceProcess):
        with QMutexLocker(self._mutex):
            self._procsInUse.discard(proc)
        self._onProcessEnded(proc)


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



# Queuing: Pass files that pass the check to ImageUploader immediately.
#          But only queue inference when last one from this ProcState has returned a result (easier aborting).
class ProcState:
    def __init__(self, proc: InferenceProcess, priority: float, queueSize: int):
        self.proc = proc
        self.priority = priority
        self.queueSize = queueSize

        self.queuedFiles = set()
        self.taskQueue = deque[tuple[str, Callable]]()

        if proc.procCfg.remote:
            self.imgUploader = ImageUploader(proc)
        else:
            self.imgUploader = None

    @property
    def hostName(self):
        return self.proc.procCfg.hostName

    def sortKey(self):
        return len(self.queuedFiles), -self.priority

    def hasSpace(self) -> bool:
        return len(self.queuedFiles) < self.queueSize

    def queueFile(self, file: str, taskFunc: Callable) -> bool:
        self.queuedFiles.add(file)
        self.taskQueue.append((file, taskFunc))
        if self.imgUploader:
            self.imgUploader.queueFile.emit(file)

        return len(self.queuedFiles) == 1

    def fileDone(self, file: str):
        try:
            self.queuedFiles.remove(file)
            if self.imgUploader:
                self.imgUploader.imageDone.emit(file)
        except KeyError:
            # When file wasn't queued on host (skipped files)
            pass

    def getNextTask(self) -> tuple[str, Callable] | None:
        try:
            return self.taskQueue.popleft()
        except IndexError:
            return None

    def shutdown(self):
        if self.imgUploader:
            self.imgUploader.shutdown()
            if self.proc.ready:
                self.proc.clearImageCache()



class InferenceSetupException(Exception):
    def __init__(self, hostName: str, message: str, errorType: str):
        host = f"Setup failed ({hostName}): " if hostName else ""
        errorType = f" ({errorType})" if errorType else ""
        msg = f"{host}{message}{errorType}"
        super().__init__(msg)



class QueueItem:
    class Type(Enum):
        FileResult  = 0
        ProcReady   = 1
        Chain       = 2
        Error       = 3

    def __init__(self, type: Type):
        self.type = type
        self.procState: ProcState           = None
        self.file: str                      = None
        self.results: list                  = None
        self.exception: Exception | None    = None
        self.chain: InferenceChain          = None

    @classmethod
    def fileResult(cls, procState: ProcState, file: str, results: list, exception: Exception | None = None):
        item = QueueItem(cls.Type.FileResult)
        item.procState = procState
        item.file = file
        item.results = results
        item.exception = exception
        return item

    @classmethod
    def processReady(cls, procState: ProcState):
        item = QueueItem(cls.Type.ProcReady)
        item.procState = procState
        return item

    @classmethod
    def error(cls, exception: Exception):
        item = QueueItem(cls.Type.Error)
        item.exception = exception
        return item

    @classmethod
    def inferenceChain(cls, procState: ProcState, file: str, chain: InferenceChain):
        item = QueueItem(cls.Type.Chain)
        item.procState = procState
        item.file = file
        item.chain = chain
        return item



# Only one thread may interact with each inference process at the same time.
class InferenceSession:
    def __init__(self, procStates: list[ProcState]):
        self.procs: list[ProcState] = procStates
        self.readyProcs: set[ProcState] = set()
        self.failedProcs: set[ProcState] = set()

        self._condProc = Condition()
        self._prepared = False
        self._aborted = False

        self._queue = Queue[QueueItem]()

    def __enter__(self):
        return self

    def __exit__(self, excType, excVal, excTraceback):
        Inference().releaseSession(self)
        return False


    def abort(self):
        with self._condProc:
            self._aborted = True


    def getFreeProc(self):
        with self._condProc:
            while not self.readyProcs:
                if len(self.failedProcs) >= len(self.procs):
                    raise InferenceSetupException("", "Failed to start inference hosts", "")
                self._condProc.wait()

            return min(self.readyProcs, key=ProcState.sortKey)

    @Slot()
    def _onProcReady(self, proc: InferenceProcess, state: bool):
        with self._condProc:
            if procState := next((p for p in self.procs if p.proc == proc), None):
                if state:
                    self.readyProcs.add(procState)
                    self._queue.put_nowait(QueueItem.processReady(procState))
                else:
                    procState.shutdown()
                    self.failedProcs.add(procState)

                    self._aborted = True
                    ex = InferenceSetupException(procState.hostName, "Process failed to start (wrong command?)", "")
                    self._queue.put_nowait(QueueItem.error(ex))

            self._condProc.notify_all()

    def _onProcPrepared(self, procState: ProcState, future: ProcFuture, prepareCallback: Callable | None):
        try:
            # Only handle first to prevent further callback execution after failure
            with self._condProc:
                if self._prepared or self._aborted:
                    return
                self._prepared = True

            future.result()

            if prepareCallback:
                prepareCallback()
        except Exception as ex:
            with self._condProc:
                procState.shutdown()
                self.failedProcs.add(procState)

            if isinstance(ex, InferenceException):
                ex = InferenceSetupException(procState.hostName, ex.message, ex.errorType)
            self._queue.put_nowait(QueueItem.error(ex))


    def prepare(self, prepareFunc: Callable[[InferenceProcess], None] | None = None, prepareCallback: Callable | None = None):
        for procState in self.procs:
            proc = procState.proc
            proc.processReady.connect(self._onProcReady)
            proc.start(wait=True)

            if proc.procCfg.remote:
                proc.clearImageCache()

            with proc:
                if prepareFunc:
                    prepareFunc(proc)

                callback = lambda future, procState=procState: self._onProcPrepared(procState, future, prepareCallback)
                for future in proc.getRecordedFutures():
                    future.setCallback(callback)


    # Called once per file, executes the check function.
    def _tryQueueFile(self, file: str, procState: ProcState, checkFunc: Callable[[str, InferenceProcess], Callable | None], all: bool) -> bool:
        if taskFunc := checkFunc(file, procState.proc):
            # InferenceChain.result comes here (when no task was queued but result was returned directly)
            if isinstance(taskFunc, InferenceChain):
                if taskFunc.exec(self, procState, file, all):
                    return True
            else:
                if procState.queueFile(file, taskFunc):
                    self._queueNextTask(procState, all)
                return True

        if all:
            self._queue.put_nowait(QueueItem.fileResult(procState, file, []))
            return True
        return False


    def _queueNextTask(self, procState: ProcState, all: bool):
        if task := procState.getNextTask():
            self._queueTask(task[0], task[1], procState, all)

    def _queueTask(self, file: str, taskFunc: Callable[[], InferenceChain | None], procState: ProcState, all: bool):
        with procState.proc as proc:
            # Execute task while recording its futures
            chain = taskFunc()
            if futures := proc.getRecordedFutures():
                if chain:
                    # InferenceChain.resultCallback comes here
                    assert chain.callback is not None
                    resultCb = ChainCallback(chain.callback, self, procState, file, len(futures))
                else:
                    resultCb = ResultCallback(self, procState, file, len(futures))

                for future in futures:
                    future.setCallback(resultCb)
            elif all:
                self._queue.put_nowait(QueueItem.fileResult(procState, file, []))


    def _queueGet(self) -> QueueItem:
        while True:
            try:
                if result := self._queue.get(timeout=5.0):
                    return result
            except Empty:
                pass

            with self._condProc:
                if self._aborted:
                    return QueueItem.error(TimeoutError("Aborted"))


    def queueFiles(
        self, files: Iterable[str], checkFunc: Callable[[str, InferenceProcess], Callable | None], all=False
    ) -> Generator[tuple[str, list[Any], Exception | None]]:
        numQueued = 0
        it = iter(files)

        def fillProcQueue(procState: ProcState):
            nonlocal numQueued
            while procState.hasSpace() and (file := next(it, None)):
                try:
                    if self._tryQueueFile(file, procState, checkFunc, all):
                        numQueued += 1
                except Exception as ex:
                    self._queue.put_nowait(QueueItem.fileResult(procState, file, [], ex))
                    numQueued += 1

        # Queue initial files
        fillProcQueue(self.getFreeProc())

        # Handle inference results and other queued tasks
        while numQueued > 0:
            item = self._queueGet()
            match item.type:
                case QueueItem.Type.FileResult:
                    item.procState.fileDone(item.file)
                    yield item.file, item.results, item.exception

                    numQueued -= 1
                    self._queueNextTask(item.procState, all)
                    fillProcQueue(item.procState)

                case QueueItem.Type.ProcReady:
                    fillProcQueue(item.procState)

                case QueueItem.Type.Chain:
                    try:
                        # InferenceChain.queue and InfereChain.forwardResult come here
                        item.chain.exec(self, item.procState, item.file, all)
                    except Exception as ex:
                        self._queue.put_nowait(QueueItem.fileResult(item.procState, item.file, [], ex))

                case QueueItem.Type.Error:
                    raise item.exception



class ResultCallback:
    def __init__(self, sess: InferenceSession, procState: ProcState, file: str, resultCount: int):
        self.sess = sess
        self.procState = procState
        self.file = file
        self.remaining = resultCount
        self.results = []

    def __call__(self, future: ProcFuture):
        try:
            result = future.result()
            self.results.append(result)
        except Exception as ex:
            self.sess._queue.put_nowait(QueueItem.fileResult(self.procState, self.file, [], ex))
            return

        self.remaining -= 1
        if self.remaining <= 0:
            self.onDone()

    def onDone(self):
        self.sess._queue.put_nowait(QueueItem.fileResult(self.procState, self.file, self.results))


class ChainCallback(ResultCallback):
    def __init__(self, func: Callable, sess: InferenceSession, procState: ProcState, file: str, resultCount: int):
        super().__init__(sess, procState, file, resultCount)
        self.func = func

    def onDone(self):
        # Forward the callback to queue for execution in same thread
        chain = InferenceChain.forwardResult(self.func, self.results)
        self.sess._queue.put_nowait(QueueItem.inferenceChain(self.procState, self.file, chain))



class InferenceChain:
    def __init__(self):
        self.callback: Callable = None
        self._checkFunc: Callable = None
        self._fwdFunc: Callable = None
        self._result: Any = None
        self.exec: Callable[[InferenceSession, ProcState, str, bool], bool] = None

    @staticmethod
    def queue(checkFunc: Callable[[str, InferenceProcess], None]) -> InferenceChain:
        'Result callbacks return `queue`-InferenceChain.'
        chain = InferenceChain()
        chain._checkFunc = checkFunc
        chain.exec = chain._execQueue
        return chain

    @staticmethod
    def resultCallback(func: Callable) -> InferenceChain:
        'Queue functions return `resultCallback`-InferenceChain.'
        chain = InferenceChain()
        chain.callback = func
        return chain

    @staticmethod
    def forwardResult(func: Callable, result: Any) -> InferenceChain:
        'ChainCallbacks enqueue `forwardResult`-InferenceChain.'
        chain = InferenceChain()
        chain._fwdFunc = func
        chain._result = result
        chain.exec = chain._execForwardResult
        return chain

    @staticmethod
    def result(result: Any) -> InferenceChain:
        'Processing functions return `result`-InferenceChain.'
        chain = InferenceChain()
        chain._result = result
        chain.exec = chain._execResult
        return chain


    def _execQueue(self, session: InferenceSession, procState: ProcState, file: str, all: bool) -> bool:
        if queueFunc := self._checkFunc(file, procState.proc):
            if isinstance(queueFunc, InferenceChain):
                queueFunc.exec(session, procState, file, all)
            else:
                session._queueTask(file, queueFunc, procState, all)
            return True
        return False

    def _execForwardResult(self, session: InferenceSession, procState: ProcState, file: str, all: bool) -> bool:
        if chain := self._fwdFunc(self._result):
            return chain.exec(session, procState, file, all)
        return False

    def _execResult(self, session: InferenceSession, procState: ProcState, file: str, all: bool) -> bool:
        session._queue.put_nowait(QueueItem.fileResult(procState, file, [self._result]))
        return True



class ImageUploader(QObject):
    queueFile = Signal(str)
    imageDone = Signal(str)
    uploadChunk = Signal()

    def __init__(self, proc: InferenceProcess) -> None:
        super().__init__()

        self.queue = deque[str]()
        self._currentFile: UploadState | None = None

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
