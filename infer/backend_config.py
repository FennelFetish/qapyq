from enum import Enum
from typing import Any


class BackendTypes(Enum):
    LLAMA_CPP    = "llama.cpp"
    TRANSFORMERS = "transformers"
    ONNX         = "onnx"
    TORCH        = "torch"
    ULTRALYTICS  = "ultralytics"
    SPANDREL     = "spandrel"

class BackendPathModes(Enum):
    FILE   = "file"
    FOLDER = "folder"


DefaultPathModes = {
    BackendTypes.LLAMA_CPP:     BackendPathModes.FILE,
    BackendTypes.TRANSFORMERS:  BackendPathModes.FOLDER,
    BackendTypes.ONNX:          BackendPathModes.FILE,
    BackendTypes.TORCH:         BackendPathModes.FOLDER,
    BackendTypes.ULTRALYTICS:   BackendPathModes.FILE,
    BackendTypes.SPANDREL:      BackendPathModes.FILE,
}


class BackendDef:
    def __init__(self, name: str, type: BackendTypes, pathMode: BackendPathModes | None = None, features: set[str] = set()):
        self.name = name
        self.type = type
        self.pathMode = pathMode if pathMode is not None else DefaultPathModes[type]
        self.features = features


BackendsCaption = {
    "Generic GGUF":     BackendDef("gguf-mtmd",         BackendTypes.LLAMA_CPP,         features={"think","video"}),
    "Florence-2":       BackendDef("florence2",         BackendTypes.TRANSFORMERS),
    "Gemma-3":          BackendDef("gemma3",            BackendTypes.LLAMA_CPP,         features={"video"}),
    "Gemma-4":          BackendDef("gemma4",            BackendTypes.LLAMA_CPP,         features={"think","video"}),
    "InternVL":         BackendDef("internvl2",         BackendTypes.TRANSFORMERS,      features={"video"}),
    "JoyCaption":       BackendDef("joycaption",        BackendTypes.TRANSFORMERS),
    "JoyCaption GGUF":  BackendDef("joycaption-gguf",   BackendTypes.LLAMA_CPP),
    "MiniCPM-V":        BackendDef("minicpm",           BackendTypes.LLAMA_CPP,         features={"think","video"}),
    "Molmo":            BackendDef("molmo",             BackendTypes.TRANSFORMERS),
    "Moondream":        BackendDef("moondream",         BackendTypes.LLAMA_CPP),
    "Ovis-1.6":         BackendDef("ovis16",            BackendTypes.TRANSFORMERS),
    "Ovis-2.0":         BackendDef("ovis2",             BackendTypes.TRANSFORMERS),
    "Ovis-2.5":         BackendDef("ovis25",            BackendTypes.TRANSFORMERS),
    "Qwen-VL 2":        BackendDef("qwen2vl",           BackendTypes.TRANSFORMERS),
    "Qwen-VL 2.5/3":    BackendDef("qwen25vl",          BackendTypes.TRANSFORMERS,      features={"video"}),
    "Qwen 3.5/3.6":     BackendDef("qwen35",            BackendTypes.LLAMA_CPP,         features={"think","video"}),
}

BackendsLLM = {
    "Generic GGUF":     BackendDef("gguf",              BackendTypes.LLAMA_CPP,         features={"think"})
}

BackendsTag = {
    "JoyTag":           BackendDef("joytag",            BackendTypes.TORCH),
    "PixAI":            BackendDef("pixai-tag",         BackendTypes.ONNX),
    "WD":               BackendDef("wd",                BackendTypes.ONNX)
}

BackendsMask = {
    "BriaAI RMBG-2.0":          BackendDef("bria-rmbg",         BackendTypes.TRANSFORMERS),
    "Florence-2 Detect":        BackendDef("florence2-detect",  BackendTypes.TRANSFORMERS,      features={"classes"}),
    "Florence-2 Segment":       BackendDef("florence2-segment", BackendTypes.TRANSFORMERS,      features={"classes"}),
    "Inspyrenet RemBg":         BackendDef("inspyrenet",        BackendTypes.TORCH, BackendPathModes.FILE),
    "Qwen-VL 2.5/3 Detect":     BackendDef("qwen25vl-detect",   BackendTypes.TRANSFORMERS,      features={"classes"}),
    "Qwen 3.5/3.6 Detect":      BackendDef("qwen35-detect",     BackendTypes.LLAMA_CPP,         features={"classes"}),
    "Yolo Detect":              BackendDef("yolo-detect",       BackendTypes.ULTRALYTICS,       features={"classes"})
}

BackendsUpscale = {
    "Upscale":          BackendDef("upscale",           BackendTypes.SPANDREL)
}

BackendsEmbedding = {
    "CLIP":             BackendDef("clip",              BackendTypes.TRANSFORMERS),
    "SigLIP":           BackendDef("siglip",            BackendTypes.TRANSFORMERS),
    "SigLIP ONNX":      BackendDef("siglip-onnx",       BackendTypes.ONNX, BackendPathModes.FOLDER),
}



def backendDefForName(backends: dict[str, BackendDef], name: str) -> BackendDef | None:
    return next((backend for backend in backends.values() if backend.name == name), None)



class BackendLoader:
    def __init__(self):
        self.backends: dict[Any, object] = dict()

    @staticmethod
    def getKey(config: dict) -> Any:
        return config["model_path"]

    def getBackend(self, config: dict, setup=False):
        if not config:
            raise ValueError("Cannot load backend without config")

        key = self.getKey(config)

        backend = self.backends.get(key)
        if not backend:
            backend = self._loadBackend(config)
            self.backends[key] = backend
        elif setup:
            backend.setConfig(config)

        return backend

    def _loadBackend(self, config: dict):
        match backendName := config.get("backend"):
            # Caption / LLM
            case "gguf-mtmd":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config).setThinkEnd("</think>")
            case "florence2" | "florence2-detect" | "florence2-segment":
                from .caption.florence2 import Florence2Backend
                return Florence2Backend(config)
            case "gemma3":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, "Gemma3ChatHandler")
            case "gemma4":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, "Gemma4ChatHandler").setThinkEnd("<channel|>", "<|channel>")
            case "internvl2":
                from .caption.internvl import InternVL2Backend
                return InternVL2Backend(config)
            case "joycaption":
                from .caption.joycaption import JoyCaptionBackend
                return JoyCaptionBackend(config)
            case "joycaption-gguf":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, jinjaFile="./res/chat-templates/joycaption.jinja")
            case "minicpm":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, "MiniCPMV46ChatHandler").setThinkEnd("</think>")
            case "molmo":
                from .caption.molmo import MolmoBackend
                return MolmoBackend(config)
            case "moondream":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, "MoondreamChatHandler")
            case "ovis16":
                from .caption.ovis16 import Ovis16Backend
                return Ovis16Backend(config)
            case "ovis2":
                from .caption.ovis2 import Ovis2Backend
                return Ovis2Backend(config)
            case "ovis25":
                from .caption.ovis25 import Ovis25Backend
                return Ovis25Backend(config)
            case "qwen2vl":
                from .caption.qwen2vl import Qwen2VLBackend
                return Qwen2VLBackend(config)
            case "qwen25vl" | "qwen25vl-detect":
                from .caption.qwen25vl import getQwenVLBackend
                return getQwenVLBackend(config)
            case "qwen35":
                from .caption.llamacpp import LlamaCppVisionBackend
                return LlamaCppVisionBackend(config, "Qwen35ChatHandler", image_min_tokens=1024, preserve_thinking=True).setThinkEnd("</think>")

            # LLM
            case "gguf":
                from .caption.llamacpp import LlamaCppBackend
                return LlamaCppBackend.createWithFormatOverride(config).setThinkEnd("</think>")

            # Tag
            case "joytag":
                from .tag.joytag import JoyTag
                return JoyTag(config)
            case "pixai-tag":
                from .tag.pixai import PixAiTag
                return PixAiTag(config)
            case "wd":
                from .tag.wd import WDTag
                return WDTag(config)

            # Masking
            case "bria-rmbg":
                from .mask.briarmbg import BriaRmbgMask
                return BriaRmbgMask(config)
            case "inspyrenet":
                from .mask.inspyrenet import InspyrenetMask
                return InspyrenetMask(config)
            case "qwen35-detect":
                from .mask.llamacpp_detect import Qwen35DetectBackend
                return Qwen35DetectBackend(config, "Qwen35ChatHandler", image_min_tokens=1024)
            case "yolo-detect":
                from .mask.yolo import YoloMask
                return YoloMask(config)

            # Upscale
            case "upscale":
                from .misc.upscale import UpscaleBackend
                return UpscaleBackend(config)

            # Embedding
            case "clip":
                from .embedding.clip import Clip
                return Clip(config)
            case "siglip":
                from .embedding.siglip import Siglip
                return Siglip(config)
            case "siglip-onnx":
                from .embedding.siglip_onnx import SiglipOnnx
                return SiglipOnnx(config)

            # VAE
            case "vae":
                from .misc.vae import VaeBackend
                return VaeBackend(config)

            # Tokenizer
            case "tokens":
                from .misc.tokens import Tokens
                return Tokens(config)

        raise ValueError(f"Unknown backend: '{backendName}'")



class LastBackendLoader:
    def __init__(self, backendLoader: BackendLoader):
        self.loader = backendLoader
        self.key: Any | None = None

    def getBackend(self, config: dict | None = None):
        if self.key:
            backend = self.loader.backends.get(self.key)
            if config:
                backend.setConfig(config)
        else:
            assert(config)
            backend = self.loader.getBackend(config)
            self.key = BackendLoader.getKey(config)

        return backend
