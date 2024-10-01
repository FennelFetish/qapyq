import torch
import torchvision.transforms as T
from torchvision.transforms.functional import InterpolationMode
from transformers import AutoModel, AutoTokenizer, set_seed
#from decord import VideoReader, cpu
from PIL import Image
#from accelerate import infer_auto_device_map, init_empty_weights
from typing import List, Dict
from .backend import InferenceBackend



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

def load_image(image_file, input_size=448, max_num=12):
    image = Image.open(image_file).convert('RGB')
    transform = build_transform(input_size=input_size)
    images = dynamic_preprocess(image, image_size=input_size, use_thumbnail=True, max_num=max_num)
    pixel_values = [transform(image) for image in images]
    pixel_values = torch.stack(pixel_values)
    return pixel_values



class InternVL2Backend(InferenceBackend):
    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")

        self.model = AutoModel.from_pretrained(
            modelPath,
            torch_dtype=torch.bfloat16,
            #low_cpu_mem_usage=True,
            #use_flash_attn=True,
            attn_implementation='flash_attention_2',
            trust_remote_code=True,
            device_map="auto"
        ).eval()#.cuda()

        # deviceMap = {name: param.device for name, param in self.model.named_parameters()}
        # printErr(f"deviceMap: {deviceMap}")

        fast = True # False
        self.tokenizer = AutoTokenizer.from_pretrained(modelPath, trust_remote_code=True, use_fast=fast)


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
            "repetition_penalty": self.config.get("repeat_penalty")
        }


    def caption(self, imgPath: str, prompts: List[Dict[str, str]], systemPrompt: str = None) -> Dict[str, str]:
        pixel_values = load_image(imgPath, max_num=12).to(torch.bfloat16).cuda()
        answers = dict()

        self.model.system_message = systemPrompt.strip() if systemPrompt else ""
        set_seed(self.randomSeed())
        
        for conversation in prompts:
            history = None
            for name, prompt in conversation.items():
                answer, history = self.model.chat(self.tokenizer, pixel_values, prompt, generation_config=self.configDict, history=history, return_history=True)
                answers[name] = answer

        return answers



    def makeDeviceMap(numGpuLayers: int = 0):
        lastLayer = 59
        numGpuLayers = min(numGpuLayers, lastLayer)
        cpu = "cpu"

        device_map = {}
        device_map["vision_model"] = cpu # 0
        device_map["language_model.model.embed_tokens"] = 0
        # --- layers ---
        device_map["language_model.model.norm"] = 0 #cpu
        device_map["language_model.model.rotary_emb"] = 0 #cpu
        device_map["language_model.lm_head"] = 0 #cpu
        device_map["mlp1"] = cpu

        layer = 0
        for l in range(numGpuLayers):
            device_map[f"language_model.model.layers.{l}"] = 0

        if numGpuLayers < lastLayer:
            device_map[f"language_model.model.layers.{numGpuLayers}.self_attn"] = 0
            device_map[f"language_model.model.layers.{numGpuLayers}.input_layernorm"] = 0 #cpu
            device_map[f"language_model.model.layers.{numGpuLayers}.post_attention_layernorm"] = cpu
            device_map[f"language_model.model.layers.{numGpuLayers}.mlp"] = 0 #cpu
        else:
            device_map[f"language_model.model.layers.{lastLayer}"] = 0

        for l in range(numGpuLayers+1, lastLayer+1):
            device_map[f"language_model.model.layers.{l}"] = cpu

        print("Device map:")
        for k, v in device_map.items():
            print(f"{k} -> {v}")
        
        return device_map




import sys, os
def printErr(text):
    sys.stderr.write(text + os.linesep)
    sys.stderr.flush()