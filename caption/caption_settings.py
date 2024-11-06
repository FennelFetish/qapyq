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
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        layout.setColumnStretch(2, 0)
        layout.setColumnMinimumWidth(2, 12)

        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)
        
        row = 0
        self.srcSelector = FileTypeSelector(self.ctx)
        layout.addWidget(QtWidgets.QLabel("Load From:"), row, 0)
        layout.addLayout(self.srcSelector, row, 1)

        self.destSelector = FileTypeSelector(self.ctx)
        layout.addWidget(QtWidgets.QLabel("Save To:"), row, 3)
        layout.addLayout(self.destSelector, row, 4)

        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        rules = self._buildRules()
        layout.addWidget(rules, row, 0, 1, 5)

        self.setLayout(layout)

    def _buildRules(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)

        layout.setColumnStretch(2, 0)
        layout.setColumnMinimumWidth(2, 12)

        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 1)

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
        layout.addWidget(QtWidgets.QLabel("Suffix:"), row, 3, Qt.AlignTop)
        layout.addWidget(self.txtSuffix, row, 4, Qt.AlignTop)

        row += 1
        self.chkPrefixSeparator = QtWidgets.QCheckBox("Append separator to prefix")
        self.chkPrefixSeparator.setChecked(True)
        layout.addWidget(self.chkPrefixSeparator, row, 1)

        self.chkSuffixSeparator = QtWidgets.QCheckBox("Prepend separator to suffix")
        self.chkSuffixSeparator.setChecked(True)
        layout.addWidget(self.chkSuffixSeparator, row, 4)

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
        layout.addWidget(QtWidgets.QLabel("Banned:"), row, 3, Qt.AlignTop)
        layout.addWidget(self.txtBanned, row, 4, 2, 1, Qt.AlignTop)

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
        layout.addWidget(btnAddBanned, row, 3)
        
        row += 1
        layout.setRowMinimumHeight(row, 8)

        row += 1
        self.btnLoad = QtWidgets.QPushButton("Load Rules and Groups...")
        self.btnLoad.clicked.connect(self.loadPreset)
        layout.addWidget(self.btnLoad, row, 0, 1, 2)

        self.btnSave = QtWidgets.QPushButton("Save Rules and Groups as...")
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, row, 3, 1, 2)

        group = QtWidgets.QGroupBox("Rules")
        group.setLayout(layout)
        return group



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



class FileTypeSelector(QtWidgets.QHBoxLayout):
    TYPE_TXT = "txt"
    TYPE_TAGS = "tags"
    TYPE_CAPTIONS = "captions"

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

        self.cboType = QtWidgets.QComboBox()
        self.cboType.addItem(".txt File", self.TYPE_TXT)
        self.cboType.addItem(".json Tags:", self.TYPE_TAGS)
        self.cboType.addItem(".json Caption:", self.TYPE_CAPTIONS)
        self.cboType.currentIndexChanged.connect(self._onTypeChanged)
        self.addWidget(self.cboType)

        self.txtName = QtWidgets.QLineEdit("tags")
        self.txtName.editingFinished.connect(self._onEdited)
        qtlib.setMonospace(self.txtName)
        self.addWidget(self.txtName)

        self._onTypeChanged(self.cboType.currentIndex())
    
    @Slot()
    def _onTypeChanged(self, index):
        nameEnabled = self.cboType.itemData(index) != self.TYPE_TXT
        self.txtName.setEnabled(nameEnabled)

        self.ctx.fileTypeUpdated.emit()

    @Slot()
    def _onEdited(self):
        if not self.name:
            if self.type == self.TYPE_TAGS:
                self.txtName.setText("tags")
            else:
                self.txtName.setText("caption")
        
        self.ctx.fileTypeUpdated.emit()


    @property
    def type(self) -> str:
        return self.cboType.currentData()

    @property
    def name(self) -> str:
        return self.txtName.text()
