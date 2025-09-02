from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Slot, QTimer
from .batch_caption import BatchCaption
from .batch_transform import BatchTransform
from .batch_rules import BatchRules
from .batch_apply import BatchApply
from .batch_scale import BatchScale
from .batch_mask import BatchMask
from .batch_crop import BatchCrop
#from .batch_metric import BatchMetric
from .batch_file import BatchFile
from .batch_log import BatchLog
from .batch_task import BatchProgressBar
import lib.qtlib as qtlib


class BatchContainer(QtWidgets.QTabWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab

        self.progressBar = BatchProgressBar()
        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.setSizeGripEnabled(False)
        self.statusBar.addPermanentWidget(self.progressBar)
        bars = (self.progressBar, self.statusBar)

        self.logWidget = BatchLog()

        self._widgets = {
            "caption":      BatchCaption(tab, self.logWidget, bars),
            "rules":        BatchRules(tab, self.logWidget, bars),
            "transform":    BatchTransform(tab, self.logWidget, bars),
            "apply":        BatchApply(tab, self.logWidget, bars),
            "scale":        BatchScale(tab, self.logWidget, bars),
            "mask":         BatchMask(tab, self.logWidget, bars),
            "crop":         BatchCrop(tab, self.logWidget, bars),
            #"metric":       BatchMetric(tab, self.logWidget, bars),
            "file":         BatchFile(tab, self.logWidget, bars),
            "log":          self.logWidget
        }

        self.addTab(self._widgets["caption"], "Caption (json)")
        self.addTab(self._widgets["rules"], "Rules (json → json)")
        self.addTab(self._widgets["transform"], "Transform (json → json)")
        self.addTab(self._widgets["apply"], "Apply (json → txt/json)")
        self.addTab(self._widgets["scale"], "Scale (Image)")
        self.addTab(self._widgets["mask"], "Mask (Image)")
        self.addTab(self._widgets["crop"], "Crop (Image)")
        #self.addTab(self._widgets["metric"], "Metric (Image)")
        self.addTab(self._widgets["file"], "File")
        self.addTab(self._widgets["log"], "Log")

        tab.filelist.addListener(self)
        self.onFileChanged(tab.filelist.getCurrentFile())

        self._activeTab = None
        self.currentChanged.connect(self._onTabChanged)
        self._onTabChanged(self.currentIndex())

        self._initAnim()


    def _initAnim(self):
        self._tabAnims: dict[int, TabColorAnim] = dict()
        for i in range(self.count()):
            widget = self.widget(i)
            if hasattr(widget, "taskHandler"):
                widget.taskHandler.started.connect(lambda index=i: self._onBatchStarted(index))
                widget.taskHandler.finished.connect(lambda index=i: self._onBatchEnded(index))

    def deleteLater(self):
        for anim in self._tabAnims.values():
            anim.stop()

        super().deleteLater()


    def getTab(self, name: str, selectTab=False) -> BatchRules:
        widget = self._widgets[name]
        if selectTab:
            self.setCurrentWidget(widget)
        return widget


    def onFileChanged(self, currentFile):
        for widget in self._widgets.values():
            widget.onFileChanged(currentFile)

    def onFileListChanged(self, currentFile):
        self.onFileChanged(currentFile)


    @Slot()
    def _onTabChanged(self, index: int):
        activeTab = self.widget(index)
        if activeTab == self.logWidget:
            return

        if self._activeTab:
            self._activeTab.taskHandler.setTabActive(False)
        if activeTab:
            activeTab.taskHandler.setTabActive(True)

        self._activeTab = activeTab


    @Slot()
    def _onBatchStarted(self, index: int):
        if index not in self._tabAnims:
            self._tabAnims[index] = TabColorAnim(self.tabBar(), index)

    @Slot()
    def _onBatchEnded(self, index: int):
        if anim := self._tabAnims.pop(index, None):
            anim.stop()



class TabColorAnim:
    COLOR_STATIC: QtGui.QColor = None
    COLORS: list[QtGui.QColor] = None
    STEPS = 14

    def __init__(self, tabBar: QtWidgets.QTabBar, tabIndex: int):
        self.tabBar = tabBar
        self.tabIndex = tabIndex
        self._colorIndex = 0

        self._timer = QTimer(interval=100)
        self._timer.timeout.connect(self._update)
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.tabBar.setTabTextColor(self.tabIndex, self.COLOR_STATIC)

    @Slot()
    def _update(self):
        self.tabBar.setTabTextColor(self.tabIndex, self.COLORS[self._colorIndex])
        self._colorIndex += 1
        if self._colorIndex >= len(self.COLORS):
            self._colorIndex = 0


    @classmethod
    def _initColors(cls):
        import math
        palette = QtWidgets.QApplication.palette()
        cls.COLOR_STATIC = palette.color(QtGui.QPalette.ColorRole.Text)
        colorHighlight = palette.color(QtGui.QPalette.ColorRole.Highlight)
        colorHighlight = qtlib.getHighlightColor(colorHighlight.name()) # "#ff7300"

        R0, G0, B0 = cls.COLOR_STATIC.redF(), cls.COLOR_STATIC.greenF(), cls.COLOR_STATIC.blueF()
        R1, G1, B1 = colorHighlight.redF(), colorHighlight.greenF(), colorHighlight.blueF()

        cls.COLORS = []
        for i in range(cls.STEPS+1):
            t = i / cls.STEPS
            t = (t+0.5) * 2*math.pi
            f = 0.4 + 0.6*(math.cos(t)+1)*0.5

            r = f*(R1-R0) + R0
            g = f*(G1-G0) + G0
            b = f*(B1-B0) + B0
            cls.COLORS.append(QtGui.QColor.fromRgbF(r, g, b))


TabColorAnim._initColors()
