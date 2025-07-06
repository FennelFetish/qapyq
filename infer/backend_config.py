from enum import Enum
from typing import Any


class BackendTypes(Enum):
    LLAMA_CPP    = "llama.cpp"
    TRANSFORMERS = "transformers"
    #VLLM         = "vllm"
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
    #BackendTypes.VLLM:          BackendPathModes.FOLDER,
    BackendTypes.ONNX:          BackendPathModes.FILE,
    BackendTypes.TORCH:         BackendPathModes.FOLDER,
    BackendTypes.ULTRALYTICS:   BackendPathModes.FILE,
    BackendTypes.SPANDREL:      BackendPathModes.FILE,
}


class BackendDef:
    def __init__(self, name: str, type: BackendTypes, pathMode: BackendPathModes | None = None):
        self.name = name
        self.type = type
        self.pathMode = pathMode if pathMode is not None else DefaultPathModes[type]

class MaskBackendDef(BackendDef):
    def __init__(self, name: str, type: BackendTypes, supportsClasses: bool, pathMode: BackendPathModes | None = None):
        super().__init__(name, type, pathMode)
        self.supportsClasses = supportsClasses



BackendsCaption = {
    "Florence-2":       BackendDef("florence2",     BackendTypes.TRANSFORMERS),
    #"Gemma-3":          BackendDef("gemma3",        BackendTypes.LLAMA_CPP),
    "InternVL":         BackendDef("internvl2",     BackendTypes.TRANSFORMERS),
    #"InternVL2/2.5 VLLM":BackendDef("internvl2-vllm",BackendTypes.VLLM),
    "JoyCaption":       BackendDef("joycaption",    BackendTypes.TRANSFORMERS),
    "MiniCPM-V-2.6":    BackendDef("minicpm",       BackendTypes.LLAMA_CPP),
    "Molmo":            BackendDef("molmo",         BackendTypes.TRANSFORMERS),
    #"Molmo VLLM":       BackendDef("molmo-vllm",    BackendTypes.VLLM),
    "Moondream":        BackendDef("moondream",     BackendTypes.LLAMA_CPP),
    "Ovis-1.6":         BackendDef("ovis16",        BackendTypes.TRANSFORMERS),
    "Ovis-2.0":         BackendDef("ovis2",         BackendTypes.TRANSFORMERS),
    "Qwen2-VL":         BackendDef("qwen2vl",       BackendTypes.TRANSFORMERS),
    "Qwen2.5-VL":       BackendDef("qwen25vl",      BackendTypes.TRANSFORMERS),
    #"Qwen2.5-VL VLLM":  BackendDef("qwen25vl-vllm", BackendTypes.VLLM)
}

# TODO: Allow loading of caption models as LLM.
#       Set visual layers to 0? -> No, load as defined in config to prevent reloading.
BackendsLLM = {
    "GGUF":             BackendDef("gguf", BackendTypes.LLAMA_CPP)
}

BackendsTag = {
    "WD":               BackendDef("wd",     BackendTypes.ONNX),
    "JoyTag":           BackendDef("joytag", BackendTypes.TORCH)
}

BackendsMask = {
    "BriaAI RMBG-2.0":      MaskBackendDef("bria-rmbg",         BackendTypes.TRANSFORMERS, False),
    "Florence-2 Detect":    MaskBackendDef("florence2-detect",  BackendTypes.TRANSFORMERS, True),
    "Florence-2 Segment":   MaskBackendDef("florence2-segment", BackendTypes.TRANSFORMERS, True),
    "Inspyrenet RemBg":     MaskBackendDef("inspyrenet",        BackendTypes.TORCH,        False, BackendPathModes.FILE),
    "Qwen2.5-VL Detect":    MaskBackendDef("qwen25vl-detect",   BackendTypes.TRANSFORMERS, True),
    "Yolo Detect":          MaskBackendDef("yolo-detect",       BackendTypes.ULTRALYTICS,  True)
}

BackendsUpscale = {
    "Upscale":          BackendDef("upscale", BackendTypes.SPANDREL)
}



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
            case "florence2" | "florence2-detect" | "florence2-segment":
                from .backend_florence2 import Florence2Backend
                return Florence2Backend(config)
            case "gemma3":
                from .backend_llamacpp import LlamaCppVisionBackend
                from llama_cpp.llama_chat_format import Llava15ChatHandler
                return LlamaCppVisionBackend(config, Llava15ChatHandler)
            case "internvl2":
                from .backend_internvl2 import InternVL2Backend
                return InternVL2Backend(config)
            case "internvl2-vllm":
                from .backend_vllm_internvl import VllmInternVlBackend
                return VllmInternVlBackend(config)
            case "joycaption":
                from .backend_joycaption import JoyCaptionBackend
                return JoyCaptionBackend(config)
            case "minicpm":
                from .backend_llamacpp import LlamaCppVisionBackend
                from llama_cpp.llama_chat_format import MiniCPMv26ChatHandler
                return LlamaCppVisionBackend(config, MiniCPMv26ChatHandler)
            case "molmo":
                from .backend_molmo import MolmoBackend
                return MolmoBackend(config)
            case "molmo-vllm":
                from .backend_vllm_molmo import VllmMolmoBackend
                return VllmMolmoBackend(config)
            case "moondream":
                from .backend_llamacpp import LlamaCppVisionBackend
                from llama_cpp.llama_chat_format import MoondreamChatHandler
                return LlamaCppVisionBackend(config, MoondreamChatHandler)
            case "ovis16":
                from .backend_ovis16 import Ovis16Backend
                return Ovis16Backend(config)
            case "ovis2":
                from .backend_ovis2 import Ovis2Backend
                return Ovis2Backend(config)
            case "qwen2vl":
                from .backend_qwen2vl import Qwen2VLBackend
                return Qwen2VLBackend(config)
            case "qwen25vl" | "qwen25vl-detect":
                from .backend_qwen25vl import Qwen25VLBackend
                return Qwen25VLBackend(config)
            case "qwen25vl-vllm":
                from .backend_vllm_qwen25vl import VllmQwen25Backend
                return VllmQwen25Backend(config)

            # LLM
            case "gguf":
                from .backend_llamacpp import LlamaCppBackend
                return LlamaCppBackend(config)

            # Tag
            case "joytag":
                from .tag_joytag import JoyTag
                return JoyTag(config)
            case "wd":
                from .tag_wd import WDTag
                return WDTag(config)

            # Masking
            case "bria-rmbg":
                from .mask_briarmbg import BriaRmbgMask
                return BriaRmbgMask(config)
            case "inspyrenet":
                from .mask_inspyrenet import InspyrenetMask
                return InspyrenetMask(config)
            case "yolo-detect":
                from .mask_yolo import YoloMask
                return YoloMask(config)

            # Upscale
            case "upscale":
                from .upscale import UpscaleBackend
                return UpscaleBackend(config)

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
