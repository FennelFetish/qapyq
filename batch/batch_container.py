from PySide6 import QtWidgets
from .batch_caption import BatchCaption
from .batch_transform import BatchTransform
from .batch_rules import BatchRules
from .batch_apply import BatchApply
from .batch_scale import BatchScale
from .batch_mask import BatchMask
from .batch_crop import BatchCrop
from .batch_log import BatchLog
from .batch_task import BatchProgressUpdate
import lib.qtlib as qtlib


# TODO: Batch File operations:
#   - Move or Copy files together to new detination (image, json, txt) set by path template
#     - Optionally copy text/json into archive instead for backup
#     - Optionally create directory structure with symlinks instead of copy


class BatchContainer(QtWidgets.QTabWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        
        self.progressbar = BatchProgressBar()
        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.addPermanentWidget(self.progressbar)

        self.logWidget = BatchLog()
        log = self.logWidget.emitLog

        self.captionWidget   = BatchCaption(tab, log, self.progressbar, self.statusBar)
        self.rulesWidget     = BatchRules(tab, log, self.progressbar, self.statusBar)
        self.transformWidget = BatchTransform(tab, log, self.progressbar, self.statusBar)
        self.applyWidget     = BatchApply(tab, log, self.progressbar, self.statusBar)
        self.scaleWidget     = BatchScale(tab, log, self.progressbar, self.statusBar)
        self.maskWidget      = BatchMask(tab, log, self.progressbar, self.statusBar)
        self.cropWidget      = BatchCrop(tab, log, self.progressbar, self.statusBar)

        self.addTab(self.captionWidget, "Caption (json)")
        self.addTab(self.rulesWidget, "Rules (json → json)")
        self.addTab(self.transformWidget, "Transform (json → json)")
        self.addTab(self.applyWidget, "Apply (json → txt/json)")
        self.addTab(self.scaleWidget, "Scale (Image)")
        self.addTab(self.maskWidget, "Mask (Image)")
        self.addTab(self.cropWidget, "Crop (Image)")
        self.addTab(self.logWidget, "Log")

        tab.filelist.addListener(self)
        self.onFileChanged(tab.filelist.getCurrentFile())


    def onFileChanged(self, currentFile):
        self.captionWidget.onFileChanged(currentFile)
        self.rulesWidget.onFileChanged(currentFile)
        self.transformWidget.onFileChanged(currentFile)
        self.applyWidget.onFileChanged(currentFile)
        self.scaleWidget.onFileChanged(currentFile)
        self.maskWidget.onFileChanged(currentFile)
        self.cropWidget.onFileChanged(currentFile)
        self.logWidget.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)



class BatchProgressBar(QtWidgets.QProgressBar):
    def __init__(self):
        super().__init__()
        self._timeText = ""
        self._lastTime = None
    
    def setTime(self, time: BatchProgressUpdate | None):
        if time is None:
            return

        self._lastTime = time
        timeSpent      = self.formatSeconds(time.timeSpent)
        timeRemaining  = self.formatSeconds(time.timeRemaining)
        self._timeText = f"{time.filesProcessed}/{time.filesTotal} Files processed in {timeSpent}, " \
                       + f"{timeRemaining} remaining ({time.timePerFile:.2f}s per File)"

    def resetTime(self):
        self._lastTime = None
        self._timeText = ""
        self.update()

    def text(self) -> str:
        if text := super().text():
            if self._timeText:
                return f"{text}  -  {self._timeText}"
            return text
        return self._timeText

    def reset(self):
        super().reset()
        if self._lastTime:
            timeSpent = self.formatSeconds(self._lastTime.timeSpent)
            self._timeText = f"{self._lastTime.filesProcessed} Files processed in {timeSpent} ({self._lastTime.timePerFile:.2f}s per File)"
        else:
            self._timeText = ""

    @staticmethod
    def formatSeconds(seconds: float):
        s = round(seconds)
        hours = s // 3600
        minutes = (s % 3600) // 60
        seconds = s % 60

        if hours > 0:
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        return f"{minutes:02}:{seconds:02}"
