import os, time
from typing_extensions import override
import numpy as np
import cv2 as cv
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRectF, QPoint, QTimer, QThreadPool, QRunnable, QObject, QMutex, QMutexLocker
from PySide6.QtGui import QColor, QPen, QPainterPath, QImage, QPixmap, QMouseEvent, QCursor, QTransform
from ui.imgview import ImgView, ImgItem
from lib import qtlib
from lib.filelist import CachedPathSort
import ui.export_settings as export
from config import Config
from .view import ViewTool


# TODO: ToolBar with SSIM/PNSR metrics, toggle for difference image


class CompareTool(ViewTool):
    OVERLAY_EXCLUDE_SIZE = 150

    def __init__(self, tab):
        super().__init__(tab)
        self._image = ClipImgItem()
        self._overlay = OverlayImageItem()

        self._toolbar = CompareToolBar(self)

        self._dividerLine = QtWidgets.QGraphicsLineItem(0, 0, 0, 0)
        self._dividerLine.setZValue(1000)
        self._dividerLine.setPen( QPen(QColor(180, 180, 180, 140)) )
        self._dividerLine.setVisible(False)

        self._overlayUpdateTimer = QTimer(tab, interval=200, singleShot=True)
        self._overlayUpdateTimer.timeout.connect(self.updateOverlay)

        self._overlayExportPath = ""


    def loadCompareImage(self, path: str):
        self._image.loadImage(path)
        self._image.updateClip(self._imgview)
        self._toolbar.chkAutoVae.setChecked(False)

        self.updateOverlay()

    def setCompareImage(self, image: QImage):
        self._image.filepath = ""
        self._image.setPixmap(QPixmap(image))
        self._image.updateClip(self._imgview)

        self.updateOverlay()


    def onFileChanged(self, currentFile: str):
        self._toolbar.vaeFileDone = ""
        if self._toolbar.chkAutoVae.isChecked():
            self._toolbar.vaeEncode(force=True)

        self.updateOverlay()

    def onFileListChanged(self, currentFile: str):
        self.onFileChanged(currentFile)


    @override
    def getToolbar(self):
        return self._toolbar

    @override
    def onEnabled(self, imgview):
        super().onEnabled(imgview)
        self.tab.filelist.addListener(self)

        imgview.scene().addItem(self._image)
        imgview.scene().addItem(self._overlay)
        imgview._guiScene.addItem(self._dividerLine)
        self.onResize()

        self.updateOverlay()

        if self._toolbar.chkAutoVae.isChecked():
            self._toolbar.vaeEncode()

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        self.tab.filelist.removeListener(self)

        imgview.scene().removeItem(self._image)
        imgview.scene().removeItem(self._overlay)
        imgview._guiScene.removeItem(self._dividerLine)

        self._toolbar.abortAllVaeTasks()
        self._overlay.clearImage()
        self._overlayUpdateTimer.stop()

    @override
    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._imgview.updateImageSmoothness(self._image)
        self.updateDividerLine( self._imgview.mapFromGlobal(QCursor.pos()) )

    @override
    def getDropRects(self):
        return [QRectF(0, 0, 0.5, 1), QRectF(0.5, 0, 1, 1)]

    @override
    def onDrop(self, event, zoneIndex):
        if zoneIndex == 0:
            super().onDrop(event, zoneIndex)
        else:
            path = event.mimeData().urls()[0].toLocalFile()
            self.loadCompareImage(path)

    @override
    def onGalleryRightClick(self, file: str):
        self.loadCompareImage(file)

    @override
    def onResize(self, event=None):
        rect = self._imgview.viewport().rect()
        rot  = self._imgview.rotation

        self._image.updateTransform(rect, rot)
        self._overlayUpdateTimer.start()


    @Slot()
    def updateOverlay(self):
        if not self._imgview or not self._toolbar.radioOverlayDiff.isChecked():
            self._overlay.clearImage()
            return

        pix1 = self._imgview.image.pixmap()
        pix2 = self._image.pixmap()
        if pix1.isNull() or pix2.isNull():
            self._overlay.clearImage()
            return

        intersection, mat1, mat2 = self._loadImagesIntersected()

        if min(len(mat1.shape), len(mat2.shape)) > 2:
            channels = min(mat1.shape[2], mat2.shape[2])
        else:
            channels = 1

        diff = cv.absdiff(mat1[..., :channels], mat2[..., :channels])
        diffImage = qtlib.numpyToQImage(diff)

        self._overlay.setPixmap(QPixmap(diffImage))
        self._overlay.updateOverlayTransform(intersection)
        self._overlay.setClipWidth(0)
        self._imgview.updateView()

    def _loadImagesIntersected(self) -> tuple[QRectF, np.ndarray, np.ndarray]:
        img1 = self._imgview.image
        img2 = self._image

        rect1 = img1.mapRectToScene(img1.boundingRect())
        rect2 = img2.mapRectToScene(img2.boundingRect())
        intersection = rect1.intersected(rect2)

        rect1 = img1.mapRectFromScene(intersection).toRect()
        rect2 = img2.mapRectFromScene(intersection).toRect()

        mat1 = qtlib.qimageToNumpy(img1.pixmap().copy(rect1).toImage())
        mat2 = qtlib.qimageToNumpy(img2.pixmap().copy(rect2).toImage())

        h1, w1 = mat1.shape[:2]
        h2, w2 = mat2.shape[:2]
        if h1 != h2 or w1 != w2:
            if h1*w1 > h2*w2:
                mat1 = cv.resize(mat1, (w2, h2), interpolation=cv.INTER_AREA)
            else:
                mat2 = cv.resize(mat2, (w1, h1), interpolation=cv.INTER_AREA)

        return intersection, mat1, mat2

    @Slot()
    def exportOverlay(self):
        pixmap = self._overlay.pixmap()
        if pixmap.isNull():
            return

        path = self.tab.filelist.getCurrentFile()
        if not path:
            return

        filename = os.path.basename(path)
        filename, ext = os.path.splitext(filename)
        filename += "_diff" + ext

        path = self._overlayExportPath or os.path.dirname(path)
        path = os.path.join(path, filename)

        path, filter = QtWidgets.QFileDialog.getSaveFileName(self.tab, "Choose target file", path, export.ExportWidget.FILE_FILTER)
        if path:
            try:
                mat = qtlib.qimageToNumpy(pixmap.toImage())
                export.saveImage(path, mat)
                self._overlayExportPath = os.path.dirname(path)

                message = f"Saved overlay to: {path}"
                print(message)
                self.tab.statusBar().showColoredMessage(message, True)
            except Exception as ex:
                self.tab.statusBar().showColoredMessage(f"Export failed: {ex}", False, 0)


    # ===== Divider Line =====
    def updateDividerLine(self, p: QPoint):
        x = p.x()

        imgX = self._image.mapFromParent( self._imgview.mapToScene(x, 0) ).x()
        self._image.setClipWidth(imgX)

        left  = x - self.OVERLAY_EXCLUDE_SIZE
        right = x + self.OVERLAY_EXCLUDE_SIZE
        overlayLeft  = self._overlay.mapFromParent( self._imgview.mapToScene(left, 0) ).x()
        overlayRight = self._overlay.mapFromParent( self._imgview.mapToScene(right, 0) ).x()
        self._overlay.setClipExclude(overlayLeft, overlayRight)

        h = self._imgview.viewport().height()
        self._dividerLine.setLine(x, 0, x, h)

    def onMouseMove(self, event: QMouseEvent):
        super().onMouseMove(event)
        self.updateDividerLine(event.position().toPoint())

    def onMouseEnter(self, event):
        if not self._image.pixmap().isNull():
            self._dividerLine.setVisible(True)

    def onMouseLeave(self, event):
        self._image.setClipEmpty()
        self._overlay.setClipWidth(0)
        self._dividerLine.setVisible(False)



class ClipImgItem(ImgItem):
    def __init__(self):
        super().__init__()
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemClipsToShape, True)
        self._clipPath = QPainterPath()

    def setClipWidth(self, x: float):
        w = self.pixmap().width()
        h = self.pixmap().height()
        self._clipPath.clear()
        self._clipPath.addRect(x, 0, w-x+1, h)
        self.update()

    def setClipEmpty(self):
        self._clipPath.clear()
        self.update()

    def shape(self) -> QPainterPath:
        return self._clipPath

    def updateClip(self, imgview: ImgView):
        if imgview:
            self.updateTransform(imgview.viewport().rect(), imgview.rotation)
            self.setClipWidth(0)
            imgview.updateView()


class OverlayImageItem(ClipImgItem):
    def __init__(self):
        super().__init__()
        self.intersection: QRectF = QRectF()

    def setClipExclude(self, left: float, right: float):
        w = self.pixmap().width()
        h = self.pixmap().height()

        self._clipPath.clear()
        self._clipPath.addRect(0, 0, w, h)
        self._clipPath.addRect(left, 0, right-left, h)
        self.update()

    def updateOverlayTransform(self, intersection: QRectF):
        if self.pixmap().isNull():
            return

        scale = intersection.height() / self.pixmap().height()
        transform = QTransform().translate(intersection.x(), intersection.y())
        transform = transform.scale(scale, scale)
        self.setTransform(transform)



class CompareToolBar(QtWidgets.QToolBar):
    def __init__(self, compareTool: CompareTool):
        super().__init__("Compare")
        self.compareTool = compareTool

        self._threadPool: QThreadPool | None = None
        self._tasks: dict[str, VaeRoundtripTask] = dict()

        self.vaeFileDone: str = ""

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildOverlayGroup())
        layout.addWidget(self._buildVaeGroup())

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setFixedWidth(180)


    def _buildOverlayGroup(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        self.radioOverlayNone = QtWidgets.QRadioButton("None")
        self.radioOverlayNone.setChecked(True)
        layout.addWidget(self.radioOverlayNone)

        self.radioOverlayDiff = QtWidgets.QRadioButton("Difference")
        self.radioOverlayDiff.toggled.connect(self._onOverlayChanged)
        layout.addWidget(self.radioOverlayDiff)

        self.btnExportOverlay = QtWidgets.QPushButton("Export Overlay...")
        self.btnExportOverlay.clicked.connect(self.compareTool.exportOverlay)
        self.btnExportOverlay.setEnabled(False)
        layout.addWidget(self.btnExportOverlay)

        group = QtWidgets.QGroupBox("Overlay")
        group.setLayout(layout)
        return group

    @Slot()
    def _onOverlayChanged(self):
        self.btnExportOverlay.setEnabled(not self.radioOverlayNone.isChecked())
        self.compareTool.updateOverlay()


    def _buildVaeGroup(self):
        layout = QtWidgets.QGridLayout()
        layout.setVerticalSpacing(2)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        row = 0
        self.cboVaeType = QtWidgets.QComboBox()
        for vaeType in self._loadVaeTypes():
            self.cboVaeType.addItem(vaeType)

        vaeTypeIndex = max(self.cboVaeType.findText(Config.compareVaeType), 0)
        self.cboVaeType.setCurrentIndex(vaeTypeIndex)

        self.cboVaeType.currentTextChanged.connect(self._onVaeTypeChanged)
        layout.addWidget(QtWidgets.QLabel("Type:"), row, 0)
        layout.addWidget(self.cboVaeType, row, 1)

        row += 1
        self.txtVaePath = QtWidgets.QLineEdit(Config.compareVaePath)
        self.txtVaePath.setPlaceholderText("Path to VAE model")
        qtlib.setFontSize(self.txtVaePath, 0.9)
        layout.addWidget(self.txtVaePath, row, 0, 1, 2)

        row += 1
        btnChooseVae = QtWidgets.QPushButton("Choose VAE...")
        btnChooseVae.setMaximumHeight(22)
        btnChooseVae.clicked.connect(self._chooseVae)
        layout.addWidget(btnChooseVae, row, 0, 1, 2)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        btnVae = QtWidgets.QPushButton("Process")
        btnVae.clicked.connect(lambda: self.vaeEncode(force=True))
        layout.addWidget(btnVae, row, 0, 1, 2)

        row += 1
        self.chkAutoVae = QtWidgets.QCheckBox("Auto Process")
        self.chkAutoVae.toggled.connect(self._onAutoVaeToggled)
        layout.addWidget(self.chkAutoVae, row, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

        group = QtWidgets.QGroupBox("VAE Encode/Decode")
        group.setLayout(layout)
        return group

    def _loadVaeTypes(self) -> list[str]:
        folder = Config.pathVaeConfig
        entries = list[str]()

        for (root, dirs, files) in os.walk(folder, topdown=True, followlinks=True):
            for file in filter(lambda file: file.endswith(".json"), files):
                filePath = os.path.join(root, file)
                name, ext = os.path.splitext( os.path.relpath(filePath, folder) )
                entries.append(name)

        entries.sort(key=CachedPathSort())
        return entries

    @Slot()
    def _chooseVae(self):
        path = self.txtVaePath.text() or Config.pathExport
        fileFilter = "Model File (*.safetensors *.ckpt)"

        path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Select VAE Model", path, fileFilter)
        if path:
            self.txtVaePath.setText(path)
            Config.compareVaePath = path

    @Slot()
    def _onVaeTypeChanged(self, vaeType: str):
        Config.compareVaeType = vaeType

    @Slot()
    def _onAutoVaeToggled(self, state: bool):
        if state:
            self.vaeEncode()

    def abortAllVaeTasks(self):
        for task in self._tasks.values():
            task.abort()

    def vaeEncode(self, force: bool = False):
        file = self.compareTool.tab.filelist.getCurrentFile()
        if not force and file == self.vaeFileDone:
            return

        task = self._tasks.get(file)
        if task and not task.isAborted():
            return

        self.abortAllVaeTasks()
        self._tasks = {}

        vaePath = self.txtVaePath.text()
        vaeType = self.cboVaeType.currentText()

        if not (file and vaePath):
            return

        task = VaeRoundtripTask(vaePath, vaeType, file)
        task.signals.loaded.connect(self._onVaeLoaded, Qt.ConnectionType.QueuedConnection)
        task.signals.done.connect(self._onVaeDone, Qt.ConnectionType.BlockingQueuedConnection)
        task.signals.fail.connect(self._onVaeFail, Qt.ConnectionType.BlockingQueuedConnection)

        self._tasks[file] = task
        self.compareTool.tab.statusBar().showMessage("Loading VAE...", 0)
        self.vaeFileDone = ""

        if self._threadPool is None:
            self._threadPool = QThreadPool(self, maxThreadCount=1)
        self._threadPool.start(task)

    @Slot()
    def _onVaeLoaded(self):
        self.compareTool.tab.statusBar().showMessage("VAE processing...", 0)

    @Slot(QImage)
    def _onVaeDone(self, file: str, image: QImage, duration: float):
        self.vaeFileDone = file
        self._tasks.pop(file, None)

        self.compareTool.setCompareImage(image)
        self.compareTool.tab.statusBar().showColoredMessage(f"VAE processing finished in {duration:.0f} ms", True)

    @Slot(str)
    def _onVaeFail(self, file: str, msg: str):
        self._tasks.pop(file, None)

        msg = f"VAE processing failed: {msg}"
        self.compareTool.tab.statusBar().showColoredMessage(msg, False, 0)
        print(msg)



class VaeRoundtripTask(QRunnable):
    class Signals(QObject):
        loaded = Signal()
        done = Signal(str, QImage, float)  # file, QImage, time [ms]
        fail = Signal(str, str)            # file, message

    def __init__(self, vaePath: str, vaeType: str, imgPath: str):
        super().__init__()
        self.setAutoDelete(True)

        self.signals = self.Signals()
        self.vaePath = vaePath
        self.vaeType = vaeType
        self.imgPath = imgPath

        self._mutex = QMutex()
        self._aborted = False


    def abort(self):
        with QMutexLocker(self._mutex):
            self._aborted = True

    def isAborted(self) -> bool:
        with QMutexLocker(self._mutex):
            return self._aborted


    @Slot()
    def run(self):
        if self.isAborted():
            self.signals.fail.emit(self.imgPath, "Aborted")
            return

        from infer.inference import Inference, InferenceProcess
        t = 0

        def prepare(proc: InferenceProcess):
            proc.setupVae({
                "backend": "vae",
                "model_path": self.vaePath,
                "vae_type": self.vaeType
            })

        def prepareCb():
            self.signals.loaded.emit()
            nonlocal t
            t = time.monotonic_ns()

        def check(file: str, proc: InferenceProcess):
            return lambda: proc.vaeRoundtrip(file)

        try:
            with Inference().createSession(1) as session:
                session.prepare(prepare, prepareCb)

                for file, results, exception in session.queueFiles((self.imgPath,), check):
                    if exception:
                        raise exception

                    t = (time.monotonic_ns() - t) / 1_000_000

                    answer: dict = results[0]
                    w = answer["w"]
                    h = answer["h"]
                    imgData = answer["img"]

                    channels = len(imgData) // (w*h)
                    mat = np.frombuffer(imgData, dtype=np.uint8)
                    mat.shape = (h, w, channels)

                    image = qtlib.numpyToQImage(mat, fromRGB=True)
                    self.signals.done.emit(self.imgPath, image, t)
                    return

            raise RuntimeError("No result")

        except Exception as ex:
            import traceback
            traceback.print_exc()
            self.signals.fail.emit(self.imgPath, str(ex))
