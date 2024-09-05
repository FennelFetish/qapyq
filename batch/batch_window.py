from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QThreadPool
from aux_window import AuxiliaryWindow
from .batch_caption import BatchCaption
import qtlib



class BatchWindow(AuxiliaryWindow):
    def __init__(self):
        super().__init__("Batch")

        # ProgressBar on status bar
        self.progressbar = QtWidgets.QProgressBar()
        statusBar = qtlib.ColoredMessageStatusBar()
        statusBar.addPermanentWidget(self.progressbar)
        self.setStatusBar(statusBar)

    
    def setupContent(self, tab) -> object:
        captionWidget = BatchCaption(tab, self.progressbar, self.statusBar())
        tabWidget = QtWidgets.QTabWidget()
        tabWidget.addTab(captionWidget, "Caption")
        tabWidget.addTab(QtWidgets.QWidget(), "Transform") # LLM process json
        return tabWidget


    def teardownContent(self, content):
        pass
