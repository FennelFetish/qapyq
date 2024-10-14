import json, os, sys

class DevMap:
    CPU = "cpu"

    def __init__(self, maxLayerLLM: int, maxLayerVis: int = 0):
        self.maxLayerLLM = max(maxLayerLLM, 0)
        self.maxLayerVis = max(maxLayerVis, 0)

        self.deviceMap = dict()
        self.hasCpuLayers = False

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


    def setCudaLayer(self, name: str, device: int = 0) -> None:
        self.deviceMap[name] = device

    def setCpuLayer(self, name: str) -> None:
        self.deviceMap[name] = self.CPU
        self.hasCpuLayers = True
    

    def setLLMLayers(self, prefix: str, numGpuLayers: int, device: int = 0) -> None:
        self._setLayers(prefix, numGpuLayers, self.maxLayerLLM, device)

    def setVisLayers(self, prefix: str, numGpuLayers: int, device: int = 0) -> None:
        self._setLayers(prefix, numGpuLayers, self.maxLayerVis, device)

    def _setLayers(self, prefix: str, numGpuLayers: int, maxGpuLayer: int, device: int) -> None:
        numGpuLayers = min(numGpuLayers, maxGpuLayer)
        if numGpuLayers < 0:
            numGpuLayers = maxGpuLayer

        if numGpuLayers == maxGpuLayer:
            self.deviceMap[prefix] = device
            return
        self.hasCpuLayers = True

        self.deviceMap[f"{prefix}.0"] = device

        for l in range(1, numGpuLayers-1):
            self.deviceMap[f"{prefix}.{l}"] = device
        for l in range(numGpuLayers-1, maxGpuLayer):
            self.deviceMap[f"{prefix}.{l}"] = self.CPU
        
        self.deviceMap[f"{prefix}.{maxGpuLayer}"] = device


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
