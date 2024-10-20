from PySide6 import QtWidgets
from .batch_caption import BatchCaption
from .batch_transform import BatchTransform
from .batch_rules import BatchRules
from .batch_apply import BatchApply
from .batch_log import BatchLog
import lib.qtlib as qtlib


class BatchContainer(QtWidgets.QTabWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        
        self.progressbar = QtWidgets.QProgressBar()
        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.addPermanentWidget(self.progressbar)

        self.logWidget = BatchLog()
        log = self.logWidget.addLog

        captionWidget        = BatchCaption(tab, log, self.progressbar, self.statusBar)
        self.rulesWidget     = BatchRules(tab, log, self.progressbar, self.statusBar)
        self.transformWidget = BatchTransform(tab, log, self.progressbar, self.statusBar)
        self.applyWidget     = BatchApply(tab, log, self.progressbar, self.statusBar)

        self.addTab(captionWidget, "Caption (json)")
        self.addTab(self.rulesWidget, "Rules (json → json)")
        self.addTab(self.transformWidget, "Transform (json → json)")
        self.addTab(self.applyWidget, "Apply (json → txt)")
        self.addTab(self.logWidget, "Log")

        tab.filelist.addListener(self)
        self.onFileChanged(tab.filelist.getCurrentFile())


    def onFileChanged(self, currentFile):
        self.transformWidget.onFileChanged(currentFile)
        self.rulesWidget.onFileChanged(currentFile)
        self.applyWidget.onFileChanged(currentFile)
        self.logWidget.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)
