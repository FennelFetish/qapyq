import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import lib.qtlib as qtlib
from .caption_preset import CaptionPreset
from config import Config


# TODO?: Banned captions, per caption configurable matching method
#        Strategy pattern defines what happens if banned caption is encountered
#        --> Would probably be easier and more accurate to use LLM for such transformations

class CaptionSettings(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()
        self.ctx = context

        self.bannedSeparator = ', '
        self._defaultPresetPath = Config.pathExport

        self._build()


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)

        row = 0
        self.txtPrefix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtPrefix)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        qtlib.setShowWhitespace(self.txtPrefix)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrefix, row, 1, Qt.AlignTop)

        self.txtSuffix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtSuffix)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        qtlib.setShowWhitespace(self.txtSuffix)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), row, 2, Qt.AlignTop)
        layout.addWidget(self.txtSuffix, row, 3, Qt.AlignTop)

        row += 1
        self.chkPrefixSeparator = QtWidgets.QCheckBox("Append separator to prefix")
        self.chkPrefixSeparator.setChecked(True)
        layout.addWidget(self.chkPrefixSeparator, row, 1)

        self.chkSuffixSeparator = QtWidgets.QCheckBox("Prepend separator to suffix")
        self.chkSuffixSeparator.setChecked(True)
        layout.addWidget(self.chkSuffixSeparator, row, 3)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        self.txtSeparator = QtWidgets.QLineEdit(", ")
        self.txtSeparator.editingFinished.connect(lambda: self.ctx.separatorChanged.emit(self.txtSeparator.text()))
        qtlib.setMonospace(self.txtSeparator)
        layout.addWidget(QtWidgets.QLabel("Separator:"), row, 0, Qt.AlignTop)
        layout.addWidget(self.txtSeparator, row, 1, Qt.AlignTop)

        self.txtBanned = QtWidgets.QPlainTextEdit()
        self.txtBanned.textChanged.connect(lambda: self.ctx.controlUpdated.emit())
        qtlib.setMonospace(self.txtBanned)
        qtlib.setTextEditHeight(self.txtBanned, 3)
        layout.addWidget(QtWidgets.QLabel("Banned:"), row, 2, Qt.AlignTop)
        layout.addWidget(self.txtBanned, row, 3, 2, 1, Qt.AlignTop)

        row += 1
        self.chkAutoApply = QtWidgets.QCheckBox("Auto apply rules")
        self.chkRemoveDup = QtWidgets.QCheckBox("Remove duplicates")
        self.chkRemoveDup.setChecked(True)
        
        rowLayout = QtWidgets.QHBoxLayout()
        rowLayout.addWidget(self.chkAutoApply)
        rowLayout.addWidget(self.chkRemoveDup)
        layout.addLayout(rowLayout, row, 1)

        btnAddBanned = QtWidgets.QPushButton("Ban")
        btnAddBanned.setFixedWidth(50)
        btnAddBanned.setFocusPolicy(Qt.NoFocus)
        btnAddBanned.clicked.connect(self.addBanned)
        layout.addWidget(btnAddBanned, row, 2)
        
        row += 1
        self.btnLoad = QtWidgets.QPushButton("Load preset...")
        self.btnLoad.clicked.connect(self.loadPreset)
        layout.addWidget(self.btnLoad, row, 0, 1, 2)

        self.btnSave = QtWidgets.QPushButton("Save preset as...")
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 2, 1, 2)

        self.setLayout(layout)


    @property
    def prefix(self) -> str:
        prefix = self.txtPrefix.toPlainText()
        if prefix and self.chkPrefixSeparator.isChecked():
            prefix += self.separator
        return prefix

    @property
    def suffix(self) -> str:
        suffix = self.txtSuffix.toPlainText()
        if suffix and self.chkSuffixSeparator.isChecked():
            suffix = self.separator + suffix
        return suffix

    @property
    def separator(self) -> str:
        return self.txtSeparator.text()


    @property
    def isAutoApplyRules(self) -> bool:
        return self.chkAutoApply.isChecked()

    @property
    def isRemoveDuplicates(self) -> bool:
        return self.chkRemoveDup.isChecked()


    @property
    def bannedCaptions(self) -> list[str]:
        banned = self.txtBanned.toPlainText().split(self.bannedSeparator.strip())
        return [b.strip() for b in banned]
    
    @bannedCaptions.setter
    def bannedCaptions(self, bannedCaptions):
        self.txtBanned.setPlainText( self.bannedSeparator.join(bannedCaptions) )


    @Slot()
    def addBanned(self):
        caption = self.ctx.getSelectedCaption()
        text = self.txtBanned.toPlainText()
        if text:
            text += self.bannedSeparator
        text += caption
        self.txtBanned.setPlainText(text)
    
    def getPreset(self):
        preset = CaptionPreset()
        preset.prefix = self.txtPrefix.toPlainText()
        preset.suffix = self.txtSuffix.toPlainText()
        preset.separator = self.txtSeparator.text()
        preset.prefixSeparator = self.chkPrefixSeparator.isChecked()
        preset.suffixSeparator = self.chkSuffixSeparator.isChecked()
        preset.autoApplyRules = self.chkAutoApply.isChecked()
        preset.removeDuplicates = self.chkRemoveDup.isChecked()
        preset.banned = self.bannedCaptions

        self.ctx.groups.saveToPreset(preset)
        return preset

    @Slot()
    def savePreset(self):
        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save preset", self._defaultPresetPath, fileFilter)
        if path:
            self._defaultPresetPath = os.path.dirname(path)
            preset = self.getPreset()
            preset.saveTo(path)

    @Slot()
    def loadPreset(self):
        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(self, "Load preset", self._defaultPresetPath, fileFilter)
        if not path:
            return
        self._defaultPresetPath = os.path.dirname(path)

        preset = CaptionPreset()
        preset.loadFrom(path)
        self.txtPrefix.setPlainText(preset.prefix)
        self.txtSuffix.setPlainText(preset.suffix)
        self.txtSeparator.setText(preset.separator)
        self.chkPrefixSeparator.setChecked(preset.prefixSeparator)
        self.chkSuffixSeparator.setChecked(preset.suffixSeparator)
        self.chkAutoApply.setChecked(preset.autoApplyRules)
        self.chkRemoveDup.setChecked(preset.removeDuplicates)
        self.bannedCaptions = preset.banned

        self.ctx.groups.loadFromPreset(preset)
        self.ctx.controlUpdated.emit()
