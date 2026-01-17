import os, json, re
import torch
import numpy as np
from typing import Union, TYPE_CHECKING
from host.imagecache import ImageFile
from config import Config
from .devmap import DevMap


if TYPE_CHECKING:
    from diffusers.models.autoencoders.autoencoder_kl import AutoencoderKL
    from diffusers.models.autoencoders.autoencoder_kl_flux2 import AutoencoderKLFlux2
    from diffusers.models.autoencoders.autoencoder_kl_qwenimage import AutoencoderKLQwenImage

VaeClass = Union['AutoencoderKL', 'AutoencoderKLFlux2', 'AutoencoderKLQwenImage']


class VaeBackend:
    SIZE_QUANT = 8  # TODO: Load from config

    def __init__(self, config: dict):
        self.device, _ = DevMap.getTorchDeviceDtype()

        self.vae: VaeClass

        vaeCfg = self._loadConfig(config["vae_type"])
        match vaeCfg.get("_class_name"):
            case "AutoencoderKLFlux2":
                from diffusers.models.autoencoders.autoencoder_kl_flux2 import AutoencoderKLFlux2
                self.vae = AutoencoderKLFlux2.from_config(vaeCfg)
                self._loadStateDict(self.vae, config["model_path"])

            case "AutoencoderKLQwenImage":
                from diffusers.models.autoencoders.autoencoder_kl_qwenimage import AutoencoderKLQwenImage
                self.vae = AutoencoderKLQwenImage.from_config(vaeCfg)
                self._loadStateDict(self.vae, config["model_path"])

                self.vae.enable_tiling(512, 512, 448, 448)

                def shapeLatent(tensor: torch.Tensor):
                    # [H, W, C] -> [1, C, 1, H, W]
                    return tensor.unsqueeze(0).permute(3, 0, 1, 2).unsqueeze(0)
                self.shapeLatent = shapeLatent

                def shapeMat(tensor: torch.Tensor):
                    # [1, C, 1, H, W] -> [H, W, C]
                    return tensor.permute(0, 2, 3, 4, 1)[0, 0]
                self.shapeMat = shapeMat

            case _:
                from diffusers.models.autoencoders.autoencoder_kl import AutoencoderKL
                self.vae = AutoencoderKL.from_single_file(
                    config["model_path"],
                    config=self._configPath(config["vae_type"]),
                    # low_cpu_mem_usage=False,
                    # ignore_mismatched_sizes=True
                )

        self.vae.use_tiling = True
        self.vae.eval().to(self.device)

        print(f"VAE dtype: {self.vae.dtype}")


    def setConfig(self, config: dict):
        pass


    @staticmethod
    def _configPath(vaeType: str) -> str:
        return os.path.join(Config.pathVaeConfig, f"{vaeType}.json")

    @classmethod
    def _loadConfig(cls, vaeType: str) -> dict:
        path = cls._configPath(vaeType)
        print(f"Using VAE config: '{path}'")
        with open(path, 'r') as file:
            return json.load(file)

    @classmethod
    def _loadStateDict(cls, vae: VaeClass, path: str):
        import safetensors.torch as sft
        stateDict = sft.load_file(path, device="cpu")
        #stateDict = fixKeys(stateDict)

        keyStatus = vae.load_state_dict(stateDict, strict=False, assign=True)

        if keyStatus.missing_keys:
            print(f"VAE missing keys:")
            for key in keyStatus.missing_keys:
                print(f"  {key}")
        if keyStatus.unexpected_keys:
            print(f"VAE unexpected keys:")
            for key in keyStatus.unexpected_keys:
                print(f"  {key}")


    @staticmethod
    def shapeLatent(tensor: torch.Tensor) -> torch.Tensor:
        # [H, W, C] -> [1, C, H, W]
        return tensor.permute(2, 0, 1).unsqueeze(0)

    @staticmethod
    def shapeMat(tensor: torch.Tensor) -> torch.Tensor:
        # [1, C, H, W] -> [H, W, C]
        return tensor.permute(0, 2, 3, 1)[0]


    @torch.inference_mode()
    def vaeRoundtrip(self, imgFile: ImageFile) -> tuple[int, int, bytes]:
        mat = imgFile.openCvMat(rgb=True, forceRGB=True)  # [H, W, C=3]
        h, w = mat.shape[:2]

        # Pad size to multiple of 8
        padX = -w % self.SIZE_QUANT
        padY = -h % self.SIZE_QUANT
        if padX or padY:
            matPad = np.zeros((h+padY, w+padX, 3), dtype=np.uint8)
            matPad[:h, :w, :] = mat
            mat = matPad

        tensor = torch.tensor(mat, dtype=self.vae.dtype, device=self.device)
        tensor = self.shapeLatent(tensor)

        # [0, 255] -> [-1, 1]
        tensor *= 2 / 255
        tensor -= 1

        # VAE roundtrip
        latentDist = self.vae.encode(tensor, return_dict=False)[0]
        decoded    = self.vae.decode(latentDist.sample(), return_dict=False)[0]

        # [-1, 1] -> [0, 255]
        decoded += 1.0
        decoded *= 0.5 * 255
        decoded.round_().clamp_(0, 255)

        decodedMat = self.shapeMat(decoded.to(device="cpu", dtype=torch.uint8)).numpy()

        # Remove padding
        if padX or padY:
            decodedMat = decodedMat[:h, :w, :]

        h, w = decodedMat.shape[:2]
        return w, h, decodedMat.tobytes()



class KeyReplace:
    def __init__(self, search: str, replace: str, groupReplace: dict[int, dict[str, str]] = {}):
        self.search = re.compile(search.replace(".", r"\."))
        self.replace = replace
        self.groupReplace = groupReplace

    def sub(self, key: str):
        return self.search.sub(self._getReplacement, key)

    def _getReplacement(self, match: re.Match) -> str:
        text = self.replace

        for i, repl in enumerate(match.groups()):
            if groupRepl := self.groupReplace.get(i):
                for s, r in groupRepl.items():
                    repl = repl.replace(s, r)

            text = text.replace(f"{{{i}}}", repl)

        print(f"{match.string[match.start():match.end()]} => {text}")
        return text


def fixKeys(state: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    subs = [
        # # SD 1.5
        # KeyReplace(r"(encoder|decoder).mid_block.attentions.0.proj_attn.(bias|weight)", "{0}.mid_block.attentions.0.to_out.0.{1}"),
        # KeyReplace(r"(encoder|decoder).mid_block.attentions.0.([a-z_]+).(bias|weight)", "{0}.mid_block.attentions.0.{1}.{2}", {
        #     1: {
        #         "query": "to_q",
        #         "key":   "to_k",
        #         "value": "to_v",
        #     }
        # }),

        # # Flux
        # KeyReplace(r"encoder.down.(\d+).block.", "encoder.down_blocks.{0}.resnets."),
        # KeyReplace(r"encoder.down.(\d+).downsample.", "encoder.down_blocks.{0}.downsamplers.0."),
        # KeyReplace(r"decoder.up.(\d+).block.", "decoder.up_blocks.{0}.resnets."),
        # KeyReplace(r"decoder.up.(\d+).upsample.", "decoder.up_blocks.{0}.upsamplers.0."),

        # # KeyReplace(r"(encoder|decoder).(up|down).(\d+).block.(\d+).([a-z0-9_]+).(weight|bias)", "{0}.{1}_blocks.{2}.resnets.{3}.{4}.{5}", {
        # #     4: {"nin_shortcut": "conv_shortcut"}
        # # }),
        # # KeyReplace(r"(encoder|decoder).(up|down).(\d+).(upsample|downsample).conv.(weight|bias)", "{0}.{1}_blocks.{2}.{3}rs.0.conv.{4}"),
        # KeyReplace(r"(encoder|decoder).norm_out.", "{0}.conv_norm_out."),
        # KeyReplace(r"(encoder|decoder).mid.attn_1.([a-z_]+).", "{0}.mid_block.attentions.0.{1}.", {
        #     1: {
        #         "norm": "group_norm",
        #         "q": "to_q",
        #         "k": "to_k",
        #         "v": "to_v",
        #         "proj_out": "to_out.0",
        #     }
        # }),
        # KeyReplace(r"(encoder|decoder).mid.block_(\d+).", "{0}.mid_block.resnets.{1}.", {
        #     1: {
        #         "1": "0",
        #         "2": "1",
        #     }
        # }),
        # KeyReplace(r"nin_shortcut", "conv_shortcut"),

        # Qwen
        KeyReplace(r"conv1.(weight|bias)", "quant_conv.{0}"),
        KeyReplace(r"conv2.(weight|bias)", "post_quant_conv.{0}"),
        KeyReplace(r"(encoder|decoder).conv1.(weight|bias)", "{0}.conv_in.{1}"),
        KeyReplace(r"(encoder|decoder).(downsamples|upsamples).(\d+).residual.(\d+).gamma", "{0}.{1}.{2}.{3}.gamma", {
            1: {
                "downsamples": "down_blocks",
                "upsamples":   "up_blocks",
            },
            3: {
                "0": "norm1",
                "3": "norm2",
            }
        }),
        KeyReplace(r"encoder.downsamples.(\d+).residual.(\d+).(weight|bias)", "encoder.down_blocks.{0}.{1}.{2}", {
            1: {
                "2": "conv1",
                "6": "conv2",
            }
        }),
        # TODO: Won't work. Needs remapping of block IDs
        KeyReplace(r"decoder.upsamples.(\d+).residual.(\d+).(weight|bias)", "decoder.up_blocks.{0}.resnets.{1}.{2}", {
            1: {
                "2": "conv1",
                "6": "conv2",
            }
        }),
    ]

    outState = {}
    for k, v in state.items():
        k = k.removeprefix("first_stage_model.")
        k = k.removeprefix("vae.")

        for sub in subs:
            k = sub.sub(k)

        outState[k] = v

    return outState
