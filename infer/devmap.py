import json, os, sys, math
from config import Config

class DevMap:
    CPU = "cpu"

    def __init__(self, maxLayerLLM: int, maxLayerVis: int = 0):
        self.maxLayerLLM = max(maxLayerLLM, 0)
        self.maxLayerVis = max(maxLayerVis, 0)

        self.deviceMap = dict()
        self.hasCpuLayers = False

        self.device = int(Config.inferDevices[0] or 0) if Config.inferDevices else 0

    @classmethod
    def fromConfig(cls, modelDirectory: str, llmLayersKey: str, visLayersKey: str = None):
        path = os.path.join(modelDirectory, "config.json")
        with open(path, 'r') as file:
            config = json.load(file)

        devmap = DevMap(0, 0)
        devmap.maxLayerLLM = cls._getConfigValue(config, llmLayersKey) - 1
        if visLayersKey:
            devmap.maxLayerVis = cls._getConfigValue(config, visLayersKey) - 1

        return devmap

    @staticmethod
    def _getConfigValue(config: dict, key: str):
        val = config
        for k in key.split("."):
            val = val.get(k) if isinstance(val, dict) else None
        return int(val) if val else 0


    def setCudaLayer(self, name: str) -> None:
        self.deviceMap[name] = self.device

    def setCpuLayer(self, name: str) -> None:
        self.deviceMap[name] = self.CPU
        self.hasCpuLayers = True


    def setLLMLayers(self, prefix: str, gpuLayersPercent: int) -> None:
        numGpuLayers = self._getNumLayers("LLM", gpuLayersPercent, self.maxLayerLLM)
        self._setLayers(prefix, numGpuLayers, self.maxLayerLLM)

    def setVisLayers(self, prefix: str, gpuLayersPercent: int) -> None:
        numGpuLayers = self._getNumLayers("Vis", gpuLayersPercent, self.maxLayerVis)
        self._setLayers(prefix, numGpuLayers, self.maxLayerVis)

    def _getNumLayers(self, type: str, percent: int, maxLayer: int):
        if percent < 0:
            percent = 100

        numGpuLayers = math.ceil((percent / 100) * (maxLayer+1))
        print(f"Total {type} layers: {maxLayer+1}, GPU: {numGpuLayers} ({percent}% on device {self.device}), CPU: {(maxLayer+1)-numGpuLayers}")
        return numGpuLayers

    def _setLayers(self, prefix: str, numGpuLayers: int, maxGpuLayer: int) -> None:
        if numGpuLayers == 0:
            self.deviceMap[prefix] = self.CPU
            return

        numGpuLayers = min(numGpuLayers, maxGpuLayer+1)
        if numGpuLayers < 0:
            numGpuLayers = maxGpuLayer+1

        if numGpuLayers == maxGpuLayer+1:
            self.deviceMap[prefix] = self.device
            return
        self.hasCpuLayers = True

        # Set last layer first (if 1 GPU layer), then (with increasing layer count) continue at the beginning.
        self.deviceMap[f"{prefix}.0"] = self.device

        for l in range(1, numGpuLayers-1):
            self.deviceMap[f"{prefix}.{l}"] = self.device
        for l in range(numGpuLayers-1, maxGpuLayer):
            self.deviceMap[f"{prefix}.{l}"] = self.CPU

        self.deviceMap[f"{prefix}.{maxGpuLayer}"] = self.device


    @property
    def attention(self) -> str:
        if self.hasCpuLayers:
            return "eager"

        try:
            import flash_attn
            return "flash_attention_2"
        except:
            return "eager"


    def print(self) -> None:
        sys.stderr.write(f"Device Map:{os.linesep}")
        for k, v in self.deviceMap.items():
            sys.stderr.write(f"{k} => {v}{os.linesep}")

        sys.stderr.flush()

    @staticmethod
    def printDeviceMap(model) -> None:
        deviceMap = {name: param.device for name, param in model.named_parameters()}

        sys.stderr.write(f"Model's Device Map:{os.linesep}")
        for k, v in deviceMap.items():
            sys.stderr.write(f"{k} => {v}{os.linesep}")

        sys.stderr.flush()

    @staticmethod
    def saveDeviceMap(model, path) -> None:
        deviceMap = {name: param.device for name, param in model.named_parameters()}

        with open(path, 'w') as file:
            for k, v in deviceMap.items():
                file.write(f"{k} => {v}{os.linesep}")



if __name__ == "__main__":
    layers = 20
    # for i in range(layers+1):
    #     devmap = DevMap(layers-1)
    #     devmap._setLayers("llm", i, layers-1, 0)
    #     print(f"=== {i} / {layers} LLM Layers ===")
    #     devmap.print()

    for p in range(0, 101, 5):
        devmap = DevMap(layers-1)
        devmap.setLLMLayers("llm", p, 0)
        print(f"=== {p}% / {layers} LLM Layers ===")
        devmap.print()
