from typing import Any
import base64, random
from io import BytesIO
from PIL import Image
from config import Config


class InferenceBackend:
    def __init__(self, config: dict[str, Any]):
        self.stop: list[str] = []

        self.config: dict[str, Any]= {
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
        self.setConfig(config)


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.config.update(config)


    @staticmethod
    def randomSeed():
        return random.randint(0, 2147483647)


    @staticmethod
    def imageToBase64(imgPath: str):
        if imgPath.lower().endswith(".png"):
            with open(imgPath, "rb") as img:
                imgData = img.read()
        else:
            buffer = BytesIO()
            img = Image.open(imgPath)
            img.save(buffer, format='PNG')
            imgData = buffer.getvalue()
            del img, buffer

        base64Data = base64.b64encode(imgData).decode('utf-8')
        return f"data:image/png;base64,{base64Data}"


    @staticmethod
    def mergeSystemPrompt(prompts: list[dict[str, str]], systemPrompt: str) -> list[dict[str, str]]:
        for conv in prompts:
            name, prompt  = next(iter(conv.items())) # First entry
            text = Config.sysPromptFallbackTemplate.replace("{{systemPrompt}}", systemPrompt)
            text = text.replace("{{prompt}}", prompt)
            conv[name] = text
        return prompts


    def caption(self, imgPath: str, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()

    def answer(self, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        raise NotImplementedError()
