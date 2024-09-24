import base64, random
from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer
from config import Config


class InferenceBackend:
    def __init__(self, config: dict):
        self.stop: list[str] = []

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
        self.setConfig(config)


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})
        self.config.update(config)


    def randomSeed(self):
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


    def caption(self, imgPath: str, prompts: dict, systemPrompt=None, rounds=1) -> dict:
        return {}

    def answer(self, prompts: dict, systemPrompt=None, rounds=1) -> dict:
        return {}