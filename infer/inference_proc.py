from PySide6.QtCore import QProcess, QByteArray, QMutex, QMutexLocker, QThread, QProcessEnvironment
import sys, struct, msgpack, copy, traceback
from lib.util import Singleton
from config import Config


class InferenceSetupException(Exception):
    def __init__(self, cmd: str, message: str, errorType: str = None):
        modelType = cmd.split("_")[-1]
        msg = f"Couldn't load {modelType} model: {message}"
        if errorType:
            msg += f" ({errorType})"

        super().__init__(msg)

class InferenceException(Exception):
    def __init__(self, message: str, errorType: str = None):
        msg = f"Error during inference: {message}"
        if errorType:
            msg += f" ({errorType})"

        super().__init__(msg)


class InferenceProcess(metaclass=Singleton):
    def __init__(self):
        self.proc: QProcess = None
        self.mutex = QMutex()

        self.currentLLMConfig = dict()
        self.currentTagConfig = dict()

        self._readBuffer: QByteArray = None
        self._readLength = 0


    def start(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                return

            env = QProcessEnvironment.systemEnvironment()
            env.insert("NO_ALBUMENTATIONS_UPDATE", "1")

            self.proc = QProcess()
            self.proc.setProgram(sys.executable)
            self.proc.setArguments(["-u", "main_inference.py"]) # Unbuffered pipes
            #self.proc.setArguments(["main_inference.py"])
            self.proc.setProcessEnvironment(env)
            self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedErrorChannel)
            self.proc.finished.connect(self._onProcessEnded)
            self.proc.start()

            while True:
                QThread.msleep(30)
                if self.proc.waitForStarted(0):
                    break


    def stop(self):
        self.currentLLMConfig = dict()
        self.currentTagConfig = dict()

        with QMutexLocker(self.mutex):
            if self.proc:
                self._writeMessage({"cmd": "quit"})
                # There isn't any answer coming. Child process doesn't send anything while quitting.
                # But for some reason, to flush the message, we have to read from the pipe
                self._blockReadMessage()

    def kill(self):
        try:
            if self.proc:
                self.proc.kill()
        except Exception as ex:
            print(ex)
                

    def setupCaption(self, config: dict):
        self._setup(config, "setup_caption", "currentLLMConfig")
        
    def setupTag(self, config: dict):
        self._setup(config, "setup_tag", "currentTagConfig")

    def setupLLM(self, config: dict):
        self._setup(config, "setup_llm", "currentLLMConfig")
    
    def setupMasking(self, config: dict):
        self._query("cmd", {
            "cmd": "setup_masking",
            "config": config
        })

    def _setup(self, config: dict, cmd: str, configAttr: str):
        try:
            self._updateBackend(config, configAttr)
            with QMutexLocker(self.mutex):
                self._writeMessage({
                    "cmd": cmd,
                    "config": config
                })

                if answer := self._blockReadMessage():
                    if error := answer.get("error"):
                        raise InferenceSetupException(cmd, error, answer.get("error_type"))
                else:
                    raise InferenceSetupException(cmd, "Unknown error")
        except:
            self.stop()
            raise

    def _updateBackend(self, config: dict, configAttr: str) -> None:
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


    def caption(self, imgPath, prompts: dict, sysPrompt=None) -> dict[str, str]:
        return self._query("captions", {
            "cmd": "caption",
            "img": imgPath,
            "prompts": prompts,
            "sysPrompt": sysPrompt
        })

    def tag(self, imgPath) -> str:
        return self._query("tags", {
            "cmd": "tag",
            "img": imgPath
        })

    def answer(self, prompts: dict, sysPrompt=None) -> dict[str, str]:
        return self._query("answers", {
            "cmd": "answer",
            "prompts": prompts,
            "sysPrompt": sysPrompt
        })

    def mask(self, config: dict, imgPath: str) -> bytes:
        return self._query("mask", {
            "cmd": "mask",
            "config": config,
            "img": imgPath
        })

    def maskBoxes(self, config: dict, imgPath: str) -> list[dict]:
        return self._query("boxes", {
            "cmd": "mask_boxes",
            "config": config,
            "img": imgPath
        })

    def _query(self, returnKey: str, msg: dict):
        with QMutexLocker(self.mutex):
            self._writeMessage(msg)
            answer = self._blockReadMessage()

            if not answer:
                raise InferenceException("Unknown error")
            if error := answer.get("error"):
                raise InferenceException(error, msg.get("error_type"))
            
            return answer.get(returnKey)


    def _onProcessEnded(self, exitCode, exitStatus):
        # FIXME: Not printed anymore in linux?
        print(f"Inference process ended. Exit code: {exitCode}, {exitStatus}")
        # Buffers still intact
        self.proc.readAllStandardOutput()
        self.proc.readAllStandardError()
        self.proc = None


    def _writeMessage(self, msg) -> None:
        try:
            data = msgpack.packb(msg)
            buffer = QByteArray()
            buffer.append( struct.pack("!I", len(data)) )
            buffer.append(data)
            self.proc.write(buffer)
        except:
            print(traceback.format_exc())

    def _readMessage(self) -> dict | None:
        # Handling of incomplete messages could also utilize QIODevice transactions
        try:
            # Start reading
            if self._readLength == 0:
                headerBuffer = self.proc.read(4)
                length = struct.unpack("!I", headerBuffer.data())[0]
                buffer = self.proc.read(length)

                if buffer.length() < length:
                    self._readBuffer = buffer
                    self._readLength = length
                    return None
            
            # Continue reading
            else:
                buffer = self.proc.read(self._readLength - self._readBuffer.length())
                self._readBuffer.append(buffer)

                if self._readBuffer.length() < self._readLength:
                    return None
                
                buffer = self._readBuffer
                self._readBuffer = None
                self._readLength = 0

            return msgpack.unpackb(buffer.data())
        except:
            print(traceback.format_exc())
            return {}

    def _blockReadMessage(self) -> dict | None:
        try:
            # waitForReadyRead blocks the UI, therefore wait manually using QThread.msleep
            while not self.proc.waitForReadyRead(0):
                QThread.msleep(30)
            while not (msg := self._readMessage()):
                self.proc.waitForReadyRead(-1)
            return msg
        except:
            # Process ended while waiting
            return None
