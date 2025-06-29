import torch
from torchvision import transforms
from transformers import AutoModelForImageSegmentation
import numpy as np
import cv2 as cv
from PIL import Image
from host.imagecache import ImageFile
from .devmap import DevMap


class BriaRmbgMask:
    def __init__(self, config: dict):
        self.device, _ = DevMap.getTorchDeviceDtype()

        self.model = AutoModelForImageSegmentation.from_pretrained(
            config.get("model_path"),
            trust_remote_code=True
        )

        #print(torch.get_float32_matmul_precision()) # highest
        #torch.set_float32_matmul_precision(['high', 'highest'][0])
        self.model.to(self.device).eval()

        self.maxSize = 1536 # longer side
        self.transform = transforms.Compose([
            #transforms.Resize((1024, 1024)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])


    def setConfig(self, config: dict):
        pass


    @torch.inference_mode()
    def mask(self, imgFile: ImageFile, classes: list[str]) -> bytes:
        image = imgFile.openPIL(forceRGB=True)
        wOrig, hOrig = image.size
        image = self.scaleImage(image)

        # shape = B C H W
        inputImages = self.transform(image).unsqueeze(0).to(self.device)

        preds: list[torch.Tensor] = self.model(inputImages)[-1].sigmoid().cpu()
        mask = preds[0].squeeze().numpy()
        mask *= 255
        mask = mask.astype(np.uint8) # Convert before resize to prevent artifacts

        hMask, wMask = mask.shape
        interp = cv.INTER_CUBIC if (wOrig>wMask or hOrig>hMask) else cv.INTER_AREA
        mask = cv.resize(mask, (wOrig, hOrig), interpolation=interp)
        return mask.tobytes()


    def scaleImage(self, image: Image.Image):
        width, height = image.size

        # Scale, so longer side matches 'maxSize'
        scale = self.maxSize / max(width, height)
        newWidth  = width * scale
        newHeight = height * scale

        # Quantize to 32
        newWidth  = round(newWidth / 32) * 32
        newHeight = round(newHeight / 32) * 32
        if newHeight == height and newWidth == width:
            return image

        interp = Image.Resampling.LANCZOS if (newWidth>width or newHeight>height) else Image.Resampling.BOX
        return image.resize((newWidth, newHeight), resample=interp)



if __name__ == "__main__":
    config = {
        "model_path": "/mnt/ai/Models/rembg/BriaAI-RMBG-2.0/"
    }
    backend = BriaRmbgMask(config)
    maskBytes = backend.mask("/home/rem/Pictures/red-tree-with-eyes_SD35.png")
    print(f"Result len: {len(maskBytes)}")
