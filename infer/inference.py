from PySide6.QtCore import QThreadPool, QRunnable, QObject, Signal, Slot
from util import Singleton


class Inference(metaclass=Singleton):
    def __init__(self):
        # All interaction with the interference process must happen inside this thread
        self.threadPool = QThreadPool()
        self.threadPool.setMaxThreadCount(1)

        from .inference_proc import InferenceProcess
        self.proc = InferenceProcess()


    def startProcess(self):
        task = InferenceTask(lambda: self.proc.start())
        self.threadPool.start(task)

    def quitProcess(self):
        task = InferenceTask(lambda: self.proc.stop())
        self.threadPool.start(task)


    def captionAsync(self, handler, failHandler, imgPath, prompts: dict, systemPrompt=None, config={}):
        task = MiniCpmInferenceTask(self.proc, imgPath, prompts, systemPrompt, config)
        task.signals.done.connect(handler)
        task.signals.fail.connect(failHandler)
        self.threadPool.start(task)
        return task 

    def tagAsync(self, handler, failHandler, imgPath, threshold):
        task = JoytagInferenceTask(self.proc, imgPath, threshold)
        task.signals.done.connect(handler)
        task.signals.fail.connect(failHandler)
        self.threadPool.start(task)
        return task



class MiniCpmInferenceTask(QRunnable):
    class Signals(QObject):
        done = Signal(str, dict)
        fail = Signal()

    def __init__(self, proc, imgPath, prompts: dict, systemPrompt=None, config={}):
        super().__init__()
        self.signals = MiniCpmInferenceTask.Signals()
        self.proc = proc
        self.imgPath = imgPath
        self.prompts = prompts
        self.systemPrompt = systemPrompt
        self.config = config

    @Slot()
    def run(self):
        try:
            self.proc.start()
            self.proc.setupCaption(self.config)
            captions = self.proc.caption(self.imgPath, self.prompts, self.systemPrompt)
            if captions != None:
                self.signals.done.emit(self.imgPath, captions)
            else:
                self.signals.fail.emit()
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()



class JoytagInferenceTask(QRunnable):
    class Signals(QObject):
        done = Signal(str, str)
        fail = Signal()

    def __init__(self, proc, imgPath, threshold):
        super().__init__()
        self.signals = JoytagInferenceTask.Signals()
        self.proc = proc
        self.imgPath = imgPath
        self.threshold = threshold

    @Slot()
    def run(self):
        try:
            self.proc.start()
            self.proc.setupTag(self.threshold)
            tags = self.proc.tag(self.imgPath)
            if tags != None:
                self.signals.done.emit(self.imgPath, tags)
            else:
                self.signals.fail.emit()
        except Exception as ex:
            print("Error during inference:")
            print(ex)
            self.signals.fail.emit()



class InferenceTask(QRunnable):
    def __init__(self, func):
        super().__init__()
        self.func = func

    @Slot()
    def run(self):
        try:
            self.func()
        except Exception as ex:
            print("Error in inference thread:")
            print(ex)
