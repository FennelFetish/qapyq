# https://github.com/ultralytics/ultralytics/issues/1196  Doesn't seem to work...
# Online mode is disabled by setting environment var "YOLO_OFFLINE" to "True" before starting inference process.
import ultralytics.utils
#ultralytics.utils.ONLINE = False
if ultralytics.utils.ONLINE:
    print("WARNING: YOLO has its online features enabled")


from ultralytics import YOLO
from PIL import Image
from host.imagecache import ImageFile
from .devmap import DevMap


class YoloMask:
    def __init__(self, config: dict) -> None:
        self.model = YOLO(config.get("model_path"), task="detect", verbose=False)

        names = ", ".join(self.model.names.values())
        print(f"Yolo classes: {names}")

        self.inferenceArgs = {
            "verbose": False,
            "device": DevMap.getDeviceId()
        }


    def setConfig(self, config: dict):
        pass


    def getClassNames(self) -> list[str]:
        return list(self.model.names.values())


    def detectBoxes(self, imgFile: ImageFile, classes: list[str]):
        image = imgFile.openPIL()
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
    # TODO: Use size buckets to prevent changing input size
    def scaleImage(self, image: Image.Image):
        width, height = image.size

        # Quantize to 32
        newWidth  = round(width / 32) * 32
        newHeight = round(height / 32) * 32
        if newHeight == height and newWidth == width:
            return image

        return image.resize((newWidth, newHeight))
