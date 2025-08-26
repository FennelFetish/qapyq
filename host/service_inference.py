from host.protocol import Protocol, Service, MessageLoop, msghandler
from host.imagecache import ImageFile
from infer.backend_config import BackendLoader, LastBackendLoader


class InferenceService(Service):
    def __init__(self, protocol: Protocol):
        super().__init__(protocol)
        self.backendLoader = BackendLoader()
        self.llmBackend = LastBackendLoader(self.backendLoader)
        self.tagBackend = LastBackendLoader(self.backendLoader)
        self.embedBackend = LastBackendLoader(self.backendLoader)

        self.loop = MessageLoop(protocol)


    @msghandler("echo")
    def echo(self, msg: dict):
        return msg

    @msghandler("quit")
    def handleQuit(self, msg):
        self.loop.stop()


    @msghandler("setup_caption", "setup_llm")
    def setupLLM(self, msg: dict):
        self.llmBackend.getBackend(msg.get("config", {}))
        return {"cmd": msg["cmd"]}

    @msghandler("setup_tag")
    def setupTag(self, msg: dict):
        self.tagBackend.getBackend(msg.get("config", {}))
        return {"cmd": msg["cmd"]}

    @msghandler("setup_embed")
    def setupEmbedding(self, msg: dict):
        self.embedBackend.getBackend(msg.get("config", {}))
        return {"cmd": msg["cmd"]}

    @msghandler("setup_masking", "setup_upscale")
    def setupMasking(self, msg: dict):
        self.backendLoader.getBackend(msg.get("config", {}), setup=True)
        return {"cmd": msg["cmd"]}


    @msghandler("caption")
    def caption(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        captions = self.llmBackend.getBackend().caption(imgFile, msg["prompts"], msg["sysPrompt"])
        return {
            "cmd": msg["cmd"],
            "img": msg["img"],
            "captions": captions
        }

    @msghandler("tag")
    def tag(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        tags = self.tagBackend.getBackend().tag(imgFile)
        return {
            "cmd": msg["cmd"],
            "img": msg["img"],
            "tags": tags
        }

    @msghandler("answer")
    def llm(self, msg: dict):
        answers = self.llmBackend.getBackend().answer(msg["prompts"], msg["sysPrompt"])
        return {
            "cmd": msg["cmd"],
            "answers": answers
        }


    @msghandler("mask")
    def mask(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        classes = msg["classes"]
        mask = self.backendLoader.getBackend(msg["config"]).mask(imgFile, classes)
        return {
            "cmd": msg["cmd"],
            "img": msg["img"],
            "mask": mask
        }

    @msghandler("mask_boxes")
    def maskBoxes(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        classes = msg["classes"]
        boxes = self.backendLoader.getBackend(msg["config"]).detectBoxes(imgFile, classes)
        return {
            "cmd": msg["cmd"],
            "img": msg["img"],
            "boxes": boxes
        }

    @msghandler("get_detect_classes")
    def getDetectClasses(self, msg: dict):
        classes = self.backendLoader.getBackend(msg["config"]).getClassNames()
        return {
            "cmd": msg["cmd"],
            "classes": classes
        }


    @msghandler("imgfile_upscale")
    def upscaleImgFile(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        backend = self.backendLoader.getBackend(msg["config"])
        w, h, imgUpscaled = backend.upscaleImage(imgFile)
        return {
            "cmd": msg["cmd"],
            "w": w,
            "h": h,
            "img": imgUpscaled
        }

    # TODO: Use ImageCache for async upload
    @msghandler("img_upscale")
    def upscaleImgData(self, msg: dict):
        imgData = msg["img_data"]
        w, h = msg["w"], msg["h"]
        backend = self.backendLoader.getBackend(msg["config"])
        w, h, imgUpscaled = backend.upscaleImageData(imgData, w, h)
        return {
            "cmd": msg["cmd"],
            "w": w,
            "h": h,
            "img": imgUpscaled
        }


    @msghandler("token_count_borders")
    def tokenCountWithBorders(self, msg: dict):
        tokenizer = self.backendLoader.getBackend(msg["config"])
        count, borders = tokenizer.countWithChunkBorders(msg["text"])
        return {
            "cmd": msg["cmd"],
            "count": count,
            "borders": borders
        }


    @msghandler("embed_text")
    def embedText(self, msg: dict):
        embedding = self.embedBackend.getBackend().embedTextNumpyBytes(msg["text"])
        return {
            "cmd": msg["cmd"],
            "embedding": embedding
        }

    @msghandler("embed_img")
    def embedImage(self, msg: dict):
        imgFile = ImageFile.fromMsg(msg)
        embeddings = self.embedBackend.getBackend().embedImagesNumpyBytes([imgFile])
        return {
            "cmd": msg["cmd"],
            "embedding": embeddings[0]
        }

    @msghandler("embed_img_batch")
    def embedImageBatch(self, msg: dict):
        imgFiles = [ImageFile(path) for path in msg["imgs"]] # TODO: Use ImageCache
        embeddings = self.embedBackend.getBackend().embedImagesNumpyBytes(imgFiles)
        return {
            "cmd": msg["cmd"],
            "embeddings": embeddings
        }

    # @msghandler("embed_similarity")
    # def embeddingSimilarity(self, msg: dict):
    #     imgFile = ImageFile.fromMsg(msg)
    #     backend = self.backendLoader.getBackend(msg["config"])
    #     scores = backend.imgTextSimilarity(imgFile, msg["texts"])
    #     return {
    #         "cmd": msg["cmd"],
    #         "scores": scores
    #     }
