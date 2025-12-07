import os, time
from PySide6.QtCore import Slot, Signal, QThreadPool, QObject, QRunnable, Qt
from PySide6.QtGui import QPixmap, QImage
from lib.filelist import DataKeys
import lib.imagerw as imagerw
from config import Config
from .gallery_model import GalleryModel



class ThumbnailCache(QObject):
    THUMBNAIL_SIZE = 300
    REQUEST_TIMEOUT = 1000 * 1000000

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ThumbnailCache, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, '_singleton_initialized', False):
            return

        super().__init__()
        self._singleton_initialized = True

        self._active = True

        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(Config.galleryThumbnailThreads)

    def shutdown(self):
        self._active = False
        self.threadpool.clear()


    def updateThumbnail(self, model: GalleryModel, file: str):
        if not self._active:
            return

        # Throttle requests to prevent unnecessary I/O and congestion of thread pool.
        requestTime = model.filelist.getData(file, DataKeys.ThumbnailRequestTime)
        now = time.monotonic_ns()
        if requestTime and requestTime+self.REQUEST_TIMEOUT > now:
            return
        model.filelist.setData(file, DataKeys.ThumbnailRequestTime, now, False)

        task = ThumbnailTask(model, file)
        task.signals.done.connect(self._onThumbnailLoaded, Qt.ConnectionType.QueuedConnection)
        self.threadpool.start(task)


    @Slot(object, str, object, object, dict)
    def _onThumbnailLoaded(self, model: GalleryModel, file: str, img: QImage, imgSize: tuple[int, int], icons: dict):
        pixmap = QPixmap.fromImage(img)

        filelist = model.filelist
        filelist.setData(file, DataKeys.Thumbnail, pixmap, False)
        filelist.setData(file, DataKeys.ImageSize, imgSize, False)
        filelist.removeData(file, DataKeys.ThumbnailRequestTime, False)

        for key, state in icons.items():
            if state:
                filelist.setData(file, key, state)

        model.onThumbnailLoaded(file)



class ThumbnailTask(QRunnable):
    class Signals(QObject):
        done = Signal(object, str, object, tuple, dict)

    ICON_KEYS = (DataKeys.CaptionState, DataKeys.MaskState)

    def __init__(self, model: GalleryModel, file: str):
        super().__init__()
        self.setAutoDelete(True)

        self.model = model
        self.file = file
        self.signals = self.Signals()

        self.icons = { k: model.filelist.getData(file, k) for k in self.ICON_KEYS }


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
        self.signals.done.emit(self.model, self.file, img, (w, h), self.icons)

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
