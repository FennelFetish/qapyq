import sys, struct, msgpack, copy, traceback
from typing import Any
from threading import Condition
from PySide6.QtCore import Qt, Slot, Signal, QObject, QProcess, QProcessEnvironment, QByteArray, QMutex, QMutexLocker
from host.protocol import Protocol, Service
from config import Config


class InferenceSetupException(Exception):
    def __init__(self, cmd: str, message: str, errorType: str = None):
        modelType = cmd.split("_")[-1]
        errorType = f" ({errorType})" if errorType else ""
        msg = f"Couldn't load {modelType} model: {message}{errorType}"
        super().__init__(msg)

class InferenceException(Exception):
    def __init__(self, message: str, errorType: str = None):
        msg = f"Error during inference: {message}"
        if errorType:
            msg += f" ({errorType})"

        super().__init__(msg)



class ProcFuture:
    def __init__(self):
        self._cond = Condition()
        self._result: dict | None = None
        self._exception = None

    def setResult(self, result: dict):
        with self._cond:
            self._result = result
            self._cond.notify_all()

    def setException(self, exception):
        with self._cond:
            if not self._exception:
                self._exception = exception
                self._cond.notify_all()

    def result(self) -> dict:
        with self._cond:
            while True:
                if self._exception is not None:
                    raise self._exception
                if self._result is not None:
                    return self._result
                self._cond.wait()



class InferenceProcess(QObject):
    queueStart = Signal()
    queueWrite = Signal(int, dict, object)


    def __init__(self, remote=True):
        super().__init__()

        self.remote = remote
        self.proc: QProcess = None

        self.currentLLMConfig = dict()
        self.currentTagConfig = dict()

        # Mutex protects proc and config
        self._mutex = QMutex()

        self._readBuffer: QByteArray = None
        self._readReq = 0
        self._readLength = 0

        self._futures: dict[int, ProcFuture] = dict()
        self._nextReqId = 1  # reqId 0 for messages with no associated Future

        self.queueStart.connect(self._start, Qt.ConnectionType.QueuedConnection)
        self.queueWrite.connect(self._writeMessage, Qt.ConnectionType.QueuedConnection)


    def start(self):
        self.queueStart.emit()

    @Slot()
    def _start(self):
        with QMutexLocker(self._mutex):
            if self.proc:
                return

            env = QProcessEnvironment.systemEnvironment()
            env.insert("NO_ALBUMENTATIONS_UPDATE", "1")
            #env.insert("VLLM_USE_V1", "1") # RuntimeError: Cannot re-initialize CUDA in forked subprocess. To use CUDA with multiprocessing, you must use the 'spawn' start method
            #env.insert("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
            env.insert("VLLM_NO_USAGE_STATS", "1")
            env.insert("VLLM_DO_NOT_TRACK", "1")

            self.proc = QProcess()
            if self.remote:
                # TODO: Textfield for this command and arguments
                with open("./ssh-command.txt", "r") as file:
                    command = file.readline().split(" ")

                self.proc.setProgram(command[0])
                self.proc.setArguments(command[1:])

                # self.proc.setProgram(sys.executable)
                # self.proc.setArguments(["-u", "main_host.py"]) # Unbuffered pipes
            else:
                self.proc.setProgram(sys.executable)
                self.proc.setArguments(["-u", "main_inference.py"]) # Unbuffered pipes

            self.proc.setProcessEnvironment(env)
            self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
            self.proc.setReadChannel(QProcess.ProcessChannel.StandardOutput)
            self.proc.readyReadStandardOutput.connect(self._onReadyRead)
            self.proc.finished.connect(self._onProcessEnded)
            self.proc.start()

            self.proc.waitForStarted()


    def stop(self):
        with QMutexLocker(self._mutex):
            self.currentLLMConfig = dict()
            self.currentTagConfig = dict()

            if self.proc:
                serviceId = Service.ID.HOST if self.remote else Service.ID.INFERENCE
                self.queueWrite.emit(serviceId, {"cmd": "quit"}, None)


    def kill(self):
        try:
            with QMutexLocker(self._mutex):
                if self.proc:
                    self.proc.kill()
        except:
            traceback.print_exc()


    def setupCaption(self, config: dict):
        self._setup(config, "setup_caption", "currentLLMConfig")

    def setupTag(self, config: dict):
        self._setup(config, "setup_tag", "currentTagConfig")

    def setupLLM(self, config: dict):
        self._setup(config, "setup_llm", "currentLLMConfig")

    def setupMasking(self, config: dict):
        self._query({
            "cmd": "setup_masking",
            "config": config
        })

    def setupUpscale(self, config: dict):
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

            answer = future.result()
            if not answer:
                raise InferenceSetupException(cmd, "Unknown error")
            if error := answer.get("error"):
                raise InferenceSetupException(cmd, error, answer.get("error_type"))
        except:
            self.stop()
            raise

    def _updateBackend(self, config: dict, configAttr: str) -> None:
        with QMutexLocker(self._mutex):
            currentConfig: dict = getattr(self, configAttr)
            diff = ( True for k, v in currentConfig.items() if config.get(k) != v )
            if any(diff):
                self.stop()
                self.start()

            # Remove sampling settings so they are not included in the check above
            currentConfig = copy.deepcopy(config)
            if Config.INFER_PRESET_SAMPLECFG_KEY in currentConfig:
                del currentConfig[Config.INFER_PRESET_SAMPLECFG_KEY]
            setattr(self, configAttr, currentConfig)


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
        return self._queryKey("mask", {
            "cmd": "mask",
            "config": config,
            "classes": classes,
            "img": imgPath
        })

    def maskBoxes(self, config: dict, classes: list[str], imgPath: str) -> list[dict]:
        return self._queryKey("boxes", {
            "cmd": "mask_boxes",
            "config": config,
            "classes": classes,
            "img": imgPath
        })

    def getDetectClasses(self, config: dict) -> list[str]:
        return self._queryKey("classes", {
            "cmd": "get_detect_classes",
            "config": config
        })

    def upscaleImageFile(self, config: dict, imgPath: str) -> tuple[int, int, bytes]:
        answer = self._query({
            "cmd": "imgfile_upscale",
            "config": config,
            "img": imgPath
        })
        return answer["w"], answer["h"], answer["img"]

    def upscaleImage(self, config: dict, imgData: bytes, w: int, h: int) -> tuple[int, int, bytes]:
        answer = self._query({
            "cmd": "img_upscale",
            "config": config,
            "img_data": imgData,
            "w": w,
            "h": h
        })
        return answer["w"], answer["h"], answer["img"]


    def _query(self, msg: dict) -> dict[str, Any]:
        future = ProcFuture()
        self.queueWrite.emit(Service.ID.INFERENCE, msg, future)

        answer = future.result()
        if not answer:
            raise InferenceException("Unknown error")
        if error := answer.get("error"):
            raise InferenceException(error, answer.get("error_type"))

        return answer

    def _queryKey(self, returnKey: str, msg: dict) -> Any:
        return self._query(msg).get(returnKey)


    @Slot()
    def _onProcessEnded(self, exitCode, exitStatus):
        print(f"Inference process ended. Exit code: {exitCode}, {exitStatus}")

        exception = InferenceException("Process terminated")
        for future in self._futures.values():
            future.setException(exception)
        self._futures = dict()

        # Buffers still intact
        self.proc.readAllStandardOutput()
        self.proc.readAllStandardError()
        self.proc = None


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


    @Slot()
    def _onReadyRead(self):
        while self.proc.bytesAvailable() > Protocol.HEADER_LENGTH:
            reqId, msg = self._readMessage()
            if reqId > 0 and msg is not None:
                if future := self._futures.pop(reqId, None):
                    future.setResult(msg)
                else:
                    print("WARNING: Message from inference process has no Future")


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
