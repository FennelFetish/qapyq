from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from ui.export_settings import ExportWidget
from ui.size_preset import SizePresetComboBox
from config import Config
from lib.colorlib import RED, GREEN
from .crop import CropTool


class CropToolBar(QtWidgets.QToolBar):
    def __init__(self, cropTool: CropTool):
        super().__init__("Crop")
        self._cropTool = cropTool
        self.exportWidget = ExportWidget("crop", cropTool.tab.filelist)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildSelectionSize())
        layout.addWidget(self._buildRotation())
        layout.addWidget(self.exportWidget)

        btnOpenLast = QtWidgets.QPushButton("Open Last File")
        btnOpenLast.clicked.connect(cropTool.openLastExportedFile)
        layout.addWidget(btnOpenLast)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)
        self.cboSizePresets.selectFirstPreset()


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

        self.cboSizePresets = SizePresetComboBox()
        self.cboSizePresets.presetSelected.connect(self.selectSizePreset)

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
        self.chkAllowUpscale.setChecked(False)

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
        self._cropTool.swapCropSize()

    @Slot()
    def sizeQuad(self):
        self.spinH.setValue( self.spinW.value() )

    @Slot()
    def selectSizePreset(self, w: int, h: int):
        # Calc orientation (-1, 0, 1) by subtracting booleans
        oldOrientation = (self.spinH.value() > self.spinW.value()) - (self.spinH.value() < self.spinW.value())
        newOrientation = (h > w) - (h < w)
        # Sum is 0 when orientations are different or both are square. In the 2nd case, swapping does nothing.
        if oldOrientation + newOrientation == 0:
            w, h = h, w

        self.spinW.setValue(w)
        self.spinH.setValue(h)
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
        self.updateExport()

    @property
    def rotation(self) -> float:
        return self.slideRot.value() / 10.0

    @rotation.setter
    def rotation(self, rot: float):
        self.slideRot.setValue(int(rot*10))


    def setSelectionSize(self, w, h):
        self.lblW.setText(f"{w:.1f} px")
        self.lblH.setText(f"{h:.1f} px")

        scale = (self.spinH.value() / h) if h>0 else 0.0
        if scale > 1.0:
            self.lblScale.setStyleSheet(f"QLabel{{color:{RED}}}")
            self.lblScale.setText(f"▲  {scale:.3f}")
        else:
            self.lblScale.setStyleSheet(f"QLabel{{color:{GREEN}}}")
            self.lblScale.setText(f"▼  {scale:.3f}")


    @property
    def constrainToImage(self) -> bool:
        return self.chkConstrainToImage.isChecked()

    @property
    def allowUpscale(self) -> bool:
        return self.chkAllowUpscale.isChecked()


    def updateExport(self):
        self.exportWidget.setExportSize(self.spinW.value(), self.spinH.value(), self.rotation)
        self.exportWidget.updateSample()
