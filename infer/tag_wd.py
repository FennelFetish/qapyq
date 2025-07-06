import numpy as np
import onnxruntime
import pandas as pd
import torch # Not used directly, but required for GPU inference
from .tag import TagBackend, ThresholdMode
from .devmap import DevMap
from config import Config


class WDTag(TagBackend):
    DEFAULT_GENERAL_THRESH = 0.35
    DEFAULT_CHAR_THRESH = 0.85

    MIN_CHAR_THRESH = 0.15

    def __init__(self, config: dict):
        super().__init__()

        self.includeRatings = False

        self.includeGeneral = True
        self.generalThresholdMode: ThresholdMode = ThresholdMode(self.DEFAULT_GENERAL_THRESH, False)

        self.includeCharacters = True
        self.characterOnlyMax = True
        self.characterThresholdMode: ThresholdMode = ThresholdMode(self.DEFAULT_CHAR_THRESH, True, True)

        self.setConfig(config)

        sep_tags = self._loadLabels(config.get("csv_path"))
        self.tag_names         = sep_tags[0]
        self.rating_indexes    = sep_tags[1]
        self.general_indexes   = sep_tags[2]
        self.character_indexes = sep_tags[3]

        # https://onnxruntime.ai/docs/api/python/api_summary.html
        # https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#configuration-options
        # CUDAExecutionProvider needs 'import torch'
        providers = [
            ('CUDAExecutionProvider', {"device_id": DevMap.getDeviceId()}),
            'CPUExecutionProvider'
        ]

        self.model = onnxruntime.InferenceSession(config.get("model_path"), providers=providers)
        _, height, width, _ = self.model.get_inputs()[0].shape
        self.modelTargetSize = height


    def __del__(self):
        if hasattr(self, "model"):
            del self.model


    def setConfig(self, config: dict):
        config = config.get(Config.INFER_PRESET_SAMPLECFG_KEY, {})

        self.includeRatings = bool(config.get("include_ratings", False))

        self.includeGeneral = bool(config.get("include_general", True))
        self.generalThresholdMode = ThresholdMode.fromConfig(config, "threshold", "threshold_mode", self.DEFAULT_GENERAL_THRESH)

        self.includeCharacters = bool(config.get("include_characters", True))
        self.characterOnlyMax = bool(config.get("character_only_max", True))
        self.characterThresholdMode = ThresholdMode.fromConfig(config, "character_threshold", "character_threshold_mode", self.DEFAULT_CHAR_THRESH)


    def tag(self, imgFile) -> str:
        img = self.loadImageSquare(imgFile, self.modelTargetSize)
        img = np.expand_dims(img, axis=0)

        results = self.predict(img)
        tags = ", ".join(res for res in results if res)
        return tags


    def predict(self, image) -> tuple[str, ...]:
        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        preds = self.model.run([label_name], {input_name: image})[0]

        labels: list[tuple[str, float]] = list(zip(self.tag_names, preds[0].astype(float)))

        # First 4 labels are actually ratings: pick one with argmax
        if self.includeRatings:
            maxRating = max(self.nameScores(labels, self.rating_indexes), key=self.scoreKey)
            rating = "rating " + maxRating[0]
        else:
            rating = ""

        # Then we have general tags: pick any where prediction confidence > threshold
        if self.includeGeneral:
            generalTags = self.processPreds(labels, self.general_indexes, self.generalThresholdMode)
        else:
            generalTags = ""

        # Everything else is characters: pick any where prediction confidence > threshold
        if self.includeCharacters:
            if self.characterOnlyMax:
                maxCharacter = max(self.nameScores(labels, self.character_indexes), key=self.scoreKey)
                characterTags = maxCharacter[0] if maxCharacter[1] > self.characterThresholdMode.threshold else ""
            else:
                characterTags = self.processPreds(labels, self.character_indexes, self.characterThresholdMode, self.MIN_CHAR_THRESH)
        else:
            characterTags = ""

        return rating, characterTags, generalTags


    @classmethod
    def processPreds(cls, labels: list[tuple[str, float]], indexes: list[int], thresholdMode: ThresholdMode, minThreshold=TagBackend.MIN_THRESH) -> str:
        threshold = thresholdMode.threshold
        if thresholdMode.adaptive:
            probs = np.fromiter((x[1] for x in cls.nameScores(labels, indexes)), dtype=float, count=len(indexes))
            threshold = cls.calcAdaptiveThreshold(probs, threshold, thresholdMode.strict)
            threshold = max(threshold, minThreshold)

        sortedNames = sorted(
            (x for x in cls.nameScores(labels, indexes) if x[1] > threshold),
            key=cls.scoreKey,
            reverse=True,
        )
        return ", ".join(x[0] for x in sortedNames)


    @staticmethod
    def nameScores(labels: list[tuple[str, float]], indexes: list[int]):
        return (labels[i] for i in indexes)

    @staticmethod
    def scoreKey(x: tuple):
        return x[1]


    @staticmethod
    def _loadLabels(csvPath: str) -> tuple[list[str], list[int], list[int], list[int]]:
        dataframe = pd.read_csv(csvPath)

        name_series = dataframe["name"]
        name_series = name_series.map(TagBackend.removeUnderscore)
        tag_names = name_series.tolist()

        rating_indexes = list(np.where(dataframe["category"] == 9)[0])
        general_indexes = list(np.where(dataframe["category"] == 0)[0])
        character_indexes = list(np.where(dataframe["category"] == 4)[0])
        return tag_names, rating_indexes, general_indexes, character_indexes
