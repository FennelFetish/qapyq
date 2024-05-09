from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import cv2 as cv


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
        layout.addWidget(self._buildSave())
        layout.addWidget(self._buildDestination())

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        act = self.addWidget(widget)

        self.setMaximumWidth(180)


    def _buildTargetSize(self):
        self.spinW = QtWidgets.QSpinBox()
        self.spinW.setRange(1, 16384)
        self.spinW.setSingleStep(64)
        self.spinW.setValue(512)
        self.spinW.valueChanged.connect(self.updateSize)

        self.spinH = QtWidgets.QSpinBox()
        self.spinH.setRange(1, 16384)
        self.spinH.setSingleStep(64)
        self.spinH.setValue(512)
        self.spinH.valueChanged.connect(self.updateSize)

        self.lblTargetAspect = QtWidgets.QLabel()

        btnSwap = QtWidgets.QPushButton("Swap")
        btnSwap.clicked.connect(self.sizeSwap)

        btnQuad = QtWidgets.QPushButton("Quad")
        btnQuad.clicked.connect(self.sizeQuad)

        self.cboSizePresets = QtWidgets.QComboBox()
        self.cboSizePresets.addItems(["", "512x512", "512x768", "768x768", "768x1152", "1024x1024", "1024x1536"])
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

        self.chkConstrainSize = QtWidgets.QCheckBox("Constrain to Image")
        self.chkConstrainSize.setChecked(True)

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

        layout.addWidget(self.chkConstrainSize, 2, 0, 1, 3)

        group = QtWidgets.QGroupBox("Selection")
        group.setLayout(layout)
        return group

    def _buildRotation(self):
        self.slideRot = QtWidgets.QSlider(Qt.Horizontal)
        self.slideRot.setRange(-1, 3600)
        self.slideRot.setTickPosition(QtWidgets.QSlider.TicksAbove)
        self.slideRot.setTickInterval(900)
        self.slideRot.setSingleStep(10)
        self.slideRot.setPageStep(50)
        self.slideRot.setValue(0)
        self.slideRot.valueChanged.connect(self.updateRotationFromSlider)

        self.spinRot = PrecisionSpinBox()
        self.spinRot.setRange(-3600, 3600)
        self.spinRot.setSingleStep(1)
        self.spinRot.setValue(0)
        self.spinRot.valueChanged.connect(self.updateRotationFromSpinner)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.slideRot)
        layout.addRow("Deg:", self.spinRot)

        group = QtWidgets.QGroupBox("Rotation")
        group.setLayout(layout)
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

        group = QtWidgets.QGroupBox("Save Params")
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

        self.txtPathSample = QtWidgets.QTextEdit()
        self.txtPathSample.setReadOnly(True)

        layout = QtWidgets.QFormLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addRow(self.btnChoosePath)
        layout.addRow("Folder Skip:", self.spinFolderSkip)
        layout.addRow("Folder Names:", self.spinFolderNames)
        layout.addRow("Subfolders:", self.spinSubfolders)
        layout.addRow(self.txtPathSample)

        group = QtWidgets.QGroupBox("Save Destination")
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
        self.spinRot.setValue(rot)
        self._cropTool._imgview.rotation = rot / 10
        self._cropTool._imgview.updateImageTransform()

    @Slot()
    def updateRotationFromSpinner(self, rot: int):
        rot = rot % 3600
        self.spinRot.setValue(rot)
        self.slideRot.setValue(rot)
        
        self._cropTool._imgview.rotation = rot / 10
        self._cropTool._imgview.updateImageTransform()


    def setSelectionSize(self, w, h):
        self.lblW.setText(f"{w:.1f} px")
        self.lblH.setText(f"{h:.1f} px")

        scale = self.spinH.value() / h
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

    def constrainSize(self) -> bool:
        return self.chkConstrainSize.isChecked()

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

        examplePath = export.getExportPath(self._cropTool._imgview.filelist.getCurrentFile())
        self.txtPathSample.setText(examplePath)



class PrecisionSpinBox(QtWidgets.QSpinBox):
    PRECISION = 10

    def textFromValue(self, val: int) -> str:
        return f"{val / self.PRECISION:.1f}"
    
    def valueFromText(self, text: str) -> int:
        val = float(text) * self.PRECISION
        return round(val)
