import torch
import torchvision.transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer, set_seed
#from decord import VideoReader, cpu
#from accelerate import infer_auto_device_map, init_empty_weights
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

def build_transform(input_size):
    MEAN, STD = IMAGENET_MEAN, IMAGENET_STD
    transform = T.Compose([
        T.Lambda(lambda img: img.convert('RGB') if img.mode != 'RGB' else img),
        T.Resize((input_size, input_size), interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=MEAN, std=STD)
    ])
    return transform

def find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float('inf')
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio

def dynamic_preprocess(image, min_num=1, max_num=12, image_size=448, use_thumbnail=False):
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / orig_height

    # calculate the existing image aspect ratio
    target_ratios = set(
        (i, j) for n in range(min_num, max_num + 1) for i in range(1, n + 1) for j in range(1, n + 1) if
        i * j <= max_num and i * j >= min_num)
    target_ratios = sorted(target_ratios, key=lambda x: x[0] * x[1])

    # find the closest aspect ratio to the target
    target_aspect_ratio = find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size)

    # calculate the target width and height
    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    # resize the image
    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size
        )
        # split the image
        split_img = resized_img.crop(box)
        processed_images.append(split_img)
    assert len(processed_images) == blocks
    if use_thumbnail and len(processed_images) != 1:
        thumbnail_img = image.resize((image_size, image_size))
        processed_images.append(thumbnail_img)
    return processed_images

def load_image(imgFile: ImageFile, input_size=448, max_num=12):
    image = imgFile.openPIL(forceRGB=True)
    transform = build_transform(input_size=input_size)
    images = dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    pixel_values = [transform(image) for image in images]
    pixel_values = torch.stack(pixel_values)
    return pixel_values



# V2.5 with quantization fails with:
#   File "/mnt/firlefanz/dev-Tools/qapyq/.venv/lib/python3.10/site-packages/accelerate/utils/operations.py", line 155, in send_to_device
#     return tensor.to(device, non_blocking=non_blocking)
# NotImplementedError: Cannot copy out of meta tensor; no data!

class InternVL2Backend(CaptionBackend):
    def __init__(self, config: dict):
        modelPath: str = config["model_path"]
        self.tokenizer = AutoTokenizer.from_pretrained(modelPath, trust_remote_code=True, use_fast=True)

        super().__init__(config)

        self.device, self.dtype = DevMap.getTorchDeviceDtype()
        devmap = self.makeDeviceMap(modelPath, self.device, config.get("gpu_layers", 100), config.get("vis_gpu_layers", 100))
        quant = Quantization.getQuantConfig(config.get("quantization", "none"), devmap.hasCpuLayers)#, ["vision_model"])

        self.model = AutoModel.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            #low_cpu_mem_usage=True,
            #use_flash_attn=True,
            attn_implementation=devmap.attention,
            device_map=devmap.deviceMap,
            quantization_config=quant,
            trust_remote_code=True,
        ).eval()

        # https://huggingface.co/docs/transformers/main/perf_torch_compile
        # https://pytorch.org/get-started/pytorch-2.0/#user-experience
        #self.model = torch.compile(self.model, mode="max-autotune") # modes: max-autotune, reduce-overhead


    def setConfig(self, config: dict):
        super().setConfig(config)

        self.configDict = {
            "max_new_tokens": self.config.get("max_tokens"),
            "stop_strings": (self.stop if self.stop else None),
            "do_sample": True,

            "temperature": self.config.get("temperature"),
            "top_k": self.config.get("top_k"),
            "top_p": self.config.get("top_p"),
            "min_p": self.config.get("min_p"),
            "typical_p": self.config.get("typical_p"),
            "repetition_penalty": self.config.get("repeat_penalty"),

            "pad_token_id": self.tokenizer.pad_token_id
        }


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        pixel_values = load_image(imgFile, max_num=12).to(self.device, dtype=self.dtype)
        answers = dict()

        self.model.system_message = systemPrompt.strip() if systemPrompt else ""
        set_seed(self.randomSeed())

        with torch.inference_mode():
            for conversation in prompts:
                history = None
                for name, prompt in conversation.items():
                    answer, history = self.model.chat(self.tokenizer, pixel_values, prompt, generation_config=self.configDict, history=history, return_history=True)
                    answers[name] = answer

        return answers


    @staticmethod
    def makeDeviceMap(modelPath: str, device, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "llm_config.num_hidden_layers",
            "vision_config.num_hidden_layers"
        )

        devmap.setDevice(device)

        # v2.0: 1b, 4b, 40b, 76b
        # v2.5: 38b
        devmap.setCudaLayer("language_model.model.embed_tokens")
        devmap.setCudaLayer("language_model.lm_head")

        # 2b, 8b, 26b
        devmap.setCudaLayer("language_model.model.tok_embeddings")
        devmap.setCudaLayer("language_model.output")

        match devmap.maxLayerLLM:
            case 23: # 1b, 2b
                if visGpuLayers == 0:
                    visGpuLayers = 1
            case 31: # 4b, 8b
                # TODO: This should only apply to 4b model
                if visGpuLayers == 0:
                    visGpuLayers = 1
            case 47: # 26b
                pass
            case 59: # 40b
                pass
            case 63: # v2.5 38b
                if visGpuLayers == 0:
                    visGpuLayers = 1
            case 79: # 76b
                pass

        devmap.setCudaLayer("language_model")
        devmap.setCudaLayer("language_model.model.norm")
        devmap.setLLMLayers("language_model.model.layers", llmGpuLayers)

        if visGpuLayers == 0:
            devmap.setCpuLayer("vision_model")
        else:
            devmap.setCudaLayer("vision_model")
            devmap.setCudaLayer("vision_model.embeddings")
            devmap.setVisLayers("vision_model.encoder.layers", visGpuLayers)

        devmap.setCudaLayer("mlp1")
        return devmap
