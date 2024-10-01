from PySide6.QtCore import QProcess, QByteArray, QMutex, QMutexLocker, QThread
import sys, struct, msgpack, copy
from util import Singleton
from config import Config


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
                self._blockReadMessage("cmd")

    def terminate(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                self.proc.terminate()


    def updateBackend(self, config: dict, configAttr: str) -> None:
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


    # TODO: Catch error when loading models and don't set config
    def setupCaption(self, config: dict):
        self.updateBackend(config, "currentLLMConfig")
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "setup_caption",
                "config": config
            })
            return self._blockReadMessage("cmd")

    def setupTag(self, config: dict):
        self.updateBackend(config, "currentTagConfig")
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "setup_tag",
                "config": config
            })
            return self._blockReadMessage("cmd")

    def setupLLM(self, config: dict):
        self.updateBackend(config, "currentLLMConfig")
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "setup_llm",
                "config": config
            })
            return self._blockReadMessage("cmd")


    def caption(self, imgPath, prompts: dict, sysPrompt=None) -> dict[str, str]:
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "caption",
                "img": imgPath,
                "prompts": prompts,
                "sysPrompt": sysPrompt
            })
            return self._blockReadMessage("captions")

    def tag(self, imgPath) -> str:
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "tag",
                "img": imgPath
            })
            return self._blockReadMessage("tags")

    def answer(self, prompts: dict, sysPrompt=None) -> dict[str, str]:
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "answer",
                "prompts": prompts,
                "sysPrompt": sysPrompt
            })
            return self._blockReadMessage("answers")


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
        

    def _writeMessage(self, msg):
        data = msgpack.packb(msg)
        buffer = QByteArray()
        buffer.append( struct.pack("!I", len(data)) )
        buffer.append(data)
        self.proc.write(buffer)

    def _readMessage(self):
        headerBuffer = self.proc.read(4)
        length = struct.unpack("!I", headerBuffer.data())[0]
        buffer = self.proc.read(length)
        return msgpack.unpackb(buffer.data())

    def _blockReadMessage(self, key):
        try:
            while True:
                QThread.msleep(30)
                if self.proc.waitForReadyRead(0):
                    break

            msg = self._readMessage()
            return msg.get(key)
        except:
            return None
