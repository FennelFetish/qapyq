import os, time
from typing_extensions import override
import numpy as np
import cv2 as cv
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QRect, QRectF, QPoint, QTimer, QThreadPool, QRunnable, QObject, QMutex, QMutexLocker
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
        self._toolbar.vae.autoProcess = False

        self.updateOverlay()
        self._toolbar.updateInfo(self._image)

    def setCompareImage(self, image: QImage):
        self._image.filepath = ""
        self._image.setPixmap(QPixmap(image))
        self._image.updateClip(self._imgview)

        self.updateOverlay()
        self._toolbar.updateInfo(self._image)


    def onFileChanged(self, currentFile: str):
        vaeBox = self._toolbar.vae
        vaeBox.fileDone = ""
        if vaeBox.autoProcess:
            vaeBox.vaeProcess(force=True)

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

        if self._toolbar.vae.autoProcess:
            self._toolbar.vae.vaeProcess()

    @override
    def onDisabled(self, imgview):
        super().onDisabled(imgview)
        self.tab.filelist.removeListener(self)

        imgview.scene().removeItem(self._image)
        imgview.scene().removeItem(self._overlay)
        imgview._guiScene.removeItem(self._dividerLine)

        self._toolbar.vae.abortAllTasks()
        self._overlay.clearImage()
        self._overlayUpdateTimer.stop()

    @override
    def onSceneUpdate(self):
        super().onSceneUpdate()
        self._imgview.updateImageSmoothness(self._image)
        self._imgview.updateImageSmoothness(self._overlay)
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

        rect1 = self._roundRect(img1.mapRectFromScene(intersection))
        rect2 = self._roundRect(img2.mapRectFromScene(intersection))

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

    @staticmethod
    def _roundRect(rect: QRectF) -> QRect:
        x = round(rect.x())
        y = round(rect.y())
        w = round(rect.right() - x)
        h = round(rect.bottom() - y)
        return QRect(x, y, w, h)


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

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildInfoGroup())
        layout.addWidget(self._buildOverlayGroup())

        self.vae = VaeGroupBox(compareTool)
        layout.addWidget(self.vae)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMinimumWidth(180)


    def _buildInfoGroup(self):
        fileLayout = QtWidgets.QVBoxLayout()
        fileLayout.setContentsMargins(0, 0, 0, 0)
        fileLayout.setSpacing(2)

        self.txtFile = QtWidgets.QLineEdit()
        self.txtFile.setReadOnly(True)
        qtlib.setFontSize(self.txtFile, 0.9)
        fileLayout.addWidget(self.txtFile)

        btnChooseFile = QtWidgets.QPushButton("Choose File...")
        btnChooseFile.setMaximumHeight(22)
        btnChooseFile.clicked.connect(self._chooseCompareFile)
        fileLayout.addWidget(btnChooseFile)

        gridLayout = QtWidgets.QGridLayout()
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setColumnStretch(1, 1)

        row = 0
        self.lblSize = QtWidgets.QLabel()
        self.lblSize.setTextFormat(Qt.TextFormat.PlainText)
        self.lblSize.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        gridLayout.addWidget(QtWidgets.QLabel("Size:"), row, 0)
        gridLayout.addWidget(self.lblSize, row, 1)

        row += 1
        self.lblAspect = QtWidgets.QLabel()
        self.lblAspect.setTextFormat(Qt.TextFormat.PlainText)
        self.lblAspect.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        gridLayout.addWidget(QtWidgets.QLabel("AR:"), row, 0)
        gridLayout.addWidget(self.lblAspect, row, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(8)
        layout.addLayout(fileLayout)
        layout.addLayout(gridLayout)

        group = QtWidgets.QGroupBox("Comparing to")
        group.setLayout(layout)
        return group

    @Slot()
    def _chooseCompareFile(self):
        path = self.compareTool._image.filepath or Config.pathExport
        path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Select Image", path, export.ExportWidget.FILE_FILTER)
        if path:
            self.compareTool.loadCompareImage(path)

    def updateInfo(self, image: ClipImgItem):
        if image.pixmap().isNull():
            self.txtFile.clear()
            self.lblSize.clear()
            self.lblAspect.clear()
            return

        if image.filepath:
            self.txtFile.setText(image.filepath)
        else:
            self.txtFile.setText(os.path.basename(self.compareTool._toolbar.vae.fileDone) + " [VAE]")

        w, h = image.pixmap().size().toTuple()
        self.lblSize.setText(f"{w}x{h}")

        if min(w, h) > 0:
            aspect = w / h
            aspectText = f"{aspect:.3f}" if aspect >= 1 else f"{aspect:.3f}  (1:{1/aspect:.3f})"
            self.lblAspect.setText(aspectText)
        else:
            self.lblAspect.clear()


    def _buildOverlayGroup(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(2)

        self.radioOverlayNone = QtWidgets.QRadioButton("None")
        self.radioOverlayNone.setChecked(True)
        layout.addWidget(self.radioOverlayNone)

        self.radioOverlayDiff = QtWidgets.QRadioButton("Difference")
        self.radioOverlayDiff.toggled.connect(self._onOverlayChanged)
        layout.addWidget(self.radioOverlayDiff)

        layout.addSpacing(4)

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



class VaeGroupBox(QtWidgets.QGroupBox):
    def __init__(self, compareTool: CompareTool):
        super().__init__("VAE Encode/Decode")
        self.compareTool = compareTool
        self.fileDone: str = ""

        self._threadPool: QThreadPool | None = None
        self._tasks: dict[str, VaeRoundtripTask] = dict()

        self.setLayout(self._build())


    def _build(self):
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
        btnChooseModel = QtWidgets.QPushButton("Choose VAE...")
        btnChooseModel.setMaximumHeight(22)
        btnChooseModel.clicked.connect(self._chooseModel)
        layout.addWidget(btnChooseModel, row, 0, 1, 2)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        btnProcess = QtWidgets.QPushButton("Process")
        btnProcess.clicked.connect(lambda: self.vaeProcess(force=True))
        layout.addWidget(btnProcess, row, 0, 1, 2)

        row += 1
        self.chkAutoProcess = QtWidgets.QCheckBox("Auto Process")
        self.chkAutoProcess.toggled.connect(self._onAutoProcessToggled)
        layout.addWidget(self.chkAutoProcess, row, 0, 1, 2, Qt.AlignmentFlag.AlignCenter)

        return layout


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
    def _onVaeTypeChanged(self, vaeType: str):
        Config.compareVaeType = vaeType

    @Slot()
    def _chooseModel(self):
        path = self.txtVaePath.text() or Config.pathExport
        fileFilter = "Model File (*.safetensors *.ckpt)"

        path, filter = QtWidgets.QFileDialog.getOpenFileName(self, "Select VAE Model", path, fileFilter)
        if path:
            self.txtVaePath.setText(path)
            Config.compareVaePath = path


    @property
    def autoProcess(self) -> bool:
        return self.chkAutoProcess.isChecked()

    @autoProcess.setter
    def autoProcess(self, value: bool):
        self.chkAutoProcess.setChecked(value)

    @Slot()
    def _onAutoProcessToggled(self, state: bool):
        if state:
            self.vaeProcess()


    def abortAllTasks(self):
        for task in self._tasks.values():
            task.abort()

    def vaeProcess(self, force: bool = False):
        file = self.compareTool.tab.filelist.getCurrentFile()
        if not force and file == self.fileDone:
            return

        task = self._tasks.get(file)
        if task and not task.isAborted():
            return

        self.abortAllTasks()
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
        self.fileDone = ""

        if self._threadPool is None:
            self._threadPool = QThreadPool(self, maxThreadCount=1)
        self._threadPool.start(task)

    @Slot()
    def _onVaeLoaded(self):
        self.compareTool.tab.statusBar().showMessage("VAE processing...", 0)

    @Slot(QImage)
    def _onVaeDone(self, file: str, image: QImage, duration: float):
        self.fileDone = file
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
