from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import superqt
import cv2 as cv
import qtlib
from config import Config


INTERP_MODES = {
    "Nearest": cv.INTER_NEAREST,
    "Linear":  cv.INTER_LINEAR,
    "Cubic":   cv.INTER_CUBIC,
    "Area":    cv.INTER_AREA,
    "Lanczos": cv.INTER_LANCZOS4
}

SAVE_PARAMS = {
    "PNG":  [cv.IMWRITE_PNG_COMPRESSION, 9],
    "JPG":  [cv.IMWRITE_JPEG_QUALITY, 100],
    "WEBP": [cv.IMWRITE_WEBP_QUALITY, 100]
}


class CropToolBar(QtWidgets.QToolBar):
    def __init__(self, cropTool):
        super().__init__("Crop")
        self._cropTool = cropTool

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildSelectionSize())
        layout.addWidget(self._buildRotation())
        layout.addWidget(self._buildExport())

        self.txtPathSample = QtWidgets.QPlainTextEdit()
        self.txtPathSample.setReadOnly(True)
        qtlib.setMonospace(self.txtPathSample, 0.9)
        layout.addWidget(self.txtPathSample)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        act = self.addWidget(widget)

        self.setMaximumWidth(180)


    def _buildTargetSize(self):
        self.spinW = QtWidgets.QSpinBox()
        self.spinW.setRange(1, 16384)
        self.spinW.setSingleStep(Config.cropSizeStep)
        self.spinW.setValue(512)
        self.spinW.valueChanged.connect(self.updateSize)

        self.spinH = QtWidgets.QSpinBox()
        self.spinH.setRange(1, 16384)
        self.spinH.setSingleStep(Config.cropSizeStep)
        self.spinH.setValue(512)
        self.spinH.valueChanged.connect(self.updateSize)

        self.lblTargetAspect = QtWidgets.QLabel()

        btnSwap = QtWidgets.QPushButton("Swap")
        btnSwap.clicked.connect(self.sizeSwap)

        btnQuad = QtWidgets.QPushButton("Quad")
        btnQuad.clicked.connect(self.sizeQuad)

        self.cboSizePresets = QtWidgets.QComboBox()
        self.cboSizePresets.addItems([""] + Config.cropSizePresets)
        self.cboSizePresets.currentTextChanged.connect(self.sizePreset)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)

        lblW = QtWidgets.QLabel("W:")
        lblW.setFixedWidth(24)
        layout.addWidget(lblW, 0, 0)
        layout.addWidget(self.spinW, 0, 1, 1, 2)

        lblH = QtWidgets.QLabel("H:")
        lblH.setFixedWidth(24)
        layout.addWidget(lblH, 1, 0)
        layout.addWidget(self.spinH, 1, 1, 1, 2)

        lblTargetAspect = QtWidgets.QLabel("AR:")
        lblTargetAspect.setFixedWidth(24)
        layout.addWidget(lblTargetAspect, 2, 0)
        layout.addWidget(self.lblTargetAspect, 2, 1, 1, 2)

        lblPreset = QtWidgets.QLabel("Pre:")
        lblPreset.setFixedWidth(24)
        layout.addWidget(lblPreset, 3, 0)
        layout.addWidget(self.cboSizePresets, 3, 1, 1, 2)

        layout.addWidget(btnSwap, 4, 1)
        layout.addWidget(btnQuad, 4, 2)

        group = QtWidgets.QGroupBox("Target Size")
        group.setLayout(layout)
        return group

    def _buildSelectionSize(self):
        self.lblW = QtWidgets.QLabel("0 px")
        self.lblH = QtWidgets.QLabel("0 px")
        self.lblScale = QtWidgets.QLabel("1.0")

        self.chkConstrainToImage = QtWidgets.QCheckBox("Constrain to Image")
        self.chkConstrainToImage.setChecked(True)

        self.chkAllowUpscale = QtWidgets.QCheckBox("Allow Upscale")
        self.chkAllowUpscale.setChecked(True)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)

        lblW = QtWidgets.QLabel("W:")
        lblW.setFixedWidth(24)
        layout.addWidget(lblW, 0, 0)
        layout.addWidget(self.lblW, 0, 1)
        layout.addWidget(self.lblScale, 0, 2)

        lblH = QtWidgets.QLabel("H:")
        lblH.setFixedWidth(24)
        layout.addWidget(lblH, 1, 0)
        layout.addWidget(self.lblH, 1, 1)

        layout.addWidget(self.chkConstrainToImage, 2, 0, 1, 3)
        layout.addWidget(self.chkAllowUpscale, 3, 0, 1, 3)

        group = QtWidgets.QGroupBox("Selection")
        group.setLayout(layout)
        return group

    def _buildRotation(self):
        self.slideRot = QtWidgets.QSlider(Qt.Horizontal)
        self.slideRot.setRange(-10, 3600)
        self.slideRot.setTickPosition(QtWidgets.QSlider.TicksAbove)
        self.slideRot.setTickInterval(900)
        self.slideRot.setSingleStep(10)
        self.slideRot.setPageStep(50)
        self.slideRot.setValue(0)
        self.slideRot.valueChanged.connect(self.updateRotationFromSlider)

        self.spinRot = QtWidgets.QDoubleSpinBox()
        self.spinRot.setRange(-360.0, 360.0)
        self.spinRot.setSingleStep(0.1)
        self.spinRot.setValue(0)
        self.spinRot.valueChanged.connect(self.updateRotationFromSpinner)

        btnDeg0 = QtWidgets.QPushButton("0")
        btnDeg0.clicked.connect(lambda: self.spinRot.setValue(0))
        btnDeg90 = QtWidgets.QPushButton("90")
        btnDeg90.clicked.connect(lambda: self.spinRot.setValue(90))
        btnDeg180 = QtWidgets.QPushButton("180")
        btnDeg180.clicked.connect(lambda: self.spinRot.setValue(180))
        btnDeg270 = QtWidgets.QPushButton("270")
        btnDeg270.clicked.connect(lambda: self.spinRot.setValue(270))

        btnLayout = QtWidgets.QHBoxLayout()
        btnLayout.addWidget(btnDeg0)
        btnLayout.addWidget(btnDeg90)
        btnLayout.addWidget(btnDeg180)
        btnLayout.addWidget(btnDeg270)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.slideRot)
        layout.addRow("Deg:", self.spinRot)
        layout.addRow(btnLayout)
        
        group = QtWidgets.QGroupBox("Rotation")
        group.setLayout(layout)
        return group

    def _buildExport(self):
        group = superqt.QCollapsible("Export Settings")
        group.layout().setContentsMargins(2, 2, 2, 0)
        group.setFrameStyle(QtWidgets.QFrame.NoFrame)
        group.setLineWidth(0)

        group.addWidget(self._buildSave())
        group.addWidget(self._buildDestination())
        return group

    def _buildSave(self):
        self.cboInterpUp = QtWidgets.QComboBox()
        self.cboInterpUp.addItems(INTERP_MODES.keys())
        self.cboInterpUp.setCurrentIndex(4) # Default: Lanczos

        self.cboInterpDown = QtWidgets.QComboBox()
        self.cboInterpDown.addItems(INTERP_MODES.keys())
        self.cboInterpDown.setCurrentIndex(3) # Default: Area

        self.cboFormat = QtWidgets.QComboBox()
        self.cboFormat.addItems(SAVE_PARAMS.keys())
        self.cboFormat.currentTextChanged.connect(self.updateExport)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow("Interp 🠕:", self.cboInterpUp)
        layout.addRow("Interp 🠗:", self.cboInterpDown)
        layout.addRow("Format:", self.cboFormat)

        group = QtWidgets.QGroupBox("Parameter")
        group.setLayout(layout)
        return group

    def _buildDestination(self):
        self.btnChoosePath = QtWidgets.QPushButton("Choose Path...")
        self.btnChoosePath.clicked.connect(self.chooseExportPath)

        self.spinFolderSkip = QtWidgets.QSpinBox()
        self.spinFolderSkip.valueChanged.connect(self.updateExport)

        self.spinFolderNames = QtWidgets.QSpinBox()
        self.spinFolderNames.valueChanged.connect(self.updateExport)

        self.spinSubfolders = QtWidgets.QSpinBox()
        self.spinSubfolders.valueChanged.connect(self.updateExport)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.btnChoosePath)
        layout.addRow("Folder Skip:", self.spinFolderSkip)
        layout.addRow("Folder Names:", self.spinFolderNames)
        layout.addRow("Subfolders:", self.spinSubfolders)

        group = QtWidgets.QGroupBox("Destination")
        group.setLayout(layout)
        return group


    @Slot()
    def updateSize(self):
        w = self.spinW.value()
        h = self.spinH.value()
        self.lblTargetAspect.setText(f"1 : {h/w:.3f}" if h>w else f"{w/h:.3f} : 1")

        self._cropTool.setTargetSize(self.spinW.value(), self.spinH.value())
        self.updateExport()

    @Slot()
    def sizeSwap(self):
        w = self.spinW.value()
        self.spinW.setValue(self.spinH.value())
        self.spinH.setValue(w)
        self.updateSize()

    @Slot()
    def sizeQuad(self):
        self.spinH.setValue( self.spinW.value() )

    def sizePreset(self, text: str):
        if not text:
            return

        w, h = text.split("x")
        self.spinW.setValue(int(w))
        self.spinH.setValue(int(h))
        
        self.updateSize()
        self.cboSizePresets.setCurrentIndex(0)
    

    @Slot()
    def updateRotationFromSlider(self, rot: int):
        self.spinRot.setValue(rot / 10.0)

    @Slot()
    def updateRotationFromSpinner(self, rot: float):
        rot = rot % 360.0
        self.slideRot.setValue(int(rot*10))
        self._cropTool._imgview.rotation = rot
        self._cropTool._imgview.updateImageTransform()

    @property
    def rotation(self) -> float:
        return self.slideRot.value() / 10.0

    @rotation.setter
    def rotation(self, rot: float):
        self.slideRot.setValue(int(rot*10))
    

    def setSelectionSize(self, w, h):
        self.lblW.setText(f"{w:.1f} px")
        self.lblH.setText(f"{h:.1f} px")

        scale = (self.spinH.value() / h) if h>0 else 1.0
        if scale > 1.0:
            self.lblScale.setStyleSheet("QLabel { color: #ff3030; }")
            self.lblScale.setText(f"▲   {scale:.3f}")
        else:
            self.lblScale.setStyleSheet("QLabel { color: #30ff30; }")
            self.lblScale.setText(f"▼   {scale:.3f}")


    def getInterpolationMode(self, upscale):
        cbo = self.cboInterpUp if upscale else self.cboInterpDown
        return INTERP_MODES[ cbo.currentText() ]

    def getSaveParams(self):
        key = self.cboFormat.currentText()
        return SAVE_PARAMS[key]

    @property
    def constrainToImage(self) -> bool:
        return self.chkConstrainToImage.isChecked()

    @property
    def allowUpscale(self) -> bool:
        return self.chkAllowUpscale.isChecked()

    def chooseExportPath(self):
        path = self._cropTool._export.basePath
        opts = QtWidgets.QFileDialog.ShowDirsOnly
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose save folder", path, opts)
        if path:
            self._cropTool._export.basePath = path
            self.updateExport()

    def updateExport(self):
        export = self._cropTool._export
        export.extension = self.cboFormat.currentText()
        export.skipDirs = self.spinFolderSkip.value()
        export.subfolders = self.spinSubfolders.value()
        export.folderNames = self.spinFolderNames.value()
        export.suffix = f"_{self.spinW.value()}x{self.spinH.value()}"

        examplePath = export.getExportPath(self._cropTool._imgview.image.filepath)
        self.txtPathSample.setPlainText(examplePath)
