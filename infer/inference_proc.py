from PySide6.QtCore import QProcess, QByteArray, QMutex, QMutexLocker, QThread
import sys, struct, msgpack, copy
from util import Singleton
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
        self.proc = None
        self.mutex = QMutex()

        self.currentLLMConfig = dict()
        self.currentTagConfig = dict()


    def start(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                return

            self.proc = QProcess()
            self.proc.setProgram(sys.executable)
            self.proc.setArguments(["-u", "main_inference.py"]) # Unbuffered pipes
            self.proc.setProcessChannelMode(QProcess.SeparateChannels)
            self.proc.readyReadStandardError.connect(self._onError)
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

    def terminate(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                self.proc.terminate()


    def setupCaption(self, config: dict):
        self._setup(config, "setup_caption", "currentLLMConfig")
        
    def setupTag(self, config: dict):
        self._setup(config, "setup_tag", "currentTagConfig")

    def setupLLM(self, config: dict):
        self._setup(config, "setup_llm", "currentLLMConfig")

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
        return self._query("tags",{
            "cmd": "tag",
            "img": imgPath
        })

    def answer(self, prompts: dict, sysPrompt=None) -> dict[str, str]:
        return self._query("answers",{
            "cmd": "answer",
            "prompts": prompts,
            "sysPrompt": sysPrompt
        })

    def _query(self, returnKey: str, msg: dict):
        with QMutexLocker(self.mutex):
            self._writeMessage(msg)
            if answer := self._blockReadMessage():
                if error := answer.get("error"):
                    raise InferenceException(error, msg.get("error_type"))
                return answer.get(returnKey)
            else:
                raise InferenceException("Unknown error")

    def _onError(self):
        err = self.proc.readAllStandardError().data().decode('utf-8')
        sys.stderr.write(err)
        sys.stderr.flush()

    def _onProcessEnded(self, exitCode, exitStatus):
        print(f"Inference process ended. Exit code: {exitCode}, {exitStatus}")
        # Buffers still intact
        self.proc.readAllStandardOutput()
        self.proc.readAllStandardError()
        self.proc = None
        

    def _writeMessage(self, msg) -> None:
        data = msgpack.packb(msg)
        buffer = QByteArray()
        buffer.append( struct.pack("!I", len(data)) )
        buffer.append(data)
        self.proc.write(buffer)

    def _readMessage(self) -> dict:
        headerBuffer = self.proc.read(4)
        length = struct.unpack("!I", headerBuffer.data())[0]
        buffer = self.proc.read(length)
        return msgpack.unpackb(buffer.data())

    def _blockReadMessage(self) -> dict | None:
        try:
            while True:
                # waitForReadyRead blocks the UI, therefore wait manually using QThread.msleep
                QThread.msleep(30)
                if self.proc.waitForReadyRead(0):
                    break

            return self._readMessage()
        except:
            # Process ended while waiting
            return None
