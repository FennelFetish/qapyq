from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QSize, Slot, Signal, QThreadPool, QObject, QRunnable
import os


THUMBNAILS = {}
THUMBNAIL_SIZE = 256


class Gallery(QtWidgets.QListWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.filelist = tab.filelist
        self.tileSize = THUMBNAIL_SIZE

        self.setFlow(QtWidgets.QListWidget.LeftToRight)
        self.setWrapping(True)
        #self.setMovement(QtWidgets.QListWidget.Static)
        self.setResizeMode(QtWidgets.QListWidget.Adjust)
        #self.setSortingEnabled(True)

        self.setHorizontalScrollMode(QtWidgets.QListWidget.ScrollPerPixel)
        self.setVerticalScrollMode(QtWidgets.QListWidget.ScrollPerPixel)
        self.setSpacing(1)

        self.setViewMode(QtWidgets.QListView.IconMode)
        #self.setIconSize(QSize(100, 100))
        #self.setUniformItemSizes(True)
        self.adjustGrid(self.width())

        self.currentItemChanged.connect(self.onFileSelected)


    def updateImages(self):
        self.clear()
        self.blockSignals(True)
        for file in self.filelist.getFiles():
            self.addImage(file)
        self.blockSignals(False)
    
    def addImage(self, file):
        galleryItem = GalleryItem(self.tab, file)
        galleryItem.setSize(self.tileSize)

        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(galleryItem.size())
        self.addItem(item)
        self.setItemWidget(item, galleryItem)

        if self.filelist.getCurrentFile() == file:
            self.setCurrentItem(item)
            galleryItem.setSelected(True)


    def onFileChanged(self, currentFile):
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget.file == currentFile:
                self.updateSelection(item, self.currentItem())

                self.blockSignals(True)
                self.setCurrentItem(item)
                self.blockSignals(False)
                break
    
    def onFileListChanged(self, currentFile):
        self.updateImages()


    @Slot()
    def onFileSelected(self, currentItem, prevItem):
        self.updateSelection(currentItem, prevItem)
        item = self.itemWidget(currentItem)
        if item:
            self.filelist.removeListener(self)
            self.filelist.setCurrentFile(item.file)
            self.filelist.addListener(self)

    def updateSelection(self, current, prev):
        wCurrent = self.itemWidget(current)
        if wCurrent:
            wCurrent.setSelected(True)

        wPrev = self.itemWidget(prev)
        if wPrev:
            wPrev.setSelected(False)

    def adjustGrid(self, widgetWidth):
        w = widgetWidth - 4
        cols = w // THUMBNAIL_SIZE
        w = w / cols
        self.setGridSize(QSize(w, w))
        self.tileSize = w

        for i in range(self.count()):
            widget = self.itemWidget(self.item(i))
            if widget:
                widget.setSize(w)

    def resizeEvent(self, event):
        self.adjustGrid(event.size().width())
        #super().resizeEvent(event)

        

# https://stackoverflow.com/questions/74252940/how-to-automatically-adjust-the-elements-of-qgridlayout-to-fit-in-a-row-when-the
class GalleryItem(QtWidgets.QFrame):
    def __init__(self, tab, file):
        super().__init__()
        self.tab = tab
        self.file = file

        self.img = QtWidgets.QLabel()
        self.img.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        #self.img.setScaledContents(True)
        self.updateThumbnail(file)

        filename = os.path.basename(file)
        self.label = QtWidgets.QLabel(filename)
        self.label.setAlignment(Qt.AlignCenter | Qt.AlignTop)
        self.label.setMaximumWidth(THUMBNAIL_SIZE)
        self.label.setWordWrap(True)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.img)
        layout.addWidget(self.label)
        layout.addStretch(1)
        self.setLayout(layout)

    
    def setSize(self, sideLength):
        self.label.setMaximumWidth(sideLength)

    def setSelected(self, selected):
        self.setFrameShape(QtWidgets.QFrame.Box if selected else QtWidgets.QFrame.NoFrame)


    def updateThumbnail(self, file):
        if file in THUMBNAILS:
            self.img.setPixmap(THUMBNAILS[file])

        task = ThumbnailTask(file)
        task.signals.done.connect(self.onThumbnailLoaded)
        QThreadPool.globalInstance().start(task)

    def onThumbnailLoaded(self, file, img):
        pixmap = QtGui.QPixmap.fromImage(img)
        THUMBNAILS[file] = pixmap
        self.img.setPixmap(pixmap)

    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.ignore()
            return
        
        if event.button() == Qt.RightButton:
            self.tab.imgview.tool.onGalleryRightClick(self.file)



# TODO: What if gallery is closed and reopened before all tasks finish?
#       In this case new (duplicate) tasks are queued.
class ThumbnailTask(QRunnable):
    def __init__(self, file):
        super().__init__()
        self.file = file
        self.signals = ThumbnailTaskSignals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        img = QtGui.QImage(self.file)
        img = img.scaled(THUMBNAIL_SIZE+20, THUMBNAIL_SIZE+20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.signals.done.emit(self.file, img)


class ThumbnailTaskSignals(QObject):
    done = Signal(str, object)

    def __init__(self):
        super().__init__()
