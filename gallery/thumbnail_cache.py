import os, time
from PySide6.QtCore import Slot, Signal, QThreadPool, QObject, QRunnable, Qt
from PySide6.QtGui import QPixmap, QImage
from lib.filelist import FileList, DataKeys
import lib.imagerw as imagerw
from config import Config
from .gallery_item import GalleryItem


class ThumbnailCache:
    THUMBNAIL_SIZE = 300
    REQUEST_TIMEOUT = 1000 * 1000000

    THREAD_POOL = QThreadPool()
    THREAD_POOL.setMaxThreadCount(Config.galleryThumbnailThreads)

    _active = True

    @classmethod
    def updateThumbnail(cls, filelist: FileList, target: GalleryItem, file: str):
        if pixmap := filelist.getData(file, DataKeys.Thumbnail):
            target.pixmap = pixmap
            return

        if not cls._active:
            return

        # Throttle requests to prevent unnecessary I/O and congestion of thread pool.
        requestTime = filelist.getData(file, DataKeys.ThumbnailRequestTime)
        now = time.monotonic_ns()
        if requestTime and requestTime+cls.REQUEST_TIMEOUT > now:
            return
        filelist.setData(file, DataKeys.ThumbnailRequestTime, now, False)

        task = ThumbnailTask(filelist, target, file)
        task.signals.done.connect(cls._onThumbnailLoaded, Qt.ConnectionType.BlockingQueuedConnection)
        cls.THREAD_POOL.start(task)

    @Slot()
    @staticmethod
    def _onThumbnailLoaded(filelist: FileList, target: GalleryItem, file: str, img: QImage, imgSize: tuple[int, int], icons: dict):
        pixmap = QPixmap.fromImage(img)

        try:
            target.pixmap = pixmap
        except RuntimeError as ex:
            if ex.args[0].endswith("already deleted."):
                return
            else:
                raise

        filelist.setData(file, DataKeys.Thumbnail, pixmap)
        filelist.setData(file, DataKeys.ImageSize, imgSize)
        filelist.removeData(file, DataKeys.ThumbnailRequestTime, False)

        for key, state in icons.items():
            if state:
                filelist.setData(file, key, state)

    @classmethod
    def shutdown(cls):
        cls._active = False
        cls.THREAD_POOL.clear()



class ThumbnailTask(QRunnable):
    class Signals(QObject):
        done = Signal(object, object, str, object, tuple, dict)

    ICON_KEYS = (DataKeys.CaptionState, DataKeys.MaskState)

    def __init__(self, filelist: FileList, target: GalleryItem, file: str):
        super().__init__()
        self.setAutoDelete(True)

        self.filelist = filelist
        self.target = target
        self.file = file
        self.signals = self.Signals()

        self.icons = { k: filelist.getData(file, k) for k in self.ICON_KEYS }


    @Slot()
    def run(self):
        # QPixmap is not threadsafe, loading as QImage instead
        try:
            img, (w, h) = imagerw.thumbnailQImage(self.file, ThumbnailCache.THUMBNAIL_SIZE)
        except Exception as ex:
            print(f"Couldn't load thumbnail: {ex} ({type(ex).__name__})")
            img = QImage()
            w = h = -1

        self.checkIcons()

        try:
            self.signals.done.emit(self.filelist, self.target, self.file, img, (w, h), self.icons)
        except RuntimeError as ex:
            if ex.args[0] != "Signal source has been deleted":
                raise

    def checkIcons(self):
        filenameNoExt = os.path.splitext(self.file)[0]

        if self.icons[DataKeys.CaptionState] is None:
            captionFile = filenameNoExt + ".txt"
            jsonFile    = filenameNoExt + ".json"
            if self._fileExists(captionFile) or self._fileExists(jsonFile):
                self.icons[DataKeys.CaptionState] = DataKeys.IconStates.Exists

        if self.icons[DataKeys.MaskState] is None:
            maskFile = f"{filenameNoExt}{Config.maskSuffix}.png"
            if os.path.exists(maskFile):
                self.icons[DataKeys.MaskState] = DataKeys.IconStates.Exists

    @staticmethod
    def _fileExists(path: str) -> bool:
        try:
            return os.path.getsize(path) > 0
        except FileNotFoundError:
            return False
