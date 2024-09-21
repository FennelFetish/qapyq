import numpy as np
import onnxruntime as rt
import pandas as pd
from PIL import Image
import torch # Not used directly, but required for GPU inference


def load_labels(dataframe: pd.DataFrame) -> list[str]:
    # https://github.com/toriato/stable-diffusion-webui-wd14-tagger/blob/a9eacb1eff904552d3012babfa28b57e1d3e295c/tagger/ui.py#L368
    kaomojis = {
        "0_0", "(o)_(o)", "+_+", "+_-", "._.", "<o>_<o>", "<|>_<|>", "=_=", ">_<", "3_3", "6_9", ">_o", "@_@", "^_^", "o_o", "u_u", "x_x", "|_|", "||_||"
    }

    name_series = dataframe["name"]
    name_series = name_series.map(
        lambda x: x.replace("_", " ") if x not in kaomojis else x
    )
    tag_names = name_series.tolist()

    rating_indexes = list(np.where(dataframe["category"] == 9)[0])
    general_indexes = list(np.where(dataframe["category"] == 0)[0])
    character_indexes = list(np.where(dataframe["category"] == 4)[0])
    return tag_names, rating_indexes, general_indexes, character_indexes


def mcut_threshold(probs: np.ndarray):
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



class Predictor:
    def __init__(self, model_path, csv_path):
        tags_df = pd.read_csv(csv_path)
        sep_tags = load_labels(tags_df)

        self.tag_names = sep_tags[0]
        self.rating_indexes = sep_tags[1]
        self.general_indexes = sep_tags[2]
        self.character_indexes = sep_tags[3]

        #https://onnxruntime.ai/docs/api/python/api_summary.html
        # GPU Acceleration needs 'import torch' ?

        # providers = [
        #     ("CUDAExecutionProvider", {
        #         "device_id": torch.cuda.current_device(),
        #         "user_compute_stream": str(torch.cuda.current_stream().cuda_stream)
        #     }),
        #     "CPUExecutionProvider"
        # ]
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        self.model = rt.InferenceSession(model_path, providers=providers)
        _, height, width, _ = self.model.get_inputs()[0].shape
        self.model_target_size = height  # TODO: max(height, width) ?


    def __del__(self):
        if hasattr(self, "model"):
            del self.model


    def prepare_image(self, image):
        target_size = self.model_target_size

        canvas = Image.new("RGBA", image.size, (255, 255, 255))
        canvas.alpha_composite(image)
        image = canvas.convert("RGB")

        # Pad image to square
        image_shape = image.size
        max_dim = max(image_shape)
        pad_left = (max_dim - image_shape[0]) // 2
        pad_top = (max_dim - image_shape[1]) // 2

        padded_image = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
        padded_image.paste(image, (pad_left, pad_top))

        # Resize
        if max_dim != target_size:
            padded_image = padded_image.resize(
                (target_size, target_size),
                Image.BICUBIC,
            )

        # Convert to numpy array
        image_array = np.asarray(padded_image, dtype=np.float32)

        # Convert PIL-native RGB to BGR
        image_array = image_array[:, :, ::-1]

        return np.expand_dims(image_array, axis=0)


    def predict(self, image, general_thresh, general_mcut_enabled, character_thresh, character_mcut_enabled):
        image = self.prepare_image(image)

        input_name = self.model.get_inputs()[0].name
        label_name = self.model.get_outputs()[0].name
        preds = self.model.run([label_name], {input_name: image})[0]

        labels = list(zip(self.tag_names, preds[0].astype(float)))

        # First 4 labels are actually ratings: pick one with argmax
        ratings_names = [labels[i] for i in self.rating_indexes]
        rating = dict(ratings_names)

        # Then we have general tags: pick any where prediction confidence > threshold
        general_names = [labels[i] for i in self.general_indexes]

        if general_mcut_enabled:
            general_probs = np.array([x[1] for x in general_names])
            general_thresh = mcut_threshold(general_probs)

        general_res = [x for x in general_names if x[1] > general_thresh]
        general_res = dict(general_res)

        # Everything else is characters: pick any where prediction confidence > threshold
        character_names = [labels[i] for i in self.character_indexes]

        if character_mcut_enabled:
            character_probs = np.array([x[1] for x in character_names])
            character_thresh = mcut_threshold(character_probs)
            character_thresh = max(0.15, character_thresh)

        character_res = [x for x in character_names if x[1] > character_thresh]
        character_res = dict(character_res)

        sorted_general_strings = sorted(
            general_res.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        # sorted_general_strings = [x[0] for x in sorted_general_strings]
        # sorted_general_strings = (
        #     ", ".join(sorted_general_strings)#.replace("(", "\(").replace(")", "\)")
        # )
        sorted_general_strings = ", ".join(x[0] for x in sorted_general_strings)

        # TODO: Only process and return the tags string, we don't need the rest
        # TODO: Append character to tags?
        return sorted_general_strings, rating, character_res, general_res



class WDTag:
    def __init__(self, config: dict):
        self.general_thresh = 0.35
        self.general_mcut = False
        self.character_thresh = 0.85
        self.character_mcut = False
        self.setConfig(config)

        self.predictor = Predictor(config.get("model_path"), config.get("csv_path"))


    def __del__(self):
        if hasattr(self, "predictor"):
            del self.predictor


    def setConfig(self, config: dict):
        self.general_thresh = float(config.get("threshold", 0.35))
        self.general_mcut   = bool(config.get("general_mcut_enabled", False))

        self.character_thresh = float(config.get("character_thresh", 0.85))
        self.character_mcut   = bool(config.get("character_mcut_enabled", False))

    
    def tag(self, imgPath) -> str:
        img = Image.open(imgPath).convert("RGBA")

        sorted_general_strings, rating, character_res, general_res = self.predictor.predict(
            img,
            self.general_thresh, self.general_mcut,
            self.character_thresh, self.character_mcut
        )

        return sorted_general_strings
