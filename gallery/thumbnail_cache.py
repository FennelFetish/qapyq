from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QObject, QRunnable
from PySide6.QtGui import QPixmap, QImage


class ThumbnailCache:
    THUMBNAIL_SIZE = 256

    thumbnails = {}

    @classmethod
    def updateThumbnail(cls, label, file):
        if file in cls.thumbnails:
            label.setPixmap(cls.thumbnails[file])

        task = ThumbnailTask(label, file)
        task.signals.done.connect(cls._onThumbnailLoaded)
        QThreadPool.globalInstance().start(task)

    @classmethod
    def _onThumbnailLoaded(cls, label, file, img):
        pixmap = QPixmap.fromImage(img)
        cls.thumbnails[file] = pixmap
        label.setPixmap(pixmap)



# TODO: What if gallery is closed and reopened before all tasks finish?
#       In this case new (duplicate) tasks are queued.
class ThumbnailTask(QRunnable):
    def __init__(self, label, file):
        super().__init__()
        self.label = label
        self.file = file
        self.signals = ThumbnailTaskSignals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        size = ThumbnailCache.THUMBNAIL_SIZE + 20
        img = QImage(self.file)
        img = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.signals.done.emit(self.label, self.file, img)


class ThumbnailTaskSignals(QObject):
    done = Signal(object, str, object)

    def __init__(self):
        super().__init__()
