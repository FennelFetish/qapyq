import csv
import numpy as np
import onnxruntime
import torch # Not used directly, but required for GPU inference
from .tag import TagBackend, ThresholdMode
from .devmap import DevMap
from config import Config


class CategoryIndexes:
    def __init__(self):
        self.general: list[int]   = list()
        self.character: list[int] = list()
        self.rating: list[int]    = list()


class WDTag(TagBackend):
    SEP = ", "

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
        self.tagNames, self.indexes = self._loadLabels(config.get("csv_path"))

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

        self.inputName = self.model.get_inputs()[0].name
        self.outputNames = [self.model.get_outputs()[0].name]


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
        tags = self.SEP.join(filter(None, results))
        return tags


    def predict(self, image: np.ndarray) -> tuple[str, ...]:
        preds = self.model.run(self.outputNames, {self.inputName: image})[0]
        labels: list[tuple[str, float]] = list(zip(self.tagNames, preds[0].tolist()))

        # First 4 labels are actually ratings: pick one with argmax
        if self.includeRatings:
            maxRating = max(self.nameScores(labels, self.indexes.rating), key=self.scoreKey)
            rating = "rating " + maxRating[0]
        else:
            rating = ""

        # Then we have general tags: pick any where prediction confidence > threshold
        if self.includeGeneral:
            generalTags = self.processPreds(labels, self.indexes.general, self.generalThresholdMode)
        else:
            generalTags = ""

        # Everything else is characters: pick any where prediction confidence > threshold
        if self.includeCharacters:
            if self.characterOnlyMax:
                maxCharacter = max(self.nameScores(labels, self.indexes.character), key=self.scoreKey)
                characterTags = maxCharacter[0] if maxCharacter[1] > self.characterThresholdMode.threshold else ""
            else:
                characterTags = self.processPreds(labels, self.indexes.character, self.characterThresholdMode, self.MIN_CHAR_THRESH)
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
        return cls.SEP.join(x[0] for x in sortedNames)


    @staticmethod
    def nameScores(labels: list[tuple[str, float]], indexes: list[int]):
        return (labels[i] for i in indexes)

    @staticmethod
    def scoreKey(x: tuple):
        return x[1]


    @staticmethod
    def _loadLabels(csvPath: str) -> tuple[list[str], CategoryIndexes]:
        tagNames = list[str]()
        indexes = CategoryIndexes()

        with open(csvPath, 'r', newline='') as csvFile:
            # columns: tag_id, name, category, count
            reader = csv.reader(csvFile)

            row = next(reader)
            if row[1] != "name" or row[2] != "category":
                raise ValueError("Unrecognized column names in CSV file")

            for i, row in enumerate(reader):
                tagNames.append(TagBackend.removeUnderscore(row[1]))

                category = int(row[2])
                match category:
                    case 0: indexes.general.append(i)
                    case 4: indexes.character.append(i)
                    case 9: indexes.rating.append(i)
                    case _:
                        raise ValueError(f"Invalid category in CSV file on row {i+1}: {category}")

        return tagNames, indexes
