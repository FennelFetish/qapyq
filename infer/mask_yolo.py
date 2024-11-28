# https://github.com/ultralytics/ultralytics/issues/1196  Doesn't seem to work...
import ultralytics.utils
ultralytics.utils.ONLINE = False

from ultralytics import YOLO
from PIL import Image

# import onnxruntime
#import torch
# import cv2 as cv
# import numpy as np


class YoloMask:
    def __init__(self, config: dict) -> None:
        self.model = YOLO(config.get("model_path"), task="detect", verbose=False)
        names = ", ".join(self.model.names.values())
        print(f"Yolo classes: {names}")

        self.inferenceArgs = {
            "verbose": False
        }

        #providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] # TensorrtExecutionProvider
        # self.model = onnxruntime.InferenceSession(modelPath, providers=providers)

        # self.inputName = self.model.get_inputs()[0].name    # images
        # input_shape = self.model.get_inputs()[0].shape  # ['batch', 3, 'height', 'width']
        # printErr(f"input_name: {self.inputName}, input_shape: {input_shape}")
        # printErr(f"{self.model.get_inputs()}")


    #@torch.inference_mode()
    def detectBoxes(self, imgPath: str):
        image = Image.open(imgPath)
        image = self.scaleImage(image)
        
        results = []

        detections = self.model(image, **self.inferenceArgs)
        for det in detections:
            boxes = det.boxes.cpu().numpy()

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


    # def detectBoxes(self, imgPath: str):
    #     # https://medium.com/@zain.18j2000/how-to-use-custom-or-official-yolov8-object-detection-model-in-onnx-format-ca8f055643df
    #     image = cv.imread(imgPath, cv.IMREAD_UNCHANGED)
    #     image = cv.cvtColor(image, cv.COLOR_BGR2RGB) # ???
    #     image = self.scaleImage(image)

    #     image = image.transpose(2, 0, 1)
    #     image = np.expand_dims(image, axis=0)
    #     image = image.astype(np.float32) / 255.0
    #     image = np.ascontiguousarray(image)
    #     printErr(f"image shape={image.shape} dtype={image.dtype}")

    #     results = self.model.run(None, {self.inputName: image})
    #     for res in results:
    #         printErr(f"Res: {res.shape}")

    # def scaleImage(self, image):
    #     height, width, channels = image.shape

    #     newHeight = round(height / 32) * 32
    #     newWidth = round(width / 32) * 32
    #     if newHeight == height and newWidth == width:
    #         return image

    #     return cv.resize(image, (newWidth, newHeight), interpolation=cv.INTER_LANCZOS4)


# https://github.com/ultralytics/ultralytics/issues/5147
# def _open_onnx_model(ckpt: str, provider: str) -> InferenceSession:
#     options = SessionOptions() # (from onnxruntime)
#     options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
#     if provider == "CPUExecutionProvider":
#         options.intra_op_num_threads = os.cpu_count()

#     logging.info(f'Model {ckpt!r} loaded with provider {provider!r}')
#     return InferenceSession(ckpt, options, [provider])


# Preferring ONNX Runtime TensorrtExecutionProvider
# 2024-11-24 18:36:23.670579960 [E:onnxruntime:Default, provider_bridge_ort.cc:1731 TryGetProviderInfo_TensorRT] /onnxruntime_src/onnxruntime/core/session/provider_bridge_ort.cc:1426 onnxruntime::Provider& onnxruntime::ProviderLibrary::Get() [ONNXRuntimeError] : 1 : FAIL : Failed to load library libonnxruntime_providers_tensorrt.so with error: libnvinfer.so.10: cannot open shared object file: No such file or directory
