import base64, io, os
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Llava15ChatHandler
from PySide6.QtGui import QImage
from PySide6.QtCore import QBuffer


class MiniCPM:
    def __init__(self, modelPath, clipPath):
        chat_handler = Llava15ChatHandler(clip_model_path=clipPath, verbose=False)

        self.llm = Llama(
            model_path=modelPath,
            n_gpu_layers=-1,
            n_ctx=32768, # n_ctx should be increased to accommodate the image embedding
            n_batch=512,
            n_threads=12,
            flash_attn=True,
            chat_handler=chat_handler,
            #logits_all=True,# needed to make llava work
            #verbose=False
        )

    def imageToBase64(self, imgPath):
        if imgPath.lower().endswith(".png"):
            with open(imgPath, "rb") as img:
                imgData = img.read()
        else:
            buffer = QBuffer()
            buffer.open(QBuffer.ReadWrite)
            img = QImage(imgPath)
            img.save(buffer, "PNG", 100) # Preserve transparency with PNG. quality 100 actually fastest?
            imgData = buffer.data()

        base64_data = base64.b64encode(imgData).decode('utf-8')
        return f"data:image/png;base64,{base64_data}"

    def caption(self, imgPath, prompt, systemPrompt=None):
        imgURI = self.imageToBase64(imgPath)
        
        messages = []
        if systemPrompt:
            systemPrompt = systemPrompt.strip() + "\n"
            messages.append({"role": "system", "content": systemPrompt})

        prompt = prompt.strip() + "\n"
        messages.append({
            "role": "user",
            "content": [
                {"type" : "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": imgURI } }
            ]
        })

        completion = self.llm.create_chat_completion(
            messages = messages,
            #temperature=0.15, top_k=40, min_p=0.15,
            temperature=0.15, top_k=60, min_p=0.1,
            max_tokens=1024,
        )

        return [choice["message"]["content"] for choice in completion["choices"]]
