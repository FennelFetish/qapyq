import re
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Signal, Slot, QObject, QSignalBlocker
import lib.qtlib as qtlib
from config import Config


class SizeBucket:
    def __init__(self, w: int, h: int):
        self.w = w
        self.h = h
        self.area = w*h
        self.aspect = w/h



class SizePresetSignals(QObject):
    sizePresetsUpdated = Signal(list)

SIZE_PRESET_SIGNALS = SizePresetSignals()



class SizePresetWidget(QtWidgets.QWidget):
    BUCKET_SPLIT = re.compile(r'[ ,x]')

    def __init__(self):
        super().__init__()
        self._build()

        self.reloadSizeBuckets()
        SIZE_PRESET_SIGNALS.sizePresetsUpdated.connect(self.reloadSizeBuckets)

    def _build(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QtWidgets.QLabel("Width x Height, one per line:"))

        self.txtBuckets = QtWidgets.QPlainTextEdit()
        layout.addWidget(self.txtBuckets)

        self.setLayout(layout)

    def parseSizeBuckets(self, includeSwapped=False) -> list[SizeBucket]:
        lines = self.txtBuckets.toPlainText().splitlines()
        buckets = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            elements = self.BUCKET_SPLIT.split(line)
            if len(elements) != 2:
                print(f"Invalid format for bucket size: {line}")
                continue

            try:
                w = int(elements[0].strip())
                h = int(elements[1].strip())
                buckets.append(SizeBucket(w, h))

                if includeSwapped and w != h:
                    buckets.append(SizeBucket(h, w))
            except ValueError:
                print(f"Invalid format for bucket size: {line}")

        return buckets

    @Slot()
    def reloadSizeBuckets(self, presets: list[str] | None = None):
        if presets is None:
            presets = Config.cropSizePresets

        text = "\n".join(presets)
        self.txtBuckets.setPlainText(text)

    @Slot()
    def saveSizeBuckets(self):
        buckets = [
            f"{bucket.w}x{bucket.h}"
            for bucket in self.parseSizeBuckets()
        ]

        Config.cropSizePresets = buckets
        SIZE_PRESET_SIGNALS.sizePresetsUpdated.emit(buckets)



class SizePresetWindow(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self._build()

        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle("Setup Size Presets")
        self.resize(400, 400)

    def _build(self):
        sizePresetWidget = SizePresetWidget()
        layout = QtWidgets.QGridLayout(self)

        row = 0
        layout.setRowStretch(row, 1)
        layout.addWidget(sizePresetWidget, row, 0, 1, 3)

        row += 1
        btnApply = QtWidgets.QPushButton("Save")
        btnApply.clicked.connect(sizePresetWidget.saveSizeBuckets)
        btnApply.clicked.connect(self.accept)
        layout.addWidget(btnApply, row, 0)

        btnReload = QtWidgets.QPushButton("Reload")
        btnReload.clicked.connect(lambda: sizePresetWidget.reloadSizeBuckets())
        layout.addWidget(btnReload, row, 1)

        btnCancel = QtWidgets.QPushButton("Cancel")
        btnCancel.clicked.connect(self.reject)
        layout.addWidget(btnCancel, row, 2)


        self.setLayout(layout)



class SizePresetComboBox(qtlib.MenuComboBox):
    presetSelected = Signal(int, int)

    def __init__(self):
        super().__init__("Size Presets")
        self.reloadPresets(Config.cropSizePresets)
        self.currentTextChanged.connect(self._onPresetSelected)
        SIZE_PRESET_SIGNALS.sizePresetsUpdated.connect(self.reloadPresets)

    @Slot()
    def reloadPresets(self, presets: list[str]):
        with QSignalBlocker(self):
            self.clear()
            self.addItemWithoutMenuAction("")
            self.addItems(presets)

            self.addSeparator()
            actShowSetup = self.addMenuAction("Setup Sizes...")
            actShowSetup.triggered.connect(self.showSetupWindow)

    @Slot()
    def showSetupWindow(self):
        win = SizePresetWindow(self)
        win.exec()

    @Slot()
    def _onPresetSelected(self, text: str):
        if not text:
            return

        w, h = text.split("x")
        try:
            self.presetSelected.emit(int(w), int(h))
        except ValueError:
            print(f"WARNING: Invalid size preset: '{text}'")

        with QSignalBlocker(self):
            self.setCurrentIndex(0)

    def selectFirstPreset(self):
        self.setCurrentIndex(1)
