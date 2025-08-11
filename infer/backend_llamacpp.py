from typing import Callable
import math
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler
from host.imagecache import ImageFile
from .backend import InferenceBackend
from .devmap import DevMap


class LlamaCppBackend(InferenceBackend):
    def __init__(self, config: dict, **kwargs):
        super().__init__(config)

        deviceId = DevMap.getDeviceId()

        self.llm = Llama(
            model_path=config.get("model_path"),
            main_gpu=deviceId,
            n_gpu_layers=self._getNumGpuLayers(config, deviceId),
            n_ctx=config.get("ctx_length", 32768), # n_ctx should be increased to accommodate the image embedding
            n_batch=config.get("batch_size", 512),
            n_threads=config.get("num_threads", 11),
            flash_attn=True,
            seed=self.randomSeed(),
            #logits_all=True,# needed to make llava work (DEPRECATED - set llama_batch.logits instead)
            verbose=False,
            **kwargs
        )


    def _getNumGpuLayers(self, config: dict, deviceId: int) -> int:
        gpuLayersPercent = config.get("gpu_layers", 100)
        if gpuLayersPercent < 0:
            gpuLayersPercent = 100

        numLayers = self.readGgufLayers(config.get("model_path"))
        if numLayers == 0:
            print("Failed to read number of layers from GGUF file. Loading all layers to GPU.")
            return -1

        numGpuLayers = math.ceil((gpuLayersPercent / 100) * numLayers)
        print(f"Total GGUF layers: {numLayers}, GPU: {numGpuLayers} ({gpuLayersPercent}% on device {deviceId}), CPU: {numLayers-numGpuLayers}")
        return numGpuLayers

    # https://github.com/ggerganov/ggml/blob/master/docs/gguf.md
    @staticmethod
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


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        raise NotImplementedError()


    def answer(self, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        def getUserContent(prompt: str, index: int):
            return prompt.strip()

        return self._tryAnswer(getUserContent, prompts, systemPrompt)


    def _tryAnswer(self, userContentFunc: Callable, prompts: list[dict[str, str]], systemPrompt) -> dict[str, str]:
        try:
            return self._answer(userContentFunc, prompts, systemPrompt)
        except ValueError as ex:
            if str(ex).startswith("System role not supported"): # TODO: Always same error string?
                # Fallback: Include system prompt in first user message
                prompts = self.mergeSystemPrompt(prompts, systemPrompt)
                return self._answer(userContentFunc, prompts, None)
            else:
                raise ex


    def _answer(self, userContentFunc: Callable, prompts: list[dict[str, str]], systemPrompt: str | None) -> dict[str, str]:
        answers = {}

        for conversation in prompts:
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            for i, (name, prompt) in enumerate(conversation.items()):
                messages.append( {"role": "user", "content": userContentFunc(prompt, i)} )

                completion = self.llm.create_chat_completion(
                    messages = messages,
                    stop=self.stop,
                    seed=self.randomSeed(),
                    **self.config
                )

                msg = completion["choices"][0]["message"]
                answer = msg["content"].strip()
                messages.append( {"role": msg["role"], "content": answer} )
                answers[name] = answer

        return answers



class LlamaCppVisionBackend(LlamaCppBackend):
    def __init__(self, config: dict, chatHandlerType: type):
        chatHandler = chatHandlerType(
            clip_model_path=config.get("proj_path"),
            verbose=False
        )

        super().__init__(config, chat_handler=chatHandler)
        self.stop.append("USER:")
        self.stop.append("ASSISTANT:")


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt=None) -> dict[str, str]:
        imgURI = imgFile.getURI()

        def getUserContent(prompt: str, index: int):
            if index == 0:
                return [
                    {"type": "text", "text": prompt.strip()},
                    {"type": "image_url", "image_url": {"url": imgURI}}
                ]
            else:
                return prompt.strip()

        return self._tryAnswer(getUserContent, prompts, systemPrompt)



# https://github.com/abetlen/llama-cpp-python/pull/1989
class Gemma3ChatHandler(Llava15ChatHandler):
    # Chat Format:
    # '<bos><start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n'

    DEFAULT_SYSTEM_MESSAGE = None

    CHAT_FORMAT = (
        "{% if messages[0]['role'] == 'system' %}"
        "{% if messages[0]['content'] is string %}"
        "{% set first_user_prefix = messages[0]['content'] + '\n\n' %}"
        "{% else %}"
        "{% set first_user_prefix = messages[0]['content'][0]['text'] + '\n\n' %}"
        "{% endif %}"
        "{% set loop_messages = messages[1:] %}"
        "{% else %}"
        "{% set first_user_prefix = \"\" %}"
        "{% set loop_messages = messages %}"
        "{% endif %}"
        "{% for message in loop_messages %}"
        "{% if (message['role'] == 'user') != (loop.index0 % 2 == 0) %}"
        "{{ raise_exception(\"Conversation roles must alternate user/assistant/user/assistant/...\") }}"
        "{% endif %}"
        "{% if (message['role'] == 'assistant') %}"
        "{% set role = \"model\" %}"
        "{% else %}"
        "{% set role = message['role'] %}"
        "{% endif %}"
        "{{ '<start_of_turn>' + role + '\n' + (first_user_prefix if loop.first else \"\") }}"
        "{% if message['content'] is string %}"
        "{{ message['content'] | trim }}"
        "{% elif message['content'] is iterable %}"
        "{% for item in message['content'] %}"
        "{% if item['type'] == 'image_url' and item['image_url'] is string %}"
        "{{ '\n\n' + item['image_url'] + '\n\n' }}"
        "{% elif item['type'] == 'image_url' and item['image_url'] is mapping %}"
        "{{ '\n\n' + item['image_url']['url'] + '\n\n' }}"
        "{% elif item['type'] == 'text' %}"
        "{{ item['text'] | trim }}"
        "{% endif %}"
        "{% endfor %}"
        "{% else %}"
        "{{ raise_exception(\"Invalid content type\") }}"
        "{% endif %}"
        "{{ '<end_of_turn>\n' }}"
        "{% endfor %}"
        "{% if add_generation_prompt %}"
        "{{ '<start_of_turn>model\n' }}"
        "{% endif %}"
    )
