from PySide6.QtCore import QProcess, QByteArray, QMutex, QMutexLocker
import sys, struct, msgpack
from util import Singleton


class InferenceProcess(metaclass=Singleton):
    def __init__(self):
        self.proc = None
        self.mutex = QMutex()


    def start(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                return

            self.proc = QProcess()
            self.proc.setProgram(sys.executable)
            #self.proc.setArguments(["-u", "main_inference.py"]) # Unbuffered pipes
            self.proc.setArguments(["main_inference.py"])
            #self.proc.setProcessChannelMode(QProcess.ForwardedChannels)
            self.proc.readyReadStandardError.connect(self._onError)
            self.proc.finished.connect(self._onProcessEnded)
            self.proc.start()
            self.proc.waitForStarted(10000)

    def stop(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                self._writeMessage({"cmd": "quit"})
                # For some reason, to flush the message, we have to read from the pipe
                self._blockReadMessage("cmd")

    def terminate(self):
        with QMutexLocker(self.mutex):
            if self.proc:
                self.proc.terminate()


    def prepareCaption(self):
        with QMutexLocker(self.mutex):
            self._writeMessage({"cmd": "prepare_caption"})
            return self._blockReadMessage("cmd")

    def prepareTag(self):
        with QMutexLocker(self.mutex):
            self._writeMessage({"cmd": "prepare_tag"})
            return self._blockReadMessage("cmd")


    def setupCaption(self):
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "setup_caption",
            })
            return self._blockReadMessage("cmd")

    def setupTag(self, threshold=0.4):
        with QMutexLocker(self.mutex):
            self._writeMessage({
                "cmd": "setup_tag",
                "threshold": threshold
            })
            return self._blockReadMessage("cmd")


    def caption(self, imgPath, prompts: dict, sysPrompt=None) -> dict:
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


    def _onError(self):
        err = self.proc.readAllStandardError().data().decode('utf-8')
        sys.stderr.write(err)
        sys.stderr.flush()

    def _onProcessEnded(self, exitCode, exitStatus):
        print(f"Inference process ended. Exit code: {exitCode}, {exitStatus}")
        # Buffers still intact
        input = self.proc.readAllStandardOutput()
        err = self.proc.readAllStandardError()
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
            while not self.proc.waitForReadyRead(2000):
                pass
            msg = self._readMessage()
            return msg[key] if key in msg else None
        except:
            return None
