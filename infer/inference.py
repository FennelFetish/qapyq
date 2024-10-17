from PySide6.QtCore import QThreadPool, QRunnable, Slot
from lib.util import Singleton


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


    def queueTask(self, task: QRunnable):
        self.threadPool.start(task)



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
