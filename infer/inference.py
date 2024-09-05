from PySide6.QtCore import QThreadPool, QRunnable, QObject, Signal, Slot
from util import Singleton
from config import Config


class Inference(metaclass=Singleton):
    def __init__(self):
        self.threadPool = QThreadPool()
        self.threadPool.setMaxThreadCount(1)

        self.minicpm = None
        self.joytag  = None


    def loadMiniCpm(self):
        if not self.minicpm:
            from .minicpm import MiniCPM
            self.minicpm = MiniCPM(Config.inferCaptionModelPath, Config.inferCaptionClipPath)
        return self.minicpm

    def unloadMiniCpm(self):
        if self.minicpm:
            del self.minicpm
            self.minicpm = None


    def loadJoytag(self):
        if not self.joytag:
            from .joytag import JoyTag
            self.joytag = JoyTag(Config.inferTagModelPath)
        return self.joytag

    def unloadJoytag(self):
        if self.joytag:
            del self.joytag
            self.joytag = None


    def captionAsync(self, handler, imgPath, prompt, systemPrompt=None):
        task = MiniCPMInferenceTask(self.loadMiniCpm(), imgPath, prompt, systemPrompt)
        task.signals.done.connect(handler)
        self.threadPool.start(task)
        return task

    def captionMultiAsync(self, handler, imgPath, prompts: dict, systemPrompt=None):
        task = MiniCPMMultiInferenceTask(self.loadMiniCpm(), imgPath, prompts, systemPrompt)
        task.signals.done.connect(handler)
        self.threadPool.start(task)
        return task 

    def tagAsync(self, handler, imgPath):
        task = JoytagInferenceTask(self.loadJoytag(), imgPath)
        task.signals.done.connect(handler)
        self.threadPool.start(task)
        return task



class MiniCPMInferenceTask(QRunnable):
    def __init__(self, minicpm, imgPath, prompt, systemPrompt=None):
        super().__init__()
        self.signals = InferenceTaskSignals()

        self.minicpm = minicpm
        self.imgPath = imgPath
        self.prompt  = prompt
        self.systemPrompt = systemPrompt

    @Slot()
    def run(self):
        try:
            result = self.minicpm.caption(self.imgPath, self.prompt, self.systemPrompt)[0].strip()
            self.signals.done.emit(self.imgPath, result)
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()


class MiniCPMMultiInferenceTask(QRunnable):
    def __init__(self, minicpm, imgPath, prompts: dict, systemPrompt=None):
        super().__init__()
        self.signals = MultiInferenceTaskSignals()

        self.minicpm = minicpm
        self.imgPath = imgPath
        self.prompts  = prompts
        self.systemPrompt = systemPrompt

    @Slot()
    def run(self):
        try:
            results = self.minicpm.captionMulti(self.imgPath, self.prompts, self.systemPrompt)
            self.signals.done.emit(self.imgPath, results)
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()


class JoytagInferenceTask(QRunnable):
    def __init__(self, joytag, imgPath):
        super().__init__()
        self.signals = InferenceTaskSignals()

        self.joytag  = joytag
        self.imgPath = imgPath

    @Slot()
    def run(self):
        try:
            tags = self.joytag.caption(self.imgPath)
            self.signals.done.emit(self.imgPath, tags)
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()


class InferenceTaskSignals(QObject):
    done = Signal(str, str)
    fail = Signal()

    def __init__(self):
        super().__init__()

class MultiInferenceTaskSignals(QObject):
    done = Signal(str, dict)
    fail = Signal()

    def __init__(self):
        super().__init__()
