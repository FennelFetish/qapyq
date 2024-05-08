from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, QSize, Slot, Signal, QThreadPool, QObject, QRunnable
import os


THUMBNAILS = {}
THUMNAIL_SIZE = 256


class Gallery(QtWidgets.QListWidget):
    def __init__(self, tab):
        super().__init__()
        self.tab = tab
        self.filelist = tab.filelist

        self.setFlow(QtWidgets.QListWidget.LeftToRight)
        self.setWrapping(True)
        #self.setMovement(QtWidgets.QListWidget.Static)
        self.setResizeMode(QtWidgets.QListWidget.Adjust)
        #self.setSortingEnabled(True)

        self.setHorizontalScrollMode(QtWidgets.QListWidget.ScrollPerPixel)
        self.setVerticalScrollMode(QtWidgets.QListWidget.ScrollPerPixel)
        self.setSpacing(4)

        #self.setIconSize(QSize(200, 200))
        #self.setViewMode(QtWidgets.QListView.IconMode)

        self.currentItemChanged.connect(self.onFileSelected)


    def updateImages(self):
        self.clear()
        self.blockSignals(True)
        for file in self.filelist.getFiles():
            self.addImage(file)
        self.blockSignals(False)
    
    def addImage(self, file):
        item = QtWidgets.QListWidgetItem()
        self.addItem(item)

        galleryItem = GalleryItem(file)
        item.setSizeHint(galleryItem.size())
        self.setItemWidget(item, galleryItem)

        if self.filelist.getCurrentFile() == file:
            self.setCurrentItem(item)


    def onFileChanged(self, currentFile):
        self.blockSignals(True)
        for i in range(self.count()):
            item = self.item(i)
            file = self.itemWidget(item).file
            if file == currentFile:
                self.setCurrentItem(item)
                break
        self.blockSignals(False)

    def onFileLoaded(self, currentFile):
        self.updateImages()


    @Slot()
    def onFileSelected(self, currentItem):
        item = self.itemWidget(currentItem)
        if item:
            file = item.file
            self.filelist.setCurrentFile(file)
            self.tab.imgview.loadImage(file, False)



class GalleryItem(QtWidgets.QFrame):
    def __init__(self, file):
        super().__init__()
        self.file = file

        self.img = QtWidgets.QLabel(alignment=Qt.AlignCenter)
        self.updateThumbnail(file)

        filename = os.path.basename(file)
        self.label = QtWidgets.QLabel(filename, alignment=Qt.AlignCenter)
        self.label.setMaximumWidth(240)
        self.label.setWordWrap(True)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)
        layout.addWidget(self.img)
        layout.addWidget(self.label)
        self.setLayout(layout)

        size = layout.sizeHint()
        w = max(size.width(), THUMNAIL_SIZE)
        h = max(size.height(), THUMNAIL_SIZE)
        self.setFixedSize(QSize(w, h))
        self.setFrameShape(QtWidgets.QFrame.Box)


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



# TODO: What if gallery is closed and reopened before all tasks finish?
#       In this case new (duplicate) tasks are queued.
class ThumbnailTask(QRunnable,):
    def __init__(self, file):
        super().__init__()
        self.file = file
        self.signals = ThumbnailTaskSignals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        img = QtGui.QImage(self.file)
        img = img.scaled(THUMNAIL_SIZE, THUMNAIL_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.signals.done.emit(self.file, img)


class ThumbnailTaskSignals(QObject):
    done = Signal(str, object)

    def __init__(self):
        super().__init__()
