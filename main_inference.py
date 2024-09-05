import sys, struct, msgpack, traceback, os
from config import Config


minicpm = None
joytag  = None


def loadMiniCpm():
    global minicpm
    if not minicpm:
        from infer.minicpm import MiniCPM
        minicpm = MiniCPM(Config.inferCaptionModelPath, Config.inferCaptionClipPath)
    return minicpm

def loadJoytag():
    global joytag
    if not joytag:
        from infer.joytag import JoyTag
        joytag = JoyTag(Config.inferTagModelPath)
    return joytag



class Protocol:
    def __init__(self, bufIn, bufOut):
        self.bufIn  = bufIn
        self.bufOut = bufOut

    def readMessage(self):
        header = self.bufIn.read(4)
        length = struct.unpack("!I", header)[0]
        data   = self.bufIn.read(length)
        return msgpack.unpackb(data)

    def writeMessage(self, msg):
        data = msgpack.packb(msg)
        length = struct.pack("!I", len(data))
        self.bufOut.write(length)
        self.bufOut.write(data)
        self.bufOut.flush()


def printErr(text):
    sys.stderr.write(text + os.linesep)


def handleMessage(protocol) -> bool:
    msg = protocol.readMessage()
    cmd = msg["cmd"]
    printErr(f"Inference process received command: {cmd}")

    if cmd == "quit":
        # No reply! It won't quit when we send something here.
        return False

    elif cmd == "prepare_caption":
        loadMiniCpm()
        protocol.writeMessage({"cmd": cmd})

    elif cmd == "prepare_tag":
        loadJoytag()
        protocol.writeMessage({"cmd": cmd})

    elif cmd == "setup_caption":
        minicpm = loadMiniCpm()
        # TODO: settings
        protocol.writeMessage({"cmd": cmd})

    elif cmd == "setup_tag":
        loadJoytag().threshold = float(msg["threshold"])
        protocol.writeMessage({"cmd": cmd})
    
    elif cmd == "caption":
        img = msg["img"]
        captions = loadMiniCpm().captionMulti(img, msg["prompts"], msg["sysPrompt"])
        protocol.writeMessage({
            "cmd": cmd,
            "img": img,
            "captions": captions
        })
    
    elif cmd == "tag":
        img = msg["img"]
        tags = loadJoytag().caption(img)
        protocol.writeMessage({
            "cmd": cmd,
            "img": img,
            "tags": tags
        })

    return True


def main() -> int:
    printErr("Inference process started")
    protocol = Protocol(sys.stdin.buffer, sys.stdout.buffer)
    running = True
    while running:
        try:
            if not handleMessage(protocol):
                running = False
                break
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback.print_exc(file=sys.stderr)
            protocol.writeMessage({
                "error_type": str(exc_type),
                "error": str(exc_value)
            })
    
    printErr("Inference process ended")
    return 0


if __name__ == "__main__":
    sys.exit( main() )
