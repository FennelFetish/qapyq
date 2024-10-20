import sys, struct, msgpack, traceback, os
from config import Config


backend = None
tag = None


def loadBackend(config: dict):
    if not config:
        raise ValueError("Cannot load backend without config")

    match config.get("backend"):
        case "minicpm":
            from infer.backend_llamacpp import LlamaCppVisionBackend
            from llama_cpp.llama_chat_format import MiniCPMv26ChatHandler
            return LlamaCppVisionBackend(config, MiniCPMv26ChatHandler)
        case "internvl2":
            from infer.backend_internvl2 import InternVL2Backend
            return InternVL2Backend(config)
        case "qwen2vl":
            from infer.backend_qwen2vl import Qwen2VLBackend
            return Qwen2VLBackend(config)
        case "ovis16":
            from infer.backend_ovis16 import Ovis16Backend
            return Ovis16Backend(config)
        case "molmo":
            from infer.backend_molmo import MolmoBackend
            return MolmoBackend(config)
        case "gguf":
            from infer.backend_llamacpp import LlamaCppBackend
            return LlamaCppBackend(config)

    raise ValueError(f"Unknown backend: {config.get('backend')}")


def getBackend(config: dict = None):
    global backend
    if backend == None:
        backend = loadBackend(config)
    elif config:
        backend.setConfig(config)
    return backend



def loadTag(config: dict):
    if not config:
        raise ValueError("Cannot load tagging backend without config")

    match config.get("backend"):
        case "joytag":
            from infer.tag_joytag import JoyTag
            return JoyTag(config)
        case "wd":
            from infer.tag_wd import WDTag
            return WDTag(config)

    raise ValueError(f"Unknown tagging backend: {config.get('backend')}")


def getTag(config: dict = None):
    global tag
    if tag == None:
        tag = loadTag(config)
    elif config:
        tag.setConfig(config)
    return tag



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
    sys.stderr.flush()


def handleMessage(protocol) -> bool:
    msg: dict = protocol.readMessage()
    cmd: str = msg["cmd"]

    match cmd:
        case "quit":
            # No reply! It won't quit when we send something here.
            return False


        case "setup_caption":
            getBackend(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})

        case "setup_tag":
            getTag(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})

        case "setup_llm":
            getBackend(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})


        # TODO: Cache image
        case "caption":
            img = msg["img"]
            captions = getBackend().caption(img, msg["prompts"], msg["sysPrompt"])
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "captions": captions
            })
        
        # TODO: Cache image
        case "tag":
            img = msg["img"]
            tags = getTag().tag(img)
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "tags": tags
            })

        case "answer":
            answers = getBackend().answer(msg["prompts"], msg["sysPrompt"])
            protocol.writeMessage({
                "cmd": cmd,
                "answers": answers
            })

    return True


def handleError(protocol: Protocol, excType: str, excMessage: str) -> None:
    import re
    pattern = r"<class '([^']+)'>"
    if match := re.match(pattern, excType):
        excType = match.group(1)

    protocol.writeMessage({
        "error_type": excType,
        "error": excMessage
    })


def main() -> int:
    printErr("Inference process started")
    protocol = Protocol(sys.stdin.buffer, sys.stdout.buffer)
    
    running = True
    while running:
        try:
            running = handleMessage(protocol)
        except KeyboardInterrupt:
            running = False
        except:
            exType, exMessage, exTraceback = sys.exc_info()
            printErr(traceback.format_exc())
            handleError(protocol, str(exType), str(exMessage))
    
    printErr("Inference process ending")
    return 0


if __name__ == "__main__":
    Config.load()
    sys.exit( main() )
