import os, math, time
from typing import Callable, Any
from typing_extensions import override
from llama_cpp import Llama, llama_chat_format
from llama_cpp.llama_cpp import llama_flash_attn_type
from llama_cpp.llama_multimodal import MTMDChatHandler, GenericMTMDChatHandler
#from llama_cpp._utils import suppress_stdout_stderr
from host.imagecache import ImageFile
from config import Config
from .backend import InferenceBackend
from .devmap import DevMap


def readChatTemplateFromFile(path: str) -> str:
    path = os.path.abspath(path)
    print(f"Reading chat template from file: '{path}'")
    with open(path, "rt") as file:
        return file.read()


# https://github.com/ggerganov/ggml/blob/master/docs/gguf.md
def readGgufLayers(modelPath: str) -> int:
    with open(modelPath, 'rb') as file:
        data = file.read(8192)
    if not data.startswith(b'GGUF'):
        return 0

    key = b'.block_count'
    pos = data.find(key)
    if pos < 0:
        return 0
    pos += len(key)

    fieldType = int.from_bytes(data[pos:pos+4], "little")
    match fieldType:
        case 0: fieldLen, fieldSigned = 1, False
        case 1: fieldLen, fieldSigned = 1, True
        case 2: fieldLen, fieldSigned = 2, False
        case 3: fieldLen, fieldSigned = 2, True
        case 4: fieldLen, fieldSigned = 4, False
        case 5: fieldLen, fieldSigned = 4, True
        case 10: fieldLen, fieldSigned = 8, False
        case 11: fieldLen, fieldSigned = 8, True
        case _: fieldLen, fieldSigned = 0, False

    pos += 4
    return int.from_bytes(data[pos:pos+fieldLen], "little", signed=fieldSigned)



class LlamaCppBackend(InferenceBackend):
    TPS_PERIOD    = 20
    TPS_EMA_ALPHA = 2 / (TPS_PERIOD + 1)

    def __init__(self, config: dict, **kwargs):
        self._supportsSystemPrompt = True

        self._tpsValues = list[float]()
        self._tpsEMA: float = -1

        deviceId = DevMap.getDeviceId()
        flashAttn = DevMap.isFlashAttentionAvailable()
        flashAttnType = llama_flash_attn_type.LLAMA_FLASH_ATTN_TYPE_ENABLED if flashAttn else llama_flash_attn_type.LLAMA_FLASH_ATTN_TYPE_DISABLED

        self.llm = Llama(
            model_path          = config.get("model_path"),
            main_gpu            = deviceId,
            n_gpu_layers        = self._getNumGpuLayers(config, deviceId),
            n_ctx               = config.get("ctx_length", 8192),  # must be large enough to accommodate the image embeddings
            n_batch             = config.get("batch_size", 512),
            n_threads           = config.get("num_threads", 11),
            flash_attn_type     = flashAttnType,
            seed                = self.randomSeed(),
            ctx_checkpoints     = 0,  # no branches in conversations, speedup
            verbose             = False,
            **kwargs
        )

        super().__init__(config)


    @classmethod
    def createWithFormatOverride(cls, config: dict) -> 'LlamaCppBackend':
        if chatFormatOverride := config.get("chat_format"):
            if os.sep in chatFormatOverride:
                backend = cls(config)
                chatTemplate = readChatTemplateFromFile(chatFormatOverride)
                backend.llm.chat_handler = JinjaChatFormatter.createChatHandler(backend.llm, chatTemplate)
            else:
                chatFormatOverride = chatFormatOverride.strip()
                print(f"Chat format override: '{chatFormatOverride}'")
                backend = cls(config, chat_format=chatFormatOverride)
        else:
            backend = cls(config)

        return backend


    @override
    def setConfig(self, config: dict):
        if sampleCfg := config.get(Config.INFER_PRESET_SAMPLECFG_KEY):
            self.config.update(sampleCfg)

        self.config["present_penalty"] = self.config.pop("presence_penalty", 0.0)

        enableThinking = self.config.pop("think", False)
        self.setThinking(enableThinking)

    def setThinking(self, enabled: bool):
        chatHandler = (
            self.llm.chat_handler
            or self.llm._chat_handlers.get(self.llm.chat_format)
            or llama_chat_format.get_chat_completion_handler(self.llm.chat_format)
        )

        # Must set both, 'enable_thinking' and 'extraTemplateArgs["enable_thinking"]'
        # because some MTMDChatHandler subclasses don't update the dict on __call__().
        thinkSet = False
        if hasattr(chatHandler, "enable_thinking"):
            chatHandler.enable_thinking = enabled
            thinkSet = True

        extraTemplateArgs = getattr(chatHandler, "extra_template_arguments", None)
        if isinstance(extraTemplateArgs, dict):
            extraTemplateArgs["enable_thinking"] = enabled
            thinkSet = True

        if enabled and not thinkSet:
            print("Warning: Thinking is enabled but chat handler has no 'enable_thinking' or 'extra_template_arguments' attribute")


    @staticmethod
    def _getNumGpuLayers(config: dict, deviceId: int) -> int:
        gpuLayersPercent = config.get("gpu_layers", 100)
        if gpuLayersPercent < 0:
            gpuLayersPercent = 100

        numLayers = readGgufLayers(config.get("model_path"))
        if numLayers == 0:
            print("Failed to read number of layers from GGUF file. Fallback to automatic allocation.")
            return -1  # -1 is auto, -2 would be all

        numGpuLayers = math.ceil((gpuLayersPercent / 100) * numLayers)
        print(f"Total GGUF layers: {numLayers}, GPU: {numGpuLayers} ({gpuLayersPercent}% on device {deviceId}), CPU: {numLayers-numGpuLayers}")
        return numGpuLayers


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        raise NotImplementedError()


    def answer(self, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        def getUserContent(prompt: str, index: int):
            return prompt.strip()

        return self._tryAnswer(getUserContent, prompts, systemPrompt)


    def _tryAnswer(self, userContentFunc: Callable, prompts: list[dict[str, str]], systemPrompt) -> dict[str, str]:
        if self._supportsSystemPrompt:
            try:
                return self._answer(userContentFunc, prompts, systemPrompt)
            except ValueError as ex:
                msg = str(ex).lower()
                if "system" in msg and "role" in msg:
                    print("System role not supported. Will merge system prompt into user prompt.")
                    self._supportsSystemPrompt = False
                else:
                    raise

        prompts = self.mergeSystemPrompt(prompts, systemPrompt)
        return self._answer(userContentFunc, prompts, None)


    def _answer(self, userContentFunc: Callable, prompts: list[dict[str, str]], systemPrompt: str | None) -> dict[str, str]:
        answers = {}

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(conversation.items()):
                messages.append( {"role": "user", "content": userContentFunc(prompt, i)} )

                t = time.monotonic_ns()

                # with suppress_stdout_stderr(disable=True):
                completion = self.llm.create_chat_completion(
                    messages,
                    stop=self.stop,
                    seed=self.randomSeed(),
                    **self.config
                )

                self._printSpeed(t, completion["usage"]["completion_tokens"])

                msg = completion["choices"][0]["message"]
                answer = msg["content"].strip()
                answer = self.stripReasoning(answer)
                messages.append( {"role": msg["role"], "content": answer} )
                answers[name] = answer

        return answers


    def _printSpeed(self, startTime: int, numTokens: int):
        t = (time.monotonic_ns() - startTime) / 1_000_000.0
        tps = 1000 * numTokens / t

        if self._tpsEMA > 0:
            self._tpsEMA = (tps * self.TPS_EMA_ALPHA) + (self._tpsEMA * (1.0 - self.TPS_EMA_ALPHA))
            avg = self._tpsEMA
        else:
            if len(self._tpsValues) < self.TPS_PERIOD:
                self._tpsValues.append(tps)

            avg = sum(self._tpsValues) / len(self._tpsValues)
            if len(self._tpsValues) >= self.TPS_PERIOD:
                self._tpsEMA = max(avg, 0.0001)

        print(f"Generated {numTokens} tokens in {t:.02f} ms (effective {tps:.02f} tok/s, smooth {avg:.02f} tok/s)")



class LlamaCppVisionBackend(LlamaCppBackend):
    def __init__(self, config: dict, chatHandlerType: type[MTMDChatHandler] | str | None = None, jinjaFile: str = "", **chatHandlerKwargs):
        chatHandlerArgs: dict[str, Any] = {
            "verbose": False,
        }
        chatHandlerArgs.update(chatHandlerKwargs)

        if chatFormatOverride := config.get("chat_format"):
            if os.sep in chatFormatOverride:
                jinjaFile = chatFormatOverride
            else:
                chatHandlerType = chatFormatOverride

        if jinjaFile:
            chatTemplate = readChatTemplateFromFile(jinjaFile)
            chatHandlerArgs["chat_template_override"] = chatTemplate
            chatHandler = self._createChatHandler(config, chatHandlerType, chatHandlerArgs)
            chatHandler._chat_format_parser_tags = [tag for tag in GenericMTMDChatHandler.KNOWN_MEDIA_TAGS if tag in chatTemplate]
        else:
            chatHandler = self._createChatHandler(config, chatHandlerType, chatHandlerArgs)

        # Bypass re-encoding of images
        self._imgBytes: dict[str, bytes] = {}
        chatHandler._load_image = self._getImage

        self.sampleFps = 2.0

        super().__init__(config, chat_handler=chatHandler)
        self.stop += ["USER:", "ASSISTANT:"]

        # Workaround: GenericMTMDChatHandler doesn't update the chat template after loading from model
        if not jinjaFile and isinstance(chatHandler, GenericMTMDChatHandler):
            chatHandler.chat_format = None
            chatHandler._resolve_chat_format(self.llm)
            chatHandler._change_chat_template(chatHandler.chat_format)


    def _createChatHandler(self, config: dict, chatHandlerType: type[MTMDChatHandler] | str | None, args: dict) -> MTMDChatHandler:
        if not chatHandlerType:
            chatHandlerType = GenericMTMDChatHandler
        elif isinstance(chatHandlerType, str):
            chatHandlerType = self.getChatHandlerClass(chatHandlerType)

        args["mmproj_path"] = config["proj_path"]
        if chatHandlerType is GenericMTMDChatHandler:
            args["chat_format"] = None

        print(f"Using chat handler: {chatHandlerType.__name__}")
        return chatHandlerType(**args)

    @staticmethod
    def getChatHandlerClass(name: str) -> type[MTMDChatHandler]:
        import inspect
        classes = {
            clsName.lower(): clsObj
            for clsName, clsObj in inspect.getmembers(llama_chat_format, inspect.isclass)
            if issubclass(clsObj, MTMDChatHandler)
        }

        try:
            return classes[name.strip().lower()]
        except KeyError:
            raise ValueError(f"Unknown chat handler class '{name}'")


    @override
    def setConfig(self, config: dict):
        super().setConfig(config)
        self.sampleFps = self.config.pop("fps", 2.0)


    @override
    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        try:
            self._imgBytes = self._loadMedia(imgFile)
            return self._tryAnswer(self._getUserContent, prompts, systemPrompt)
        except ValueError as ex:
            if imgFile.isVideo() and "media marker mismatch" in str(ex).lower():
                raise ValueError("This model does not support video input (media marker mismatch)")
            raise
        finally:
            self._imgBytes.clear()


    def _loadMedia(self, imgFile: ImageFile) -> dict[str, bytes]:
        # Need unique URLs per file because of caching
        if imgFile.isVideo():
            frameBytes = list(imgFile.getVideoFramesEncodedBytes(self.sampleFps))
            count = len(frameBytes)
            return {
                f"qapyq://[{i}/{count}]{imgFile.file}": buf
                for i, buf in enumerate(frameBytes, 1)
            }
        else:
            return { f"qapyq://{imgFile.file}": imgFile.getEncodedBytes() }

    def _getUserContent(self, prompt: str, index: int) -> str | list[dict[str, str]]:
        if index != 0:
            return prompt.strip()

        content = [{"type": "text", "text": prompt.strip()}]
        for url in self._imgBytes:
            content.append({"type": "image_url", "image_url": url})
        return content

    def _getImage(self, image_url: str) -> bytes:
        return self._imgBytes[image_url]  # This bypasses llama-cpp-python's internal loading which would encode the image again



class JinjaChatFormatter(llama_chat_format.Jinja2ChatFormatter):
    "Adds an enable_thinking attribute to the returned chat handler closure which is then modified in LlamaCppBackend.setThinking()"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._func = None

    @override
    def __call__(self, *args, **kwargs):
        kwargs["enable_thinking"] = getattr(self._func, "enable_thinking", False) if self._func else False
        return super().__call__(*args, **kwargs)

    @override
    def to_chat_handler(self):
        self._func = super().to_chat_handler()
        setattr(self._func, "enable_thinking", False)
        return self._func

    @classmethod
    def createChatHandler(cls, llm: Llama, template: str):
        # From Llama.__init__()
        eos_token_id = llm.token_eos()
        bos_token_id = llm.token_bos()
        eot_token_id = llm.token_eot()
        sep_token_id = llm.token_sep()
        nl_token_id = llm.token_nl()
        pad_token_id = llm.token_pad()
        mask_token_id = llm.token_mask()

        def _token_text(token_id: int) -> str:
            return llm._model.token_get_text(token_id) if token_id != -1 else ""

        bos_token = _token_text(bos_token_id)
        eos_token = _token_text(eos_token_id)

        special_tokens_map = {
            name: text
            for name, token_id in {
                "eot_token": eot_token_id,
                "sep_token": sep_token_id,
                "nl_token": nl_token_id,
                "pad_token": pad_token_id,
                "mask_token": mask_token_id,
            }.items()
            if token_id != -1 and (text := _token_text(token_id))
        }

        stop_token_ids = [
            token_id
            for token_id in (eos_token_id, eot_token_id)
            if token_id != -1
        ]

        if not stop_token_ids:
            stop_token_ids = None

        return cls(
            template=template,
            eos_token=eos_token,
            bos_token=bos_token,
            stop_token_ids=stop_token_ids,
            special_tokens_map=special_tokens_map,
        ).to_chat_handler()



# def readGgufMetadata(model_path: str, keys: list[str]) -> dict[str, str]:
#     if not os.path.exists(model_path):
#         raise ValueError(f"GGUF model path does not exist: {model_path}")

#     model_params = llama_cpp.llama_model_default_params()
#     model_params.vocab_only = True  # skip loading weights

#     model = llama_cpp.llama_model_load_from_file(model_path.encode(), model_params)
#     if not model:
#         raise RuntimeError(f"Failed to load GGUF metadata from '{model_path}'")

#     metadata: dict[str, str] = {}

#     try:
#         buf = bytes(512)
#         for key in keys:
#             n = llama_cpp.llama_model_meta_val_str(model, key.encode(), buf, len(buf))
#             if n > 0:
#                 metadata[key] = buf[:n].decode("utf-8", errors='replace')

#     finally:
#         llama_cpp.llama_model_free(model)

#     return metadata
