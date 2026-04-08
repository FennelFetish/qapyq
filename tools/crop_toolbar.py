from typing import TYPE_CHECKING
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
from ui.export_settings import ExportWidget, ExportFileType
from ui.size_preset import SizePresetComboBox
from ui.imgview import MediaItemType
from config import Config
from lib import colorlib
from .crop import CropTool

if TYPE_CHECKING:
    from ui.video_player import VideoItem


class CropToolBar(QtWidgets.QToolBar):
    def __init__(self, cropTool: CropTool):
        super().__init__("Crop")
        self._cropTool = cropTool
        self._initialized = False

        self.exportWidget = ExportWidget("crop", cropTool.tab.filelist)
        self.exportWidget.fpsChanged.connect(self.updateDuration)
        self.exportWidget.fileTypeChanged.connect(self._onExportFileTypeChanged)

        self._timeRange = self._buildTimeRange()

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(self._buildTargetSize())
        layout.addWidget(self._buildSelectionSize())
        layout.addWidget(self._timeRange)
        layout.addWidget(self._buildRotation())
        layout.addWidget(self.exportWidget)

        btnOpenLast = QtWidgets.QPushButton("Open Last File")
        btnOpenLast.clicked.connect(cropTool.openLastExportedFile)
        layout.addWidget(btnOpenLast)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.addWidget(widget)

        self.setMaximumWidth(180)

    def initPreset(self):
        # Initialize preset when tool is first enabled because some functions need ImgView
        if not self._initialized:
            self.cboSizePresets.selectFirstPreset()
            self._initialized = True

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
        btnSwap.setMaximumHeight(22)
        btnSwap.clicked.connect(self.sizeSwap)
        layout.addWidget(btnSwap, row, 1)

        btnQuad = QtWidgets.QPushButton("Square")
        btnQuad.setToolTip("Make square (height=width)")
        btnQuad.setMaximumHeight(22)
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
        self.spinLength.setRange(9, 999_992)
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

        btnSetEnd = QtWidgets.QPushButton("End Frame")
        btnSetEnd.setToolTip("Set current frame as last frame. Skip back by 'Len' frames")
        btnSetEnd.setMaximumHeight(22)
        #qtlib.setFontSize(btnSetEnd, 0.9)
        btnSetEnd.clicked.connect(self.setEndFrame)
        layout.addWidget(btnSetEnd, row, 1, 1, 2)

        row += 1
        self.lblDurationScaled = QtWidgets.QLabel("0.000 s")
        self.lblDurationScaled.hide()

        self.chkChangeExportSpeed = QtWidgets.QCheckBox("Change Speed")
        self.chkChangeExportSpeed.setToolTip("Change the speed of the exported media to the current playback speed")
        self.chkChangeExportSpeed.toggled.connect(self.lblDurationScaled.setVisible)
        self.chkChangeExportSpeed.toggled.connect(self.updateDuration)
        layout.addWidget(self.chkChangeExportSpeed, row, 0, 1, 3)

        row += 1
        layout.addWidget(self.lblDurationScaled, row, 0, 1, 3, Qt.AlignmentFlag.AlignHCenter)

        group = QtWidgets.QGroupBox("Time Range")
        group.setLayout(layout)
        return group

    def _buildSelectionSize(self):
        self.lblW = QtWidgets.QLabel("0 px")
        self.lblH = QtWidgets.QLabel("0 px")
        self.lblScale = QtWidgets.QLabel("1.0")

        self.chkConstrainToImage = QtWidgets.QCheckBox("Constrain to Image")
        self.chkConstrainToImage.setToolTip("Keep selection rectangle inside image")
        self.chkConstrainToImage.setChecked(True)

        self.chkAllowUpscale = QtWidgets.QCheckBox("Allow Upscale")
        self.chkAllowUpscale.setToolTip("Keep selection rectangle larger than 'target size' to prevent upscaling")
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

    @Slot(int, int, int)
    def selectSizePreset(self, w: int, h: int, length: int):
        # Calc orientation (-1, 0, 1) by subtracting booleans
        oldOrientation = (self.spinH.value() > self.spinW.value()) - (self.spinH.value() < self.spinW.value())
        newOrientation = (h > w) - (h < w)
        # Sum is 0 when orientations are different or both are square. In the 2nd case, swapping does nothing.
        if oldOrientation + newOrientation == 0:
            w, h = h, w

        self.spinW.setValue(w)
        self.spinH.setValue(h)
        self.updateSize()

        if length > 0:
            self.spinLength.setValue(length)
        self.updateDuration()

        self.cboSizePresets.setCurrentIndex(0)

    @Slot()
    def setEndFrame(self):
        item: VideoItem = self._cropTool._imgview.image
        if item.TYPE != MediaItemType.Video:
            return

        speed = item.player.playbackRate() if self.changeSpeed else 1.0
        duration = round(self.getDurationMs() * speed)

        pos = item.player.position() - duration
        pos = max(pos, 0)
        if item.setVideoPosition(pos):
            self._cropTool.updateTimeSegment()


    def getDurationMs(self) -> int:
        fps = self.exportWidget.getFps()
        numFrames = self.spinLength.value()
        return round(1000.0 * numFrames / fps)

    @Slot()
    def updateDuration(self):
        duration = self.getDurationMs() / 1000.0
        self.lblDuration.setText(f"{duration:.3f} s")
        self._cropTool.updateTimeSegment(setStart=False)
        self.updateExport()

        changeSpeedText = "Change Speed"
        durationScaledText = "0.000 s"

        item: VideoItem = self._cropTool._imgview.image
        if item.TYPE == MediaItemType.Video:
            speed = item.player.playbackRate()
            changeSpeedText = f"Change Speed (x{speed:.2f})"
            if self.changeSpeed:
                durationScaled = speed * duration
                durationScaledText = f"{durationScaled:.3f} s  →  {duration:.3f} s"

        self.chkChangeExportSpeed.setText(changeSpeedText)
        self.lblDurationScaled.setText(durationScaledText)


    @Slot(int)
    def updateRotationFromSlider(self, rot: int):
        self.spinRot.setValue(rot / 10.0)

    @Slot(float)
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

    @property
    def changeSpeed(self) -> bool:
        return self.chkChangeExportSpeed.isChecked()

    @property
    def needTimeSegment(self) -> bool:
        return self._timeRange.isVisible()


    def updateExport(self):
        speed = 1.0
        item: VideoItem = self._cropTool._imgview.image
        if item.TYPE == MediaItemType.Video and self.changeSpeed:
            speed = item.player.playbackRate()

        self.exportWidget.setExportSize(self.spinW.value(), self.spinH.value(), self.rotation, self.spinLength.value(), speed)
        self.exportWidget.updateSample()

    @Slot(ExportFileType)
    def _onExportFileTypeChanged(self, fileType: ExportFileType):
        isVideo = (fileType == ExportFileType.Video)
        self._timeRange.setVisible(isVideo)

        if not isVideo:
            self._cropTool.updateTimeSegment()
