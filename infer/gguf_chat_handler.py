from __future__ import annotations

import os
import sys
import json
import ctypes

from contextlib import ExitStack
from typing import Dict, Iterator, List, Optional, Union

from jinja2.sandbox import ImmutableSandboxedEnvironment

import llama_cpp.llama_cpp as llama_cpp
import llama_cpp.llama as llama
import llama_cpp.llama_types as llama_types
import llama_cpp.llama_grammar as llama_grammar

from llama_cpp.llama_chat_format import (
    _get_system_message,
    _grammar_for_response_format,
    _convert_completion_to_chat_function,
    _convert_completion_to_chat
)

from llama_cpp._utils import suppress_stdout_stderr



def read_gguf_chat_template(model_path: str) -> str:
    "Extract tokenizer.chat_template from a GGUF file's metadata without loading the full model weights."

    if not os.path.exists(model_path):
        raise ValueError(f"GGUF model path does not exist: {model_path}")

    model_params = llama_cpp.llama_model_default_params()
    model_params.vocab_only = True  # skip loading weights

    model = llama_cpp.llama_model_load_from_file(model_path.encode(), model_params)
    if not model:
        raise RuntimeError(f"Failed to load GGUF metadata from '{model_path}'")

    try:
        key = b"tokenizer.chat_template"
        buf_size = 64 * 1024
        buf = bytes(buf_size)
        n = llama_cpp.llama_model_meta_val_str(model, key, buf, buf_size)
    finally:
        llama_cpp.llama_model_free(model)

    if n < 0:
        raise RuntimeError(f"Failed to extract chat template from GGUF model '{model_path}'")

    return buf.decode("utf-8")



# Based on llama_cpp.llama_chat_format.Llava15ChatHandler
class JinjaChatHandler:
    DEFAULT_SYSTEM_MESSAGE: Optional[str] = (
        "A chat between a curious human and an artificial intelligence assistant. The assistant gives helpful, detailed, and polite answers to the human's questions."
    )

    def __init__(self, model_path: str, clip_model_path: str, verbose: bool = True, enable_thinking: bool = False):
        import llama_cpp.mtmd_cpp as mtmd_cpp

        self.clip_model_path = clip_model_path
        self.verbose = verbose
        self.enable_thinking = enable_thinking

        with suppress_stdout_stderr(disable=verbose):
            self.chat_format = read_gguf_chat_template(model_path)

        self._mtmd_cpp = mtmd_cpp
        self._exit_stack = ExitStack()
        self.mtmd_ctx: Optional[mtmd_cpp.mtmd_context_p] = None

        if not os.path.exists(clip_model_path):
            raise ValueError(f"Clip model path does not exist: {clip_model_path}")


    def _init_mtmd_context(self, llama_model: llama.Llama):
        """Initialize mtmd context with the llama model."""
        if self.mtmd_ctx is not None:
            return  # Already initialized

        with suppress_stdout_stderr(disable=self.verbose):
            # Get default parameters
            ctx_params = self._mtmd_cpp.mtmd_context_params_default()
            ctx_params.use_gpu = True  # TODO: Make this configurable
            ctx_params.print_timings = self.verbose
            ctx_params.n_threads = llama_model.n_threads
            ctx_params.flash_attn_type = (
                llama_cpp.LLAMA_FLASH_ATTN_TYPE_ENABLED
                if (
                    llama_model.context_params.flash_attn_type
                    == llama_cpp.LLAMA_FLASH_ATTN_TYPE_ENABLED
                )
                else llama_cpp.LLAMA_FLASH_ATTN_TYPE_DISABLED
            )

            # Initialize mtmd context
            self.mtmd_ctx = self._mtmd_cpp.mtmd_init_from_file(
                self.clip_model_path.encode(), llama_model.model, ctx_params
            )

            if self.mtmd_ctx is None:
                raise ValueError(
                    f"Failed to load mtmd context from: {self.clip_model_path}"
                )

            # Check if vision is supported
            if not self._mtmd_cpp.mtmd_support_vision(self.mtmd_ctx):
                raise ValueError("Vision is not supported by this model")

            def mtmd_free():
                with suppress_stdout_stderr(disable=self.verbose):
                    if self.mtmd_ctx is not None:
                        self._mtmd_cpp.mtmd_free(self.mtmd_ctx)
                        self.mtmd_ctx = None

            self._exit_stack.callback(mtmd_free)


    def __call__(
        self,
        *,
        llama: llama.Llama,
        messages: List[llama_types.ChatCompletionRequestMessage],
        functions: Optional[List[llama_types.ChatCompletionFunction]] = None,
        function_call: Optional[llama_types.ChatCompletionRequestFunctionCall] = None,
        tools: Optional[List[llama_types.ChatCompletionTool]] = None,
        tool_choice: Optional[llama_types.ChatCompletionToolChoiceOption] = None,
        temperature: float = 0.2,
        top_p: float = 0.95,
        top_k: int = 40,
        min_p: float = 0.05,
        typical_p: float = 1.0,
        stream: bool = False,
        stop: Optional[Union[str, List[str]]] = [],
        seed: Optional[int] = None,
        response_format: Optional[
            llama_types.ChatCompletionRequestResponseFormat
        ] = None,
        max_tokens: Optional[int] = None,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
        repeat_penalty: float = 1.1,
        tfs_z: float = 1.0,
        mirostat_mode: int = 0,
        mirostat_tau: float = 5.0,
        mirostat_eta: float = 0.1,
        model: Optional[str] = None,
        logits_processor: Optional[llama.LogitsProcessorList] = None,
        grammar: Optional[llama.LlamaGrammar] = None,
        logit_bias: Optional[Dict[str, float]] = None,
        logprobs: Optional[bool] = None,
        top_logprobs: Optional[int] = None,
        **kwargs,  # type: ignore
    ) -> Union[
        llama_types.CreateChatCompletionResponse,
        Iterator[llama_types.CreateChatCompletionStreamResponse],
    ]:
        # Initialize mtmd context
        self._init_mtmd_context(llama)
        assert self.mtmd_ctx is not None

        system_prompt = _get_system_message(messages)
        if system_prompt == "" and self.DEFAULT_SYSTEM_MESSAGE is not None:
            messages = [
                llama_types.ChatCompletionRequestSystemMessage(
                    role="system", content=self.DEFAULT_SYSTEM_MESSAGE
                )
            ] + messages

        # Get the default media marker
        media_marker = self._mtmd_cpp.mtmd_default_marker().decode("utf-8")

        # Extract image bytes, modify messages and replace image content with media markers
        messages, images = self._extract_image_bytes(messages, media_marker)

        template = ImmutableSandboxedEnvironment(
            trim_blocks=True,
            lstrip_blocks=True,
        ).from_string(self.chat_format)

        text = template.render(
            messages=messages,
            add_generation_prompt=True,
            eos_token=llama.detokenize([llama.token_eos()]),
            bos_token=llama.detokenize([llama.token_bos()]),
            enable_thinking=self.enable_thinking
        )

        if self.verbose:
            print(text, file=sys.stderr)

        # Create bitmaps from images
        bitmaps = []
        bitmap_cleanup = []
        try:
            for image_bytes in images:
                bitmap = self._create_bitmap_from_bytes(image_bytes)
                bitmaps.append(bitmap)
                bitmap_cleanup.append(bitmap)

            # Create input text structure
            input_text = self._mtmd_cpp.mtmd_input_text()
            input_text.text = text.encode("utf-8")
            input_text.add_special = True
            input_text.parse_special = True

            # Create input chunks
            chunks = self._mtmd_cpp.mtmd_input_chunks_init()
            if chunks is None:
                raise ValueError("Failed to create input chunks")

            try:
                # Tokenize text and images together
                bitmap_array = (self._mtmd_cpp.mtmd_bitmap_p_ctypes * len(bitmaps))(
                    *bitmaps
                )
                result = self._mtmd_cpp.mtmd_tokenize(
                    self.mtmd_ctx,
                    chunks,
                    ctypes.byref(input_text),
                    bitmap_array,
                    len(bitmaps),
                )

                if result != 0:
                    raise ValueError(f"Failed to tokenize input: error code {result}")

                # Reset llama context
                llama.reset()
                llama._ctx.kv_cache_clear()

                # Process each chunk
                #n_past = llama_cpp.llama_pos(0)
                n_chunks = self._mtmd_cpp.mtmd_input_chunks_size(chunks)

                for i in range(n_chunks):
                    chunk = self._mtmd_cpp.mtmd_input_chunks_get(chunks, i)
                    if chunk is None:
                        continue

                    chunk_type = self._mtmd_cpp.mtmd_input_chunk_get_type(chunk)

                    if chunk_type == self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_TEXT:
                        # Handle text chunk
                        n_tokens_out = ctypes.c_size_t()
                        tokens_ptr = self._mtmd_cpp.mtmd_input_chunk_get_tokens_text(
                            chunk, ctypes.byref(n_tokens_out)
                        )

                        if tokens_ptr and n_tokens_out.value > 0:
                            # Convert ctypes array to Python list
                            tokens = [tokens_ptr[j] for j in range(n_tokens_out.value)]

                            if llama.n_tokens + len(tokens) > llama.n_ctx():
                                raise ValueError(
                                    f"Prompt exceeds n_ctx: {llama.n_tokens + len(tokens)} > {llama.n_ctx()}"
                                )
                            llama.eval(tokens)

                    elif chunk_type in [
                        self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_IMAGE,
                        self._mtmd_cpp.MTMD_INPUT_CHUNK_TYPE_AUDIO,
                    ]:
                        # Handle image/audio chunk using helper
                        chunk_n_tokens = self._mtmd_cpp.mtmd_input_chunk_get_n_tokens(
                            chunk
                        )

                        if llama.n_tokens + chunk_n_tokens > llama.n_ctx():
                            raise ValueError(
                                f"Prompt exceeds n_ctx: {llama.n_tokens + chunk_n_tokens} > {llama.n_ctx()}"
                            )

                        new_n_past = llama_cpp.llama_pos(0)
                        result = self._mtmd_cpp.mtmd_helper_eval_chunk_single(
                            self.mtmd_ctx,
                            llama._ctx.ctx,
                            chunk,
                            llama_cpp.llama_pos(llama.n_tokens),
                            llama_cpp.llama_seq_id(0),
                            llama.n_batch,
                            False,  # logits_last
                            ctypes.byref(new_n_past),
                        )

                        if result != 0:
                            raise ValueError(
                                f"Failed to evaluate chunk: error code {result}"
                            )

                        # Update llama's token count
                        llama.n_tokens = new_n_past.value

                # Get prompt tokens to avoid a cache miss
                prompt = llama.input_ids[: llama.n_tokens].tolist()

            finally:
                self._mtmd_cpp.mtmd_input_chunks_free(chunks)

        finally:
            # Cleanup bitmaps
            for bitmap in bitmap_cleanup:
                self._mtmd_cpp.mtmd_bitmap_free(bitmap)

        # Handle response format and tools (same as before)
        if response_format is not None and response_format["type"] == "json_object":
            grammar = _grammar_for_response_format(response_format)

        # Convert legacy functions to tools
        if functions is not None:
            tools = [
                {
                    "type": "function",
                    "function": function,
                }
                for function in functions
            ]

        # Convert legacy function_call to tool_choice
        if function_call is not None:
            if isinstance(function_call, str) and (
                function_call == "none" or function_call == "auto"
            ):
                tool_choice = function_call
            if isinstance(function_call, dict) and "name" in function_call:
                tool_choice = {
                    "type": "function",
                    "function": {
                        "name": function_call["name"],
                    },
                }

        tool = None
        if (
            tool_choice is not None
            and isinstance(tool_choice, dict)
            and tools is not None
        ):
            name = tool_choice["function"]["name"]
            tool = next((t for t in tools if t["function"]["name"] == name), None)
            if tool is None:
                raise ValueError(f"Tool choice '{name}' not found in tools.")
            schema = tool["function"]["parameters"]
            try:
                # create grammar from json schema
                grammar = llama_grammar.LlamaGrammar.from_json_schema(
                    json.dumps(schema), verbose=llama.verbose
                )
            except Exception as e:
                if llama.verbose:
                    print(str(e), file=sys.stderr)
                grammar = llama_grammar.LlamaGrammar.from_string(
                    llama_grammar.JSON_GBNF, verbose=llama.verbose
                )

        completion_or_chunks = llama.create_completion(
            prompt=prompt,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            typical_p=typical_p,
            logprobs=top_logprobs if logprobs else None,
            stream=stream,
            stop=stop,
            seed=seed,
            max_tokens=max_tokens,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            repeat_penalty=repeat_penalty,
            tfs_z=tfs_z,
            mirostat_mode=mirostat_mode,
            mirostat_tau=mirostat_tau,
            mirostat_eta=mirostat_eta,
            model=model,
            logits_processor=logits_processor,
            grammar=grammar,
            logit_bias=logit_bias,
        )

        if tool is not None:
            tool_name = tool["function"]["name"]
            return _convert_completion_to_chat_function(
                tool_name, completion_or_chunks, stream
            )
        return _convert_completion_to_chat(completion_or_chunks, stream=stream)


    @classmethod
    def _extract_image_bytes(
        cls, messages: List[llama_types.ChatCompletionRequestMessage], marker: str,
    ) -> tuple[List[llama_types.ChatCompletionRequestMessage], List[bytes]]:
        new_messages = []
        image_bytes = []
        num_markers = 0

        for msg in messages:
            content = msg.get("content")
            if not isinstance(content, list) or msg["role"] != "user":
                new_messages.append(msg)
                continue

            new_content = []
            for part in content:
                if not isinstance(part, dict):
                    new_content.append(part)
                    continue

                match part.get("type"):
                    case "image_bytes":
                        img_bytes = part.get("image_bytes")
                        assert img_bytes

                    case "image_url":
                        url = part.get("image_url")
                        if isinstance(url, dict):
                            img_bytes = cls._load_image(url["url"])
                        elif isinstance(url, str):
                            img_bytes = cls._load_image(url)
                        else:
                            raise ValueError("Missing image url")

                    case _:
                        new_content.append(part)
                        continue

                image_bytes.append(img_bytes)

                # Replace with a text block containing the marker. The Jinja template will output it verbatim.
                new_content.append({"type": "text", "text": marker})
                num_markers += 1

            new_messages.append({**msg, "content": new_content})

        if num_markers != len(image_bytes):
            raise ValueError("Number of markers in chat messages does not match image count")

        return new_messages, image_bytes


    @staticmethod
    def _load_image(image_url: str) -> bytes:
        # TODO: Add Pillow support for other image formats beyond (jpg, png)
        if image_url.startswith("data:"):
            import base64

            image_bytes = base64.b64decode(image_url.split(",")[1])
            return image_bytes
        else:
            import urllib.request

            with urllib.request.urlopen(image_url) as f:
                image_bytes = f.read()
                return image_bytes

    def _create_bitmap_from_bytes(self, image_bytes: bytes):
        """Create mtmd_bitmap from image bytes."""
        if self.mtmd_ctx is None:
            raise ValueError("mtmd context not initialized")

        with suppress_stdout_stderr(disable=self.verbose):
            # Create bitmap from buffer using helper function
            bitmap = self._mtmd_cpp.mtmd_helper_bitmap_init_from_buf(
                self.mtmd_ctx,
                (ctypes.c_uint8 * len(image_bytes)).from_buffer(bytearray(image_bytes)),
                len(image_bytes),
            )

            if bitmap is None:
                raise ValueError("Failed to create bitmap from image bytes")

            return bitmap
