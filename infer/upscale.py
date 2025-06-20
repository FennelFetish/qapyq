from spandrel import ImageModelDescriptor, ModelLoader
import spandrel_extra_arches
import torch
import torchvision.transforms as transforms
import numpy as np
from host.imagecache import ImageFile

# add extra architectures before `ModelLoader` is used
spandrel_extra_arches.install()


# TODO: Use tiling for large images?

CONVERSIONS = {"1": "RGB", "L": "RGB", "LA": "RGBA", "P": "RGB", "PA": "RGBA"}


class UpscaleBackend:
    def __init__(self, config: dict):
        self.model = ModelLoader().load_from_file(config.get("model_path"))
        assert isinstance(self.model, ImageModelDescriptor)
        self.model.cuda().eval()

        self.toTensor = transforms.ToTensor()


    def setConfig(self, config: dict):
        pass


    @torch.inference_mode()
    def _upscaleImage(self, tensor: torch.Tensor) -> np.ndarray:
        tensor = tensor[:3, ...] # Remove alpha channel # TODO: Do proper alpha composition
        tensor = tensor.unsqueeze(0)
        tensor = tensor.to(self.model.device)
        # tensor shape = [batch, channels, height, width]

        result = self.model(tensor)
        result = result.cpu().squeeze(0).numpy()
        result *= 255
        result = result.astype(np.uint8).transpose(1, 2, 0)
        return result

    def upscaleImage(self, imgFile: ImageFile) -> tuple[int, int, bytes]:
        image = imgFile.openPIL()
        if convertMode := CONVERSIONS.get(image.mode):
            print(f"Converting color mode from {image.mode} to {convertMode} ({imgFile.file})")
            image = image.convert(convertMode)

        tensor = self.toTensor(image)
        result = self._upscaleImage(tensor)
        h, w = result.shape[:2]
        return w, h, result.tobytes()

    def upscaleImageData(self, imgData: bytes, w: int, h: int) -> tuple[int, int, bytes]:
        channels = len(imgData) // (w*h)
        mat = np.frombuffer(imgData, dtype=np.uint8).copy()
        mat.shape = (h, w, channels)
        tensor = self.toTensor(mat)
        result = self._upscaleImage(tensor)
        h, w = result.shape[:2]
        return w, h, result.tobytes()
