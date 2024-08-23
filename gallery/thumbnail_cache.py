from PySide6.QtCore import Qt, Slot, Signal, QThreadPool, QObject, QRunnable
from PySide6.QtGui import QPixmap, QImage


class ThumbnailCache:
    THUMBNAIL_SIZE = 256

    thumbnails = {}

    @classmethod
    def updateThumbnail(cls, target, file):
        if file in cls.thumbnails:
            target.pixmap = cls.thumbnails[file]

        task = ThumbnailTask(target, file)
        task.signals.done.connect(cls._onThumbnailLoaded)
        QThreadPool.globalInstance().start(task)

    @classmethod
    def _onThumbnailLoaded(cls, target, file, img):
        pixmap = QPixmap.fromImage(img)
        cls.thumbnails[file] = pixmap
        target.pixmap = pixmap


class ThumbnailTask(QRunnable):
    def __init__(self, target, file):
        super().__init__()
        self.target = target
        self.file = file
        self.signals = ThumbnailTaskSignals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        size = ThumbnailCache.THUMBNAIL_SIZE + 20
        img = QImage(self.file)
        img = img.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.signals.done.emit(self.target, self.file, img)


class ThumbnailTaskSignals(QObject):
    done = Signal(object, str, object)

    def __init__(self):
        super().__init__()
