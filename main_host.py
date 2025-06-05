import sys, struct, msgpack
from typing import Any, IO
from typing_extensions import override
from host.protocol import Protocol, MessageLoop, Service, msghandler
from host.imagecache import ImageCache, ImageFile
from config import Config


class Host(Service):
    def __init__(self, protocol: Protocol):
        super().__init__(protocol)
        self.loop = MessageLoop(protocol)
        self.imgCache = ImageCache()

        self.inference = None
        protocol.setSubServiceSpawner(Service.ID.INFERENCE, self.spawnInference)

    def spawnInference(self, serviceId: int):
        self.inference = InferenceSubprocess(serviceId, self.protocol, self.imgCache)
        return self.inference.protocol


    @msghandler("cache_img")
    def cacheImage(self, msg: dict):
        self.imgCache.recvImageData(msg["img"], msg["img_data"], msg["size"])

    @msghandler("uncache_img")
    def uncacheImage(self, msg: dict):
        self.imgCache.releaseImage(msg["img"])


    @msghandler("quit")
    def handleQuit(self, msg):
        if self.inference:
            self.inference.stop()
        self.loop.stop()



class ForwardingProtocol(Protocol):
    def __init__(self, serviceId: int, bufIn: IO[bytes], bufOut: IO[bytes], receiverProtocol: Protocol, imgCache: ImageCache):
        super().__init__(serviceId, bufIn, bufOut)
        self.receiverProtocol = receiverProtocol
        self.imgCache = imgCache

    @override
    def readMessage(self) -> tuple[int, dict[str, Any] | None]:
        header = self.bufIn.read(self.HEADER_LENGTH)
        srv, length, reqId = struct.unpack("!HII", header)
        data = self.bufIn.read(length)

        self.receiverProtocol.write(header, data)
        return reqId, None

    @override
    def writeSubService(self, reqId: int, header: bytes, data: bytes):
        msg: dict = msgpack.unpackb(data)
        # TODO: Add callback when imgFile doesn't exist yet? -> This shouldn't happen because upload is queued before tasks
        if (img := msg.get("img")) and (imgFile := self.imgCache.getImage(img)):
            if imgFile.isComplete():
                self.forwardImgData(imgFile, reqId, msg)
            else:
                imgFile.addCompleteCallback(lambda imgFile, reqId=reqId, msg=msg: self.forwardImgData(imgFile, reqId, msg))
        else:
            self.write(header, data)

    def forwardImgData(self, imgFile: ImageFile, reqId: int, msg: dict):
        msg["img_data"] = imgFile.data
        self.writeMessage(reqId, msg)



class InferenceSubprocess:
    def __init__(self, serviceId: int, mainProtocol: Protocol, imgCache: ImageCache):
        import subprocess, threading

        self.process = subprocess.Popen(
            [sys.executable, "-u", "main_inference.py"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False
        )

        self.protocol = ForwardingProtocol(serviceId, self.process.stdout, self.process.stdin, mainProtocol, imgCache)
        self.loop = MessageLoop(self.protocol)

        self.threadOut = threading.Thread(target=self.loop)
        self.threadOut.daemon = True
        self.threadOut.start()

        self.threadErr = threading.Thread(target=self.forwardStdErr, args=(self.process.stderr,))
        self.threadErr.daemon = True
        self.threadErr.start()

    @staticmethod
    def forwardStdErr(errPipe: IO[bytes]):
        for line in iter(errPipe.readline, b''):
            print(line.decode().strip())

    def stop(self):
        self.protocol.writeMessage(0, {"cmd": "quit"})
        self.loop.stop()


def main() -> int:
    sys.stderr.reconfigure(line_buffering=True)

    # Send data through original stdout, redirect stdout to stderr for logging
    protocol = Protocol(Service.ID.HOST, sys.stdin.buffer, sys.stdout.buffer)
    sys.stdout = sys.stderr

    if not Config.load():
        return 1

    print("Host process started")
    host = Host(protocol)
    host.loop()
    print("Host process ending")
    return 0


if __name__ == "__main__":
    sys.exit( main() )
