from __future__ import annotations
import sys, struct, msgpack, copy, traceback
from typing import Any, Callable
from threading import Condition
from PySide6.QtCore import Qt, Slot, Signal, QObject, QThread, QProcess, QProcessEnvironment, QByteArray, QMutex, QMutexLocker
from host.protocol import Protocol, Service
from host.host_window import LOCAL_NAME
from config import Config


class InferenceException(Exception):
    def __init__(self, hostName: str, message: str, errorType: str = None):
        self.hostName = hostName
        self.message = message
        self.errorType = errorType

        host = f" ({hostName})" if hostName else ""
        errorType = f" ({errorType})" if errorType else ""
        msg = f"Error during inference{host}: {message}{errorType}"
        super().__init__(msg)



class ProcFuture:
    def __init__(self):
        self._cond = Condition()
        self._received = False
        self._result: dict | None = None
        self._exception: Exception | None = None
        self._callback: Callable | None = None

    def setCallback(self, callback: Callable[[ProcFuture], None]):
        with self._cond:
            self._callback = callback
            if not self._received:
                return

        callback(self)

    def setResult(self, result: dict | None):
        with self._cond:
            if self._received:
                return

            self._received = True
            self._result = result
            self._cond.notify_all()
            cb = self._callback

        if cb:
            cb(self)

    def setException(self, exception):
        with self._cond:
            if self._received:
                return

            self._received = True
            self._exception = exception
            self._cond.notify_all()
            cb = self._callback

        if cb:
            cb(self)

    def result(self) -> dict | None:
        with self._cond:
            while not self._received:
                self._cond.wait()

            if self._exception is not None:
                raise self._exception
            return self._result


class AwaitableFunc:
    def __init__(self, func: Callable, *args):
        self.func = func
        self.args = args
        self.future = ProcFuture()

    def __call__(self):
        try:
            self.func(*self.args)
            self.future.setResult(None)
        except Exception as ex:
            self.future.setException(ex)

    def awaitExec(self):
        self.future.result()



class InferenceProcConfig:
    def __init__(self, hostName: str, configOverride: dict | None = None):
        self.hostName = hostName

        cfgLocal = Config.inferHosts.get(LOCAL_NAME, {})
        self.localBasePath: str = cfgLocal.get("model_base_path", "")
        self.remoteBasePath: str = ""

        if hostName == LOCAL_NAME and not configOverride:
            self.remote = False
            self.hostServiceId = Service.ID.INFERENCE
            self.executable = sys.executable
            self.arguments = ["-u", "main_inference.py"] # Unbuffered pipes
        else:
            self.remote = True
            self.hostServiceId = Service.ID.HOST

            cfgRemote: dict = configOverride or Config.inferHosts.get(hostName, {})
            self.remoteBasePath = cfgRemote.get("model_base_path", "")

            import shlex
            cmd = shlex.split(cfgRemote.get("cmd", ""))
            self.executable: str = cmd[0]
            self.arguments: list[str] = cmd[1:]

        self.localBasePath = self.localBasePath.replace("\\", "/").rstrip("/")
        self.remoteBasePath = self.remoteBasePath.replace("\\", "/").rstrip("/")

    def translateConfig(self, config: dict[str, Any], keys: list[str]) -> dict:
        if self.remote and self.localBasePath and self.remoteBasePath:
            config = copy.deepcopy(config)
            self._translateModelPaths(config, keys)
        return config

    def _translateModelPaths(self, config: dict[str, Any], keys: list[str]):
        modelPath: str = None
        for key in keys:
            if modelPath := config.get(key):
                modelPath = modelPath.replace("\\", "/")
                modelPath = modelPath.removeprefix(self.localBasePath).lstrip("/")
                config[key] = f"{self.remoteBasePath}/{modelPath}"



class InferenceProcess(QObject):
    queueStart = Signal(object)
    queueWrite = Signal(int, dict, object)
    processReady = Signal(object, bool)
    processEnded = Signal(object)
    processStartFailed = Signal(object)
    execAwaitable = Signal(object)

    def __init__(self, config: InferenceProcConfig):
        super().__init__()

        self._thread = QThread()
        self._thread.setObjectName("inference-process")
        self._thread.start()
        self.moveToThread(self._thread)

        self.procCfg = config
        self.proc: QProcess = None
        self._ready: bool | None = None

        self.currentLLMConfig = dict()
        self.currentTagConfig = dict()

        # Mutex protects proc and config
        self._mutex = QMutex()

        self._readBuffer: QByteArray = None
        self._readReq = 0
        self._readLength = 0

        self._futures: dict[int, ProcFuture] = dict()
        self._nextReqId = 1  # reqId 0 for messages with no associated Future

        self.queueStart.connect(self._startProcess, Qt.ConnectionType.QueuedConnection)
        self.queueWrite.connect(self._writeMessage, Qt.ConnectionType.QueuedConnection)
        self.execAwaitable.connect(lambda func: func(), Qt.ConnectionType.QueuedConnection)

        self.record = False
        self.recordedFutures: list[ProcFuture] = list()


    @property
    def ready(self) -> bool:
        return bool(self._ready)

    def awaitTask(self, func: Callable, *args):
        task = AwaitableFunc(func, *args)
        self.execAwaitable.emit(task)
        task.awaitExec()


    def __enter__(self):
        self.record = True
        return self

    def __exit__(self, excType, excVal, excTraceback):
        self.record = False
        return False

    def getRecordedFutures(self) -> list[ProcFuture]:
        futures = self.recordedFutures
        self.recordedFutures = list()
        return futures


    def start(self, wait=True):
        if wait:
            self.awaitTask(self._startProcess)
        else:
            self.queueStart.emit(None)

    @Slot()
    def _startProcess(self):
        with QMutexLocker(self._mutex):
            if self.proc:
                if self._ready is not None:
                    self.processReady.emit(self, self._ready)
                return

            env = QProcessEnvironment.systemEnvironment()
            env.insert("NO_ALBUMENTATIONS_UPDATE", "1")
            #env.insert("VLLM_USE_V1", "1") # RuntimeError: Cannot re-initialize CUDA in forked subprocess. To use CUDA with multiprocessing, you must use the 'spawn' start method
            #env.insert("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
            env.insert("VLLM_NO_USAGE_STATS", "1")
            env.insert("VLLM_DO_NOT_TRACK", "1")

            self.proc = QProcess()
            self.proc.setProgram(self.procCfg.executable)
            self.proc.setArguments(self.procCfg.arguments)

            self.proc.setProcessEnvironment(env)
            self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
            self.proc.setReadChannel(QProcess.ProcessChannel.StandardOutput)
            self.proc.readyReadStandardOutput.connect(self._onReadyRead)
            self.proc.finished.connect(self._onProcessEnded)
            self.proc.start()

            future = ProcFuture()
            future.setCallback(self._onProcessStarted)
            self.queueWrite.emit(self.procCfg.hostServiceId, {"cmd": "echo"}, future)

            if not self.proc.waitForStarted():
                print(f"WARNING: Inference process ({self.procCfg.hostName}) failed to start (wrong command?)")
                self._ready = False
                self.processReady.emit(self, False)
                self.processStartFailed.emit(self)


    def stop(self, wait=False):
        with QMutexLocker(self._mutex):
            self.currentLLMConfig = dict()
            self.currentTagConfig = dict()

            if self.proc:
                self.queueWrite.emit(self.procCfg.hostServiceId, {"cmd": "quit"}, None)
            else:
                wait = False

        if wait:
            self.awaitTask(lambda: self.proc.waitForFinished())

    def kill(self):
        try:
            with QMutexLocker(self._mutex):
                if self.proc:
                    self.proc.kill()
        except:
            traceback.print_exc()

    def shutdown(self):
        self._thread.quit()
        self._thread.wait()


    def setupCaption(self, config: dict):
        config = self.procCfg.translateConfig(config, ["model_path", "proj_path"])
        self._setup(config, "setup_caption", "currentLLMConfig")

    def setupTag(self, config: dict):
        config = self.procCfg.translateConfig(config, ["model_path", "csv_path"])
        self._setup(config, "setup_tag", "currentTagConfig")

    def setupLLM(self, config: dict):
        config = self.procCfg.translateConfig(config, ["model_path"])
        self._setup(config, "setup_llm", "currentLLMConfig")

    def setupMasking(self, config: dict):
        config = self.procCfg.translateConfig(config, ["model_path"])
        self._query({
            "cmd": "setup_masking",
            "config": config
        })

    def setupUpscale(self, config: dict):
        config = self.procCfg.translateConfig(config, ["model_path"])
        self._query({
            "cmd": "setup_upscale",
            "config": config
        })


    def _setup(self, config: dict, cmd: str, configAttr: str):
        msg = {
            "cmd": cmd,
            "config": config
        }

        try:
            self._updateBackend(config, configAttr)
            future = ProcFuture()
            self.queueWrite.emit(Service.ID.INFERENCE, msg, future)

            if self.record:
                self.recordedFutures.append(future)
                return

            future.result()
        except:
            self.stop()
            raise

    def _updateBackend(self, config: dict, configAttr: str) -> None:
        currentConfig: dict = getattr(self, configAttr)
        diff = ( True for k, v in currentConfig.items() if config.get(k) != v )
        if any(diff):
            self.stop(wait=True)
            self.start(wait=True)

        # Remove sampling settings so they are not included in the check above
        currentConfig = copy.deepcopy(config)
        if Config.INFER_PRESET_SAMPLECFG_KEY in currentConfig:
            del currentConfig[Config.INFER_PRESET_SAMPLECFG_KEY]
        setattr(self, configAttr, currentConfig)


    def clearImageCache(self):
        self.queueWrite.emit(Service.ID.HOST, {
            "cmd": "cache_clear"
        }, None)

    def cacheImage(self, imgPath: str, imgData: bytes, totalSize: int):
        self.queueWrite.emit(Service.ID.HOST, {
            "cmd": "cache_img",
            "img": imgPath,
            "img_data": imgData,
            "size": totalSize
        }, None)

    def uncacheImage(self, imgPath: str):
        self.queueWrite.emit(Service.ID.HOST, {
            "cmd": "uncache_img",
            "img": imgPath
        }, None)


    def caption(self, imgPath, prompts: list[dict[str, str]], sysPrompt=None) -> dict[str, str]:
        return self._queryKey("captions", {
            "cmd": "caption",
            "img": imgPath,
            "prompts": prompts,
            "sysPrompt": sysPrompt
        })

    def tag(self, imgPath) -> str:
        return self._queryKey("tags", {
            "cmd": "tag",
            "img": imgPath
        })

    def answer(self, prompts: list[dict[str, str]], sysPrompt=None) -> dict[str, str]:
        return self._queryKey("answers", {
            "cmd": "answer",
            "prompts": prompts,
            "sysPrompt": sysPrompt
        })

    def mask(self, config: dict, classes: list[str], imgPath: str) -> bytes:
        config = self.procCfg.translateConfig(config, ["model_path"])
        return self._queryKey("mask", {
            "cmd": "mask",
            "config": config,
            "classes": classes,
            "img": imgPath
        })

    def maskBoxes(self, config: dict, classes: list[str], imgPath: str) -> list[dict]:
        config = self.procCfg.translateConfig(config, ["model_path"])
        return self._queryKey("boxes", {
            "cmd": "mask_boxes",
            "config": config,
            "classes": classes,
            "img": imgPath
        })

    def getDetectClasses(self, config: dict) -> list[str]:
        config = self.procCfg.translateConfig(config, ["model_path"])
        return self._queryKey("classes", {
            "cmd": "get_detect_classes",
            "config": config
        })

    def upscaleImageFile(self, config: dict, imgPath: str) -> tuple[int, int, bytes]:
        config = self.procCfg.translateConfig(config, ["model_path"])
        answer = self._query({
            "cmd": "imgfile_upscale",
            "config": config,
            "img": imgPath
        })
        return (answer["w"], answer["h"], answer["img"]) if answer else (0, 0, b"")

    def upscaleImage(self, config: dict, imgData: bytes, w: int, h: int) -> tuple[int, int, bytes]:
        # TODO: Compress images for remote hosts
        config = self.procCfg.translateConfig(config, ["model_path"])
        answer = self._query({
            "cmd": "img_upscale",
            "config": config,
            "img_data": imgData,
            "w": w,
            "h": h
        })
        return (answer["w"], answer["h"], answer["img"]) if answer else (0, 0, b"")


    def _query(self, msg: dict, serviceId=Service.ID.INFERENCE) -> dict[str, Any]:
        future = ProcFuture()
        self.queueWrite.emit(serviceId, msg, future)

        if self.record:
            self.recordedFutures.append(future)
            return dict()

        return future.result()

    def _queryKey(self, returnKey: str, msg: dict) -> Any:
        return self._query(msg).get(returnKey)


    def _onProcessStarted(self, future: ProcFuture):
        try:
            future.result()
            state = True
        except:
            state = False

        with QMutexLocker(self._mutex):
            self._ready = state
            self.processReady.emit(self, state)

    @Slot()
    def _onProcessEnded(self, exitCode, exitStatus):
        print(f"Inference process '{self.procCfg.hostName}' ended. Exit code: {exitCode}, {exitStatus}")

        exception = InferenceException(self.procCfg.hostName, f"Process terminated")
        for future in self._futures.values():
            future.setException(exception)
        self._futures = dict()

        self.processEnded.emit(self)

        with QMutexLocker(self._mutex):
            try:
                # Buffers still intact
                self.proc.readAllStandardOutput()
                self.proc.readAllStandardError()
            except:
                pass
            finally:
                self.proc = None
                self._ready = False


    @Slot()
    def _writeMessage(self, serviceId: int, msg: dict, future: ProcFuture | None):
        reqId = self._nextReqId
        self._nextReqId += 1

        try:
            data: bytes = msgpack.packb(msg)
            header = struct.pack("!HII", serviceId, len(data), reqId)
            self.proc.write(header)
            self.proc.write(data)
            self.proc.waitForBytesWritten(0) # Flush

            if future:
                self._futures[reqId] = future
        except Exception as ex:
            if future:
                future.setException(ex)
            else:
                raise


    @Slot()
    def _onReadyRead(self):
        while self.proc.bytesAvailable() > Protocol.HEADER_LENGTH:
            reqId, msg = self._readMessage()
            if reqId <= 0:
                continue

            if future := self._futures.pop(reqId, None):
                if not msg:
                    future.setException(InferenceException(self.procCfg.hostName, "Unknown error"))
                elif error := msg.get("error"):
                    future.setException(InferenceException(self.procCfg.hostName, error, msg.get("error_type", "Unknown Error Type")))
                else:
                    future.setResult(msg)
            else:
                content = (msg.get("cmd") or msg.get("error_type")) if msg else "Unknown"
                print(f"WARNING: Message from inference process has no Future (Received: {content})")


    def _readMessage(self) -> tuple[int, dict | None]:
        # Handling of incomplete messages could also utilize QIODevice transactions
        try:
            # Start reading
            if self._readLength == 0:
                headerBuffer = self.proc.read(Protocol.HEADER_LENGTH)
                srv, length, reqId = struct.unpack("!HII", headerBuffer.data())
                buffer = self.proc.read(length)

                if buffer.length() < length:
                    self._readBuffer = buffer
                    self._readReq = reqId
                    self._readLength = length
                    return 0, None

            # Continue reading
            else:
                buffer = self.proc.read(self._readLength - self._readBuffer.length())
                self._readBuffer.append(buffer)

                if self._readBuffer.length() < self._readLength:
                    return 0, None

                buffer = self._readBuffer
                reqId = self._readReq

                self._readBuffer = None
                self._readReq = 0
                self._readLength = 0

            return reqId, msgpack.unpackb(buffer.data())
        except:
            traceback.print_exc()
            return 0, None
