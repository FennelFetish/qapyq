import sys, struct, msgpack, traceback
from infer.backend_config import BackendLoader, LastBackendLoader
from config import Config


backendLoader = BackendLoader()
llmBackend = LastBackendLoader(backendLoader)
tagBackend = LastBackendLoader(backendLoader)


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



def handleMessage(protocol) -> bool:
    msg: dict = protocol.readMessage()
    cmd: str = msg["cmd"]

    match cmd:
        case "quit":
            # No reply! It won't quit when we send something here.
            return False


        case "setup_caption" | "setup_llm":
            llmBackend.getBackend(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})

        case "setup_tag":
            tagBackend.getBackend(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})
        
        case "setup_masking" | "setup_upscale":
            backendLoader.getBackend(msg.get("config", {}))
            protocol.writeMessage({"cmd": cmd})


        # TODO: Cache image
        case "caption":
            img = msg["img"]
            captions = llmBackend.getBackend().caption(img, msg["prompts"], msg["sysPrompt"])
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "captions": captions
            })
        
        # TODO: Cache image
        case "tag":
            img = msg["img"]
            tags = tagBackend.getBackend().tag(img)
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "tags": tags
            })

        case "answer":
            answers = llmBackend.getBackend().answer(msg["prompts"], msg["sysPrompt"])
            protocol.writeMessage({
                "cmd": cmd,
                "answers": answers
            })


        case "mask":
            img = msg["img"]
            classes = msg["classes"]
            mask = backendLoader.getBackend(msg["config"]).mask(img, classes)
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "mask": mask
            })

        case "mask_boxes":
            img = msg["img"]
            classes = msg["classes"]
            boxes = backendLoader.getBackend(msg["config"]).detectBoxes(img, classes)
            protocol.writeMessage({
                "cmd": cmd,
                "img": img,
                "boxes": boxes
            })

        case "get_detect_classes":
            classes = backendLoader.getBackend(msg["config"]).getClassNames()
            protocol.writeMessage({
                "cmd": cmd,
                "classes": classes
            })


        case "imgfile_upscale":
            img = msg["img"]
            backend = backendLoader.getBackend(msg["config"])
            w, h, imgUpscaled = backend.upscaleImage(img)
            protocol.writeMessage({
                "cmd": cmd,
                "w": w,
                "h": h,
                "img": imgUpscaled
            })
        
        case "img_upscale":
            imgData = msg["img_data"]
            w, h = msg["w"], msg["h"]
            backend = backendLoader.getBackend(msg["config"])
            w, h, imgUpscaled = backend.upscaleImageData(imgData, w, h)
            protocol.writeMessage({
                "cmd": cmd,
                "w": w,
                "h": h,
                "img": imgUpscaled
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
    # Send data through original stdout, redirect stdout to stderr for logging
    protocol = Protocol(sys.stdin.buffer, sys.stdout.buffer)
    sys.stdout = sys.stderr

    print("Inference process started")
    
    running = True
    while running:
        try:
            running = handleMessage(protocol)
        except KeyboardInterrupt:
            running = False
        except:
            exType, exMessage, exTraceback = sys.exc_info()
            print(traceback.format_exc())
            handleError(protocol, str(exType), str(exMessage))
    
    print("Inference process ending")
    return 0


if __name__ == "__main__":
    Config.load()
    sys.exit( main() )
