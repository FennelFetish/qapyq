import os
from PySide6.QtCore import Slot, Signal, QSize, QThreadPool, QObject, QRunnable, Qt
from PySide6.QtGui import QPixmap, QImageReader
from lib.filelist import FileList, DataKeys
from config import Config
import time


class ThumbnailCache:
    THUMBNAIL_SIZE = Config.galleryThumbnailSize
    REQUEST_TIMEOUT = 1000 * 1000000

    @classmethod
    def updateThumbnail(cls, filelist: FileList, target, file):
        if pixmap := filelist.getData(file, DataKeys.Thumbnail):
            target.pixmap = pixmap
            return

        # Throttle requests to prevent unnecessary I/O and congestion of thread pool.
        requestTime = filelist.getData(file, DataKeys.ThumbnailRequestTime)
        now = time.monotonic_ns()
        if requestTime and requestTime+cls.REQUEST_TIMEOUT > now:
            return
        filelist.setData(file, DataKeys.ThumbnailRequestTime, now, False)

        task = ThumbnailTask(filelist, target, file)
        task.signals.done.connect(cls._onThumbnailLoaded, Qt.ConnectionType.BlockingQueuedConnection)
        QThreadPool.globalInstance().start(task)

    @Slot()
    @staticmethod
    def _onThumbnailLoaded(filelist: FileList, target, file: str, img, imgSize: tuple[int, int], icons: dict):
        pixmap = QPixmap.fromImage(img)
        filelist.setData(file, DataKeys.Thumbnail, pixmap)
        filelist.setData(file, DataKeys.ImageSize, imgSize)
        filelist.removeData(file, DataKeys.ThumbnailRequestTime, False)
        target.pixmap = pixmap

        for key, state in icons.items():
            if state:
                filelist.setData(file, key, state)



class ThumbnailTask(QRunnable):
    class Signals(QObject):
        done = Signal(object, object, str, object, tuple, dict)

    def __init__(self, filelist, target, file):
        super().__init__()
        self.filelist = filelist
        self.target = target
        self.file = file
        self.signals = self.Signals()

        iconKeys = (DataKeys.CaptionState, DataKeys.CropState, DataKeys.MaskState)
        self.icons = { k: filelist.getData(file, k) for k in iconKeys }

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
        self.checkIcons()
        self.signals.done.emit(self.filelist, self.target, self.file, img, imgSize.toTuple(), self.icons)

    def checkIcons(self):
        filenameNoExt = os.path.splitext(self.file)[0]

        if self.icons[DataKeys.CaptionState] is None:
            captionFile = filenameNoExt + ".txt"
            jsonFile    = filenameNoExt + ".json"
            if os.path.exists(captionFile) or os.path.exists(jsonFile):
                self.icons[DataKeys.CaptionState] = DataKeys.IconStates.Exists

        if self.icons[DataKeys.MaskState] is None:
            maskFile = f"{filenameNoExt}{Config.maskSuffix}.png"
            if os.path.exists(maskFile):
                self.icons[DataKeys.MaskState] = DataKeys.IconStates.Exists
