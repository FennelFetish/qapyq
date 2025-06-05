from transformers import AutoModelForCausalLM, AutoProcessor, set_seed
import torch, re
import numpy as np
import cv2 as cv
from host.imagecache import ImageFile
from .backend import CaptionBackend
from .devmap import DevMap
from .quant import Quantization


# https://www.assemblyai.com/blog/florence-2-how-it-works-how-to-use/
# https://blog.roboflow.com/florence-2-instance-segmentation/


class Florence2Backend(CaptionBackend):
    TASK_DEFAULT_CAPTION = "<DETAILED_CAPTION>"
    TASK_DETECT     = "<CAPTION_TO_PHRASE_GROUNDING>"
    TASK_DETECT_ALL = "<OD>"
    TASK_SEGMENT    = "<REFERRING_EXPRESSION_SEGMENTATION>"


    def __init__(self, config: dict):
        super().__init__(config)
        modelPath = config.get("model_path")
        self.tagPattern = re.compile(r'<[^>]*>')

        if torch.cuda.is_available():
            self.device = "cuda:0"
            self.dtype = torch.bfloat16
        else:
            self.device = "cpu"
            self.dtype = torch.float32

        devmap = self.makeDeviceMap(modelPath, config.get("gpu_layers", -1), config.get("vis_gpu_layers", -1))
        quant = Quantization.getQuantConfig(config.get("quantization"), devmap.hasCpuLayers)

        self.model = AutoModelForCausalLM.from_pretrained(
            modelPath,
            torch_dtype=self.dtype,
            device_map=devmap.deviceMap,
            attn_implementation=devmap.attention,
            quantization_config=quant,
            trust_remote_code=True
        )#.to(self.device)

        self.processor = AutoProcessor.from_pretrained(
            modelPath,
            trust_remote_code=True
        )


    def setConfig(self, config: dict):
        super().setConfig(config)

        # Config for detection/segmentation
        if "temperature" not in config:
            self.genArgs = {
                "max_new_tokens": 16384,
                "num_beams": 3,
                "early_stopping": True,

                # "do_sample": True,
                # "temperature": 1.0,
                # "top_k": 40,
                # "top_p": 0.95,
                # "min_p": 0.05
            }
            return

        self.genArgs = {
            "max_new_tokens": self.config.get("max_tokens"),
            "stop_strings": (self.stop if self.stop else None),
            "do_sample": self.config.get("temperature") > 0.01,

            "temperature": self.config.get("temperature"),
            "top_k": self.config.get("top_k"),
            "top_p": self.config.get("top_p"),
            "min_p": self.config.get("min_p"),
            "typical_p": self.config.get("typical_p"),
            "repetition_penalty": self.config.get("repeat_penalty"),

            "num_beams": 3,
        }


    def caption(self, imgFile: ImageFile, prompts: list[dict[str, str]], systemPrompt: str = None) -> dict[str, str]:
        image = imgFile.openPIL()
        answers = dict()

        set_seed(self.randomSeed())

        for conversation in prompts:
            for name, prompt in conversation.items():
                tags = self.tagPattern.findall(prompt)
                task = tags[0].upper() if tags else self.TASK_DEFAULT_CAPTION

                prompt = self.tagPattern.sub("", prompt)
                prompt = prompt.strip()

                result = self.runTask(image, task, prompt)
                answers[name] = str(result.get(task))

        return answers

    @torch.inference_mode()
    def runTask(self, image, task, prompt=None):
        if prompt:
            prompt = task + prompt
        else:
            prompt = task

        inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.device, self.dtype)
        generated_ids = self.model.generate(
            input_ids=inputs["input_ids"],
            pixel_values=inputs["pixel_values"],
            **self.genArgs
        )

        generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
        parsed_answer = self.processor.post_process_generation(generated_text, task=task, image_size=(image.width, image.height))
        return parsed_answer

    # @torch.inference_mode()
    # def runTaskWithScores(self, image, task, prompt=None):
    #     if prompt:
    #         prompt = task + prompt
    #     else:
    #         prompt = task

    #     inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.device, self.dtype)
    #     generated_ids = self.model.generate(
    #         input_ids=inputs["input_ids"],
    #         pixel_values=inputs["pixel_values"],
    #         return_dict_in_generate=True,
    #         output_scores=True,
    #         **self.genArgs
    #     )

    #     #print(f"scores: {generated_ids.scores}")

    #     #generated_text = self.processor.batch_decode(generated_ids.sequences, skip_special_tokens=False)[0]

    #     prediction, scores, beam_indices = generated_ids.sequences, generated_ids.scores, generated_ids.beam_indices
    #     transition_beam_scores = self.model.compute_transition_scores(
    #         sequences=prediction,
    #         scores=scores,
    #         beam_indices=beam_indices,
    #     )

    #     print(f"transition_beam_scores[0]: {transition_beam_scores[0]}")

    #     parsed_answer = self.processor.post_process_generation(
    #         sequence=generated_ids.sequences[0],
    #         transition_beam_score=transition_beam_scores[0],
    #         task=task, image_size=(image.width, image.height)
    #     )

    #     print(parsed_answer)
    #     return parsed_answer


    def detectBoxes(self, imgFile: ImageFile, classes: list[str]):
        image = imgFile.openPIL()
        if image.mode != "RGB":
            image = image.convert("RGB")

        results = []

        # When empty, do OD (all classes), TODO: use detailed caption as grounding?
        if not classes:
            results.extend( self._detectClass(image, self.TASK_DETECT_ALL) )

        for prompt in classes:
            results.extend( self._detectClass(image, self.TASK_DETECT, prompt) )
        return results

    def _detectClass(self, image, task: str, prompt: str = None):
        w, h = image.size

        answer: dict = self.runTask(image, task, prompt).get(task)
        bboxes = answer["bboxes"]
        labels = answer["labels"]
        #scores = answer["scores"]

        #for box, label, score in zip(bboxes, labels, scores):
        for box, label in zip(bboxes, labels):
            p0x, p0y, p1x, p1y = box
            p0x /= w
            p0y /= h
            p1x /= w
            p1y /= h

            yield {
                "name": label,
                "confidence": 1.0,
                "p0": (float(p0x), float(p0y)),
                "p1": (float(p1x), float(p1y))
            }


    def mask(self, imgFile: ImageFile, classes: list[str]):
        image = imgFile.openPIL()
        if image.mode != "RGB":
            image = image.convert("RGB")
        w, h = image.size

        mask = np.zeros((h, w), dtype=np.uint8)
        for prompt in classes:
            self._maskClass(image, mask, prompt)

        return mask.tobytes()


    def _maskClass(self, image, mask: np.ndarray, prompt: str):
        answer: dict = self.runTask(image, self.TASK_SEGMENT, prompt).get(self.TASK_SEGMENT)
        polygons = answer["polygons"]

        for polys in polygons:
            for poly in polys:
                numPoints = len(poly)

                polyInt = np.zeros((numPoints), dtype=np.int32)
                for i, p in enumerate(poly):
                    polyInt[i] = round(p)

                polyInt.shape = (numPoints // 2, 2)
                cv.fillPoly(mask, [polyInt], color=(255,), lineType=cv.LINE_AA)


    def getClassNames(self) -> list[str]:
        return []


    @staticmethod
    def makeDeviceMap(modelPath, llmGpuLayers: int, visGpuLayers: int) -> DevMap:
        devmap = DevMap.fromConfig(
            modelPath,
            "text_config.num_hidden_layers"
        )
        devmap.maxLayerVis = 3

        devmap.setCudaLayer("language_model")
        devmap.setCudaLayer("language_model.lm_head")
        devmap.setCudaLayer("language_model.model.shared")

        devmap.setCudaLayer("language_model.model.encoder.embed_positions")
        devmap.setCudaLayer("language_model.model.encoder.layernorm_embedding")
        devmap.setLLMLayers("language_model.model.encoder.layers", llmGpuLayers)

        devmap.setCudaLayer("language_model.model.decoder.embed_positions")
        devmap.setCudaLayer("language_model.model.decoder.layernorm_embedding")
        devmap.setLLMLayers("language_model.model.decoder.layers", llmGpuLayers)

        if visGpuLayers == 0:
            devmap.setCpuLayer("image_projection")
            devmap.setCpuLayer("image_proj_norm")
            devmap.setCpuLayer("image_pos_embed")
            devmap.setCpuLayer("visual_temporal_embed") # Not printed with DevMap.printDeviceMap()

            devmap.setCpuLayer("vision_tower")
            devmap.setCpuLayer("vision_tower.convs")
            devmap.setCpuLayer("vision_tower.blocks")
        else:
            devmap.setCudaLayer("image_projection")
            devmap.setCudaLayer("image_proj_norm")
            devmap.setCudaLayer("image_pos_embed")
            devmap.setCudaLayer("visual_temporal_embed") # Not printed with DevMap.printDeviceMap()

            devmap.setCudaLayer("vision_tower")
            devmap.setCudaLayer("vision_tower.convs")
            devmap.setVisLayers("vision_tower.blocks", visGpuLayers)

        return devmap
