import os
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot, QSignalBlocker, QTimer
import lib.qtlib as qtlib
from ui.edit_table import EditableTable
from ui.flow_layout import SortedStringFlowWidget
from .caption_tab import CaptionTab
from .caption_preset import CaptionPreset
from config import Config


class CaptionSettings(CaptionTab):
    def __init__(self, context):
        super().__init__(context)

        self._defaultPresetPath = Config.pathExport
        self._emitUpdates = True

        self._build()

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 0)

        layout.setColumnStretch(3, 0)
        layout.setColumnMinimumWidth(3, 12)

        layout.setColumnStretch(4, 0)
        layout.setColumnStretch(5, 1)

        self._buildLeftColumn(layout)
        self._buildRightColumn(layout)

        for row in range(layout.rowCount()):
            layout.setRowStretch(row, 0)
        layout.setRowStretch(row, 1)

        self.setLayout(layout)

    def _buildLeftColumn(self, layout: QtWidgets.QGridLayout):
        row = 0
        self.txtSeparator = QtWidgets.QLineEdit(", ")
        self.txtSeparator.editingFinished.connect(lambda: self.ctx.separatorChanged.emit(self.txtSeparator.text()))
        qtlib.setMonospace(self.txtSeparator)
        layout.addWidget(QtWidgets.QLabel("Separator:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtSeparator, row, 1, 1, 2, Qt.AlignmentFlag.AlignTop)

        row += 1
        self.chkPrefixSeparator = QtWidgets.QCheckBox("Append separator to prefix")
        self.chkPrefixSeparator.setChecked(True)
        self.chkPrefixSeparator.toggled.connect(self._emitUpdate)
        layout.addWidget(self.chkPrefixSeparator, row, 1, Qt.AlignmentFlag.AlignTop)

        self.chkSuffixSeparator = QtWidgets.QCheckBox("Prepend separator to suffix")
        self.chkSuffixSeparator.setChecked(True)
        self.chkSuffixSeparator.toggled.connect(self._emitUpdate)
        layout.addWidget(self.chkSuffixSeparator, row, 2, Qt.AlignmentFlag.AlignTop)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Options:"), row, 0, Qt.AlignmentFlag.AlignTop)

        self.chkRemoveDup = QtWidgets.QCheckBox("Remove Duplicates/Subsets")
        self.chkRemoveDup.setChecked(True)
        self.chkRemoveDup.toggled.connect(self._emitUpdate)
        layout.addWidget(self.chkRemoveDup, row, 1, Qt.AlignmentFlag.AlignTop)

        self.chkSortCaptions = QtWidgets.QCheckBox("Sort Captions")
        self.chkSortCaptions.setChecked(True)
        self.chkSortCaptions.toggled.connect(self._emitUpdate)
        layout.addWidget(self.chkSortCaptions, row, 2, Qt.AlignmentFlag.AlignTop)

        row += 1
        layout.setRowMinimumHeight(row, 4)

        row += 1
        self.tableReplace = EditableTable(2)
        self.tableReplace.setHorizontalHeaderLabels(["Search Pattern", "Replacement"])
        self.tableReplace.contentChanged.connect(self._emitUpdate)
        layout.addWidget(QtWidgets.QLabel("Replace:"), row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.tableReplace, row, 1, 3, 2)

    def _buildRightColumn(self, layout: QtWidgets.QGridLayout):
        row = 0
        self.txtPrefix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtPrefix)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        qtlib.setShowWhitespace(self.txtPrefix)
        self.txtPrefix.textChanged.connect(self._emitUpdate)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), row, 4, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtPrefix, row, 5, 2, 1, Qt.AlignmentFlag.AlignTop)

        row += 2
        self.txtSuffix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtSuffix)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        qtlib.setShowWhitespace(self.txtSuffix)
        self.txtSuffix.textChanged.connect(self._emitUpdate)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), row, 4, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.txtSuffix, row, 5, Qt.AlignmentFlag.AlignTop)

        row += 1
        # spacing

        row += 1
        self.chkWhitelistGroups = QtWidgets.QCheckBox("Groups are Whitelists (Ban all other tags)")
        self.chkWhitelistGroups.toggled.connect(lambda checked: self.banWidget.setEnabled(not checked))
        self.chkWhitelistGroups.toggled.connect(self._emitUpdate)
        layout.addWidget(self.chkWhitelistGroups, row, 5, Qt.AlignmentFlag.AlignTop)

        row += 1
        layout.addWidget(QtWidgets.QLabel("Banned:"), row, 4, Qt.AlignmentFlag.AlignTop)

        self.banWidget = SortedStringFlowWidget()
        self.banWidget.changed.connect(self._emitUpdate)
        layout.addWidget(qtlib.BaseColorScrollArea(self.banWidget), row, 5, 2, 1)

        row += 1
        btnAddBanned = QtWidgets.QPushButton("Ban")
        btnAddBanned.setFixedWidth(50)
        btnAddBanned.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btnAddBanned.clicked.connect(self.banSelectedCaption)
        layout.addWidget(btnAddBanned, row, 4, Qt.AlignmentFlag.AlignTop)


    @Slot()
    def _emitUpdate(self):
        if self._emitUpdates:
            self.ctx.controlUpdated.emit()


    @property
    def prefix(self) -> str:
        return self.txtPrefix.toPlainText()

    @property
    def suffix(self) -> str:
        return self.txtSuffix.toPlainText()

    @property
    def isAddPrefixSeparator(self) -> bool:
        return self.chkPrefixSeparator.isChecked()

    @property
    def isAddSuffixSeparator(self) -> bool:
        return self.chkSuffixSeparator.isChecked()


    @property
    def separator(self) -> str:
        return self.txtSeparator.text()


    @property
    def isRemoveDuplicates(self) -> bool:
        return self.chkRemoveDup.isChecked()

    @property
    def isSortCaptions(self) -> bool:
        return self.chkSortCaptions.isChecked()

    @property
    def isWhitelistGroups(self) -> bool:
        return self.chkWhitelistGroups.isChecked()


    @property
    def searchReplacePairs(self) -> list[tuple[str, str]]:
        return self.tableReplace.getContent()

    @searchReplacePairs.setter
    def searchReplacePairs(self, pairs: list[tuple[str, str]]):
        self.tableReplace.setContent(pairs)
        self.tableReplace.resizeColumnsToContents()


    @property
    def bannedCaptions(self) -> list[str]:
        return [b.strip() for b in self.banWidget.getItems()]

    @bannedCaptions.setter
    def bannedCaptions(self, bannedCaptions: list[str]):
        self.banWidget.setItems(bannedCaptions)

    def addBannedCaption(self, caption: str) -> bool:
        if caption:
            return self.banWidget.addItem(caption)
        return False

    @Slot()
    def banSelectedCaption(self):
        caption = self.ctx.text.getSelectedCaption()
        self.addBannedCaption(caption)


    def getPreset(self):
        preset = CaptionPreset()
        preset.prefix           = self.txtPrefix.toPlainText()
        preset.suffix           = self.txtSuffix.toPlainText()
        preset.separator        = self.txtSeparator.text()
        preset.prefixSeparator  = self.chkPrefixSeparator.isChecked()
        preset.suffixSeparator  = self.chkSuffixSeparator.isChecked()
        preset.removeDuplicates = self.chkRemoveDup.isChecked()
        preset.sortCaptions     = self.chkSortCaptions.isChecked()
        preset.whitelistGroups  = self.chkWhitelistGroups.isChecked()
        preset.searchReplace    = self.searchReplacePairs
        preset.banned           = self.bannedCaptions

        preset.autoApplyRules = self.ctx.container.isAutoApplyRules()

        self.ctx.groups.saveToPreset(preset)
        self.ctx.conditionals.saveToPreset(preset)
        return preset

    @Slot()
    def savePreset(self):
        fileFilter = "JSON (*.json)"
        path = os.path.join(self._defaultPresetPath, "caption-rules.json")
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save preset", path, fileFilter)
        if path:
            self._defaultPresetPath = os.path.dirname(path)
            preset = self.getPreset()
            preset.saveTo(path)

    @Slot()
    def saveAsDefaultPreset(self):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Overwrite Defaults")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        presetPath = os.path.abspath(Config.pathDefaultCaptionRules)
        dialog.setText(f"Overwrite the default rules and groups?\n\nThis will overwrite the file:\n{presetPath}")

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            preset = self.getPreset()
            preset.saveTo(presetPath)

    @Slot()
    def loadPreset(self):
        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(self, "Load preset", self._defaultPresetPath, fileFilter)
        if not path:
            return
        self._defaultPresetPath = os.path.dirname(path)

        preset = CaptionPreset()
        preset.loadFrom(path)
        self.applyPreset(preset)

    @Slot()
    def loadDefaultPreset(self):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Reset")
        dialog.setText(f"Reset all rules and groups to the default values?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            if not self._loadDefaultPreset():
                self.applyPreset(CaptionPreset())

    def _loadDefaultPreset(self) -> bool:
        if not os.path.exists(Config.pathDefaultCaptionRules):
            return False

        preset = CaptionPreset()
        preset.loadFrom(Config.pathDefaultCaptionRules)
        self.applyPreset(preset)
        return True

    @Slot()
    def clearPreset(self):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm Reset")
        dialog.setText(f"Clear all rules and groups?")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.applyPreset(CaptionPreset())

    def applyPreset(self, preset: CaptionPreset):
        try:
            self._emitUpdates = False

            self.txtPrefix.setPlainText(preset.prefix)
            self.txtSuffix.setPlainText(preset.suffix)
            self.txtSeparator.setText(preset.separator)
            self.chkPrefixSeparator.setChecked(preset.prefixSeparator)
            self.chkSuffixSeparator.setChecked(preset.suffixSeparator)
            self.chkRemoveDup.setChecked(preset.removeDuplicates)
            self.chkSortCaptions.setChecked(preset.sortCaptions)
            self.chkWhitelistGroups.setChecked(preset.whitelistGroups)

            self.ctx.container.setAutoApplyRules(preset.autoApplyRules)

            self.searchReplacePairs = preset.searchReplace
            self.bannedCaptions = preset.banned

            with QSignalBlocker(self.ctx):
                self.ctx.groups.loadFromPreset(preset)
                self.ctx.conditionals.loadFromPreset(preset)

        finally:
            self._emitUpdates = True

            # When the group tab is open while loading a preset, highlighting fails because the groups are not directly visible after adding.
            # They report enabled=False and are filtered out in CaptionContextDataSource.getGroups(). Workaround: Delay the update.
            QTimer.singleShot(0, self.ctx.controlUpdated.emit)
            QTimer.singleShot(0, self.ctx.groups.updateGalleryFilter)
