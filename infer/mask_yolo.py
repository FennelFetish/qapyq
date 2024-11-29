# https://github.com/ultralytics/ultralytics/issues/1196  Doesn't seem to work...
import ultralytics.utils
ultralytics.utils.ONLINE = False

from ultralytics import YOLO
from PIL import Image


class YoloMask:
    def __init__(self, config: dict) -> None:
        self.model = YOLO(config.get("model_path"), task="detect", verbose=False)
        names = ", ".join(self.model.names.values())
        print(f"Yolo classes: {names}")

        self.inferenceArgs = {
            "verbose": False
        }


    def detectBoxes(self, imgPath: str):
        image = Image.open(imgPath)
        image = self.scaleImage(image)
        
        results = []

        detections = self.model(image, **self.inferenceArgs)
        for boxes in (det.boxes.cpu().numpy() for det in detections):
            for i, nameIndex in enumerate(boxes.cls):
                name = self.model.names[int(nameIndex)]
                p0x, p0y, p1x, p1y = boxes.xyxyn[i]
                results.append({
                    "name": name,
                    "confidence": float(boxes.conf[i]),
                    "p0": (float(p0x), float(p0y)),
                    "p1": (float(p1x), float(p1y))
                })

        return results

    # Pad instead? Complicates result calculation, but maybe better accuracy when AR is kept?
    def scaleImage(self, image: Image.Image):
        width, height = image.size

        # Quantize to 32
        newWidth  = round(width / 32) * 32
        newHeight = round(height / 32) * 32
        if newHeight == height and newWidth == width:
            return image
        
        return image.resize((newWidth, newHeight))
