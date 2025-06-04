import numpy as np
import onnxruntime
import pandas as pd
import torch # Not used directly, but required for GPU inference
from .tag import TagBackend
from config import Config


class WDTag(TagBackend):
    def __init__(self, config: dict):
        self.general_thresh = 0.35
        self.general_mcut = False
        self.character_thresh = 0.85
        self.character_mcut = False
        self.setConfig(config)

        sep_tags = self.loadLabels(config.get("csv_path"))

        self.tag_names = sep_tags[0]
        self.rating_indexes = sep_tags[1]
        self.general_indexes = sep_tags[2]
        self.character_indexes = sep_tags[3]

        #https://onnxruntime.ai/docs/api/python/api_summary.html
        # CUDAExecutionProvider needs 'import torch'
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        self.model = onnxruntime.InferenceSession(config.get("model_path"), providers=providers)
        _, height, width, _ = self.model.get_inputs()[0].shape
        self.modelTargetSize = height


    def __del__(self):
        if hasattr(self, "model"):
            del self.model


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})

        self.general_thresh = float(config.get("threshold", 0.35))
        self.general_mcut   = bool(config.get("general_mcut_enabled", False))

        self.character_thresh = float(config.get("character_thresh", 0.85))
        self.character_mcut   = bool(config.get("character_mcut_enabled", False))


    def tag(self, imgFile) -> str:
        img = self.loadImageSquare(imgFile, self.modelTargetSize)
        img = np.expand_dims(img, axis=0)

        tags, characterResults = self.predict(img)

        # Prepend character
        if characterResults and (char := max(characterResults, key=lambda k: characterResults[k])):
            tags = ", ".join([char, tags])

        return tags


    def predict(self, image):
        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        preds = self.model.run([label_name], {input_name: image})[0]

        labels = list(zip(self.tag_names, preds[0].astype(float)))

        # First 4 labels are actually ratings: pick one with argmax
        # ratings_names = (labels[i] for i in self.rating_indexes)
        # rating = dict(ratings_names)

        # Then we have general tags: pick any where prediction confidence > threshold
        general_names = (labels[i] for i in self.general_indexes)

        general_thresh = self.general_thresh
        if self.general_mcut:
            general_probs = np.array([x[1] for x in general_names])
            general_thresh = self.mcutThreshold(general_probs)

        general_res = (x for x in general_names if x[1] > general_thresh)
        general_res = dict(general_res)

        # Everything else is characters: pick any where prediction confidence > threshold
        character_names = (labels[i] for i in self.character_indexes)

        character_thresh = self.character_thresh
        if self.character_mcut:
            character_probs = np.array([x[1] for x in character_names])
            character_thresh = self.mcutThreshold(character_probs)
            character_thresh = max(0.15, character_thresh)

        character_res = (x for x in character_names if x[1] > character_thresh)
        character_res = dict(character_res)

        sorted_general_strings = sorted(
            general_res.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        sorted_general_strings = ", ".join(x[0] for x in sorted_general_strings)

        #return sorted_general_strings, rating, character_res, general_res
        return sorted_general_strings, character_res


    @staticmethod
    def loadLabels(csvPath: str) -> list[str]:
        dataframe = pd.read_csv(csvPath)

        name_series = dataframe["name"]
        name_series = name_series.map(TagBackend.removeUnderscore)
        tag_names = name_series.tolist()

        rating_indexes = list(np.where(dataframe["category"] == 9)[0])
        general_indexes = list(np.where(dataframe["category"] == 0)[0])
        character_indexes = list(np.where(dataframe["category"] == 4)[0])
        return tag_names, rating_indexes, general_indexes, character_indexes


    @staticmethod
    def mcutThreshold(probs: np.ndarray):
        """
        Maximum Cut Thresholding (MCut)
        Largeron, C., Moulin, C., & Gery, M. (2012). MCut: A Thresholding Strategy
        for Multi-label Classification. In 11th International Symposium, IDA 2012
        (pp. 172-183).
        """
        sorted_probs = probs[probs.argsort()[::-1]]
        difs = sorted_probs[:-1] - sorted_probs[1:]
        t = difs.argmax()
        thresh = (sorted_probs[t] + sorted_probs[t + 1]) / 2
        return thresh
