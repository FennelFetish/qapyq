import base64, io, os, random
from llama_cpp import Llama
from llama_cpp.llama_chat_format import MiniCPMv26ChatHandler
from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer
from config import Config


class MiniCPM:
    def __init__(self, config: dict = {}):
        self.config = {
            "max_tokens": 1000,
            "temperature": 0.15,
            "top_p": 0.95,
            "top_k": 40,
            "min_p": 0.05,
            "typical_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "repeat_penalty": 1.05,
            "mirostat_mode": 0,
            "mirostat_tau": 5.0,
            "mirostat_eta": 0.1,
            "tfs_z": 1.0
        }

        self.chat_handler = MiniCPMv26ChatHandler(
            clip_model_path=config.get("proj_path"),
            verbose=False
        )

        self.llm = Llama(
            model_path=config.get("model_path"),
            n_gpu_layers=config.get("gpu_layers", -1),
            n_ctx=config.get("ctx_length", 32768), # n_ctx should be increased to accommodate the image embedding
            n_batch=config.get("batch_size", 512),
            n_threads=config.get("num_threads", 15),
            flash_attn=True,
            seed=self.getSeed(),
            chat_handler=self.chat_handler,
            #logits_all=True,# needed to make llava work (DEPRECATED - set llama_batch.logits instead)
            verbose=False
        )

        self.setConfig(config)
        self.stop = ["USER:", "ASSISTANT:"]


    def __del__(self):
        self.llm.close()


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.config.update(config)


    def getSeed(self):
        return random.randint(0, 2147483647)


    def imageToBase64(self, imgPath):
        if imgPath.lower().endswith(".png"):
            with open(imgPath, "rb") as img:
                imgData = img.read()
        else:
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            img = QImage(imgPath)
            img.save(buffer, "PNG", 100)
            imgData = buffer.data()
            del img

        base64Data = base64.b64encode(imgData).decode('utf-8')
        return f"data:image/png;base64,{base64Data}"


    def caption(self, imgPath, prompts: dict, systemPrompt=None, rounds=1) -> dict:
        imgURI = self.imageToBase64(imgPath)
        answers = {}

        for r in range(rounds):
            messages = []
            if systemPrompt:
                messages.append( {"role": "system", "content": systemPrompt.strip()} )

            firstPrompt = True
            for name, prompt in prompts.items():
                prompt = prompt.strip()

                content = [ {"type" : "text", "text": prompt} ]
                if firstPrompt:
                    content.append( {"type": "image_url", "image_url": {"url": imgURI}} )
                    firstPrompt = False

                messages.append( {"role": "user", "content": content} )

                completion = self.llm.create_chat_completion(
                    messages = messages,
                    stop=self.stop,
                    seed=self.getSeed(),
                    **self.config
                )

                msg = completion["choices"][0]["message"]
                answer = msg["content"].strip()
                messages.append( { "role": msg["role"], "content": f"{answer}\n"} )

                if r > 0:
                    name = f"{name}_round{r}"
                answers[name] = answer
        
        return answers
