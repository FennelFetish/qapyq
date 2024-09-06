from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QThreadPool
from aux_window import AuxiliaryWindow
from .batch_caption import BatchCaption
from .batch_apply import BatchApply
import qtlib



class BatchWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Batch")

        # ProgressBar on status bar
        self.progressbar = QtWidgets.QProgressBar()
        statusBar = qtlib.ColoredMessageStatusBar()
        statusBar.addPermanentWidget(self.progressbar)
        self.setStatusBar(statusBar)

        self.tab = None

    
    def setupContent(self, tab) -> object:
        tab.filelist.addListener(self)
        self.tab = tab

        captionWidget = BatchCaption(tab, self.progressbar, self.statusBar())
        self.applyWidget = BatchApply(tab, self.progressbar, self.statusBar())

        tabWidget = QtWidgets.QTabWidget()
        tabWidget.addTab(captionWidget, "Generate")
        tabWidget.addTab(QtWidgets.QWidget(), "Transform") # LLM process json
        tabWidget.addTab(self.applyWidget, "Set Caption") # LLM process json

        self.onFileChanged(tab.filelist.getCurrentFile())
        return tabWidget


    def teardownContent(self, content):
        self.tab.filelist.removeListener(self)
        self.tab = None
        self.applyWidget = None


    def onFileChanged(self, currentFile):
        self.applyWidget.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)
