from PySide6.QtCore import Slot, Signal, QSize, QThreadPool, QObject, QRunnable
from PySide6.QtGui import QPixmap, QImageReader
from filelist import DataKeys
from config import Config
import time


class ThumbnailCache:
    THUMBNAIL_SIZE = Config.galleryThumbnailSize
    REQUEST_TIMEOUT = 1000 * 1000000

    @classmethod
    def updateThumbnail(cls, filelist, target, file):
        if pixmap := filelist.getData(file, DataKeys.Thumbnail):
            target.pixmap = pixmap
            return

        # FIXME: Sometimes the images aren't loaded or applied to the gallery items. Why?
        # More requests are queued while the items are painted, congesting the thread pool and causing unnecessary I/O.
        # As a workaround, the request time is stored here. This will throttle the requests,
        # but some thumbnails may be missing initially until another paint event is received.
        requestTime = filelist.getData(file, DataKeys.ThumbnailRequestTime)
        now = time.monotonic_ns()
        if requestTime and requestTime+cls.REQUEST_TIMEOUT > now:
            return
        filelist.setData(file, DataKeys.ThumbnailRequestTime, now, False)

        task = ThumbnailTask(filelist, target, file)
        task.signals.done.connect(cls._onThumbnailLoaded)
        QThreadPool.globalInstance().start(task)

    @staticmethod
    def _onThumbnailLoaded(filelist, target, file, img):
        pixmap = QPixmap.fromImage(img)
        filelist.setData(file, DataKeys.Thumbnail, pixmap)
        filelist.removeData(file, DataKeys.ThumbnailRequestTime, False)
        target.pixmap = pixmap
        del img



class ThumbnailTask(QRunnable):
    class Signals(QObject):
        done = Signal(object, object, str, object)

    def __init__(self, filelist, target, file):
        super().__init__()
        self.filelist = filelist
        self.target = target
        self.file = file
        self.signals = ThumbnailTask.Signals()

    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        reader = QImageReader(self.file)
        reader.setQuality(100)
        imgSize = reader.size()

        targetWidth = int(ThumbnailCache.THUMBNAIL_SIZE * 1.25)
        targetHeight = targetWidth * (imgSize.height() / imgSize.width())
        targetHeight = int(targetHeight + 0.5)
        reader.setScaledSize(QSize(targetWidth, targetHeight))

        img = reader.read()
        self.signals.done.emit(self.filelist, self.target, self.file, img)
