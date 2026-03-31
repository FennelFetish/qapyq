from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from ui.export_settings import ExportWidget, ExportFileType
from ui.size_preset import SizePresetComboBox
from config import Config
from lib import colorlib
from .crop import CropTool


class CropToolBar(QtWidgets.QToolBar):
    def __init__(self, cropTool: CropTool):
        super().__init__("Crop")
        self._cropTool = cropTool

        self.exportWidget = ExportWidget("crop", cropTool.tab.filelist)
        self.exportWidget.fpsChanged.connect(self.updateDuration)
        self.exportWidget.fileTypeChanged.connect(self._onExportFileTypeChanged)

        self._timeRange = self._buildTimeRange()

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._timeRange)
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
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)

        row = 0
        lblW = QtWidgets.QLabel("W:")
        lblW.setToolTip("Scale to this width")
        lblW.setFixedWidth(24)
        layout.addWidget(lblW, row, 0)

        self.spinW = QtWidgets.QSpinBox()
        self.spinW.setToolTip("Scale to this width")
        self.spinW.setRange(1, 16384)
        self.spinW.setSingleStep(Config.cropSizeStep)
        self.spinW.setValue(512)
        self.spinW.valueChanged.connect(self.updateSize)
        layout.addWidget(self.spinW, row, 1, 1, 2)

        row += 1
        lblH = QtWidgets.QLabel("H:")
        lblH.setToolTip("Scale to this height")
        lblH.setFixedWidth(24)
        layout.addWidget(lblH, row, 0)

        self.spinH = QtWidgets.QSpinBox()
        self.spinH.setToolTip("Scale to this height")
        self.spinH.setRange(1, 16384)
        self.spinH.setSingleStep(Config.cropSizeStep)
        self.spinH.setValue(512)
        self.spinH.valueChanged.connect(self.updateSize)
        layout.addWidget(self.spinH, row, 1, 1, 2)

        row += 1
        lblTargetAspect = QtWidgets.QLabel("AR:")
        lblTargetAspect.setToolTip("Resulting aspect ratio")
        lblTargetAspect.setFixedWidth(24)
        layout.addWidget(lblTargetAspect, row, 0)

        self.lblTargetAspect = QtWidgets.QLabel()
        layout.addWidget(self.lblTargetAspect, row, 1, 1, 2)

        row += 1
        lblPreset = QtWidgets.QLabel("Pre:")
        lblPreset.setToolTip("Choose size preset")
        lblPreset.setFixedWidth(24)
        layout.addWidget(lblPreset, row, 0)

        self.cboSizePresets = SizePresetComboBox()
        self.cboSizePresets.setToolTip("Choose size preset")
        self.cboSizePresets.presetSelected.connect(self.selectSizePreset)
        layout.addWidget(self.cboSizePresets, row, 1, 1, 2)

        row += 1
        btnSwap = QtWidgets.QPushButton("Swap")
        btnSwap.setToolTip("Swap width/height with <b>Middle Mouse Button</b>")
        btnSwap.clicked.connect(self.sizeSwap)
        layout.addWidget(btnSwap, row, 1)

        btnQuad = QtWidgets.QPushButton("Square")
        btnQuad.setToolTip("Make square (height=width)")
        btnQuad.clicked.connect(self.sizeQuad)
        layout.addWidget(btnQuad, row, 2)

        group = QtWidgets.QGroupBox("Target Size")
        group.setLayout(layout)
        return group

    def _buildTimeRange(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        row = 0
        self.spinLength = QtWidgets.QSpinBox()
        self.spinLength.setToolTip("Length of the exported segment in frames")
        self.spinLength.setRange(1, 999_992)
        self.spinLength.setSingleStep(8)
        self.spinLength.setValue(121)
        self.spinLength.setMinimumWidth(60)
        self.spinLength.valueChanged.connect(self.updateDuration)

        row += 1
        lblLength = QtWidgets.QLabel("Len:")
        lblLength.setToolTip("Length of the exported segment")
        lblLength.setFixedWidth(24)
        layout.addWidget(lblLength, row, 0)
        layout.addWidget(self.spinLength, row, 1)

        self.lblDuration = QtWidgets.QLabel("0.000 s")
        self.lblDuration.setToolTip("Length of the exported segment in seconds")
        layout.addWidget(self.lblDuration, row, 2, Qt.AlignmentFlag.AlignHCenter)

        row += 1
        lblSet = QtWidgets.QLabel("Set:")
        lblSet.setFixedWidth(24)
        layout.addWidget(lblSet, row, 0)

        btnSetEnd = QtWidgets.QPushButton("End")
        btnSetEnd.setToolTip("Set current frame as last frame. Skip back by 'Len' frames.")
        btnSetEnd.clicked.connect(self.setEndFrame)
        layout.addWidget(btnSetEnd, row, 1)

        btnSetKey = QtWidgets.QPushButton("Key")
        btnSetKey.setToolTip("Skip back to last key frame")
        btnSetKey.setEnabled(False)
        layout.addWidget(btnSetKey, row, 2)

        group = QtWidgets.QGroupBox("Time Range")
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
        self.slideRot = QtWidgets.QSlider(Qt.Orientation.Horizontal)
        self.slideRot.setRange(-10, 3600)
        self.slideRot.setTickPosition(QtWidgets.QSlider.TickPosition.TicksAbove)
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


    def getDurationMs(self) -> int:
        fps = self.exportWidget.getFps()
        numFrames = self.spinLength.value()
        return round(1000.0 * numFrames / fps)

    @Slot()
    def updateDuration(self):
        seconds = self.getDurationMs() / 1000.0
        self.lblDuration.setText(f"{seconds:.3f} s")
        self._cropTool.updateTimeSegment(setStart=False)
        self.updateExport()

    @Slot()
    def setEndFrame(self):
        from ui.video_player import VideoItem
        item: VideoItem = self._cropTool._imgview.image
        if item.TYPE != VideoItem.TYPE:
            return

        pos = item.player.position() - self.getDurationMs()
        pos = max(pos, 0)
        item.player.setPosition(pos)
        self._cropTool.updateTimeSegment()


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
        self._cropTool.resetSelection()

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
            self.lblScale.setStyleSheet(f"QLabel{{color:{colorlib.RED}}}")
            self.lblScale.setText(f"▲  {scale:.3f}")
        else:
            self.lblScale.setStyleSheet(f"QLabel{{color:{colorlib.GREEN}}}")
            self.lblScale.setText(f"▼  {scale:.3f}")


    @property
    def constrainToImage(self) -> bool:
        return self.chkConstrainToImage.isChecked()

    @property
    def allowUpscale(self) -> bool:
        return self.chkAllowUpscale.isChecked()


    def updateExport(self):
        self.exportWidget.setExportSize(self.spinW.value(), self.spinH.value(), self.rotation, self.spinLength.value())
        self.exportWidget.updateSample()
        #self.updateDuration()

    @Slot()
    def _onExportFileTypeChanged(self, fileType: ExportFileType):
        isVideo = (fileType == ExportFileType.Video)
        self._timeRange.setVisible(isVideo)

        if not isVideo:
            self._cropTool.updateTimeSegment()

    def needTimeSegment(self) -> bool:
        return self._timeRange.isVisible()
