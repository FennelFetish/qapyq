from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QObject, QRunnable
from PySide6.QtGui import QPixmap, QImage
from filelist import DataKeys


class ThumbnailCache:
    THUMBNAIL_SIZE = 196

    @classmethod
    def updateThumbnail(cls, filelist, target, file):
        if pixmap := filelist.getData(file, DataKeys.Thumbnail):
            target.pixmap = pixmap
            return

        task = ThumbnailTask(filelist, target, file)
        task.signals.done.connect(cls._onThumbnailLoaded)
        QThreadPool.globalInstance().start(task)

    @classmethod
    def _onThumbnailLoaded(cls, filelist, target, file, img):
        pixmap = QPixmap.fromImage(img)
        filelist.setData(file, DataKeys.Thumbnail, pixmap)
        target.pixmap = pixmap


class ThumbnailTask(QRunnable):
    def __init__(self, filelist, target, file):
        super().__init__()
        self.filelist = filelist
        self.target = target
        self.file = file
        self.signals = ThumbnailTaskSignals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        size = ThumbnailCache.THUMBNAIL_SIZE
        img = QImage(self.file)
        img = img.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.signals.done.emit(self.filelist, self.target, self.file, img)


class ThumbnailTaskSignals(QObject):
    done = Signal(object, object, str, object)

    def __init__(self):
        super().__init__()
