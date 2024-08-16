
import os
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt, Signal, Slot
from typing import ForwardRef
import qtlib
from .caption_preset import CaptionPreset

CaptionControlGroup = ForwardRef('CaptionControlGroup')


# Controls for:
#    - Prefix, Suffix
#    - Separator (',' / '.')
#    - Banned captions, per caption configurable matching method
#        - Strategy pattern: Object defines what happens if banned caption is encountered
#    - Groups
#        - Order of groups define sorting
#        - Optional: mutually exclusive
#        - Per group matching method:
#           exact match (str1 == str2)
#           substring ('b c' in 'a b c d e', but not 'b d')
#           all words ('b c' in 'a b c d e', but not 'b f')
#           any word  ('b d' in 'a b c d e', also 'b f')
#    - Per group captions:
#        - Mutually exclusive (radio group, no: border color)
#        - Boolean (checkbox, no: toggle with different border color)
#        ---> Always like "checkbox"

#    - Adding captions to groups / Removing captions from groups
#    - Save/load caption presets

# Button: Apply Rules
#    - Matches captions and sorts them
#    - Removes mutually exclusive captions as defined by groups
#    - Deletes banned captions

class CaptionControl(QtWidgets.QTabWidget):
    captionClicked = Signal(str)
    separatorChanged = Signal(str)

    def __init__(self, container):
        super().__init__()
        self._container = container
        self.bannedSeparator = ', '

        self._defaultPresetPath = self._container.tab.export.basePath

        self._settingsWidget = self._buildSettings()
        self._groupsWidget = self._buildGroups()
        self.addTab(self._settingsWidget, "Settings")
        self.addTab(self._groupsWidget, "Caption")
        self.addTab(QtWidgets.QWidget(), "Batch Process")
        self.addTab(QtWidgets.QWidget(), "Generate")


    def _buildSettings(self):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignTop)

        # Row 0
        self.txtPrefix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtPrefix)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        qtlib.setShowWhitespace(self.txtPrefix)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), 0, 0, Qt.AlignTop)
        layout.addWidget(self.txtPrefix, 0, 1, Qt.AlignTop)

        self.txtSuffix = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtSuffix)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        qtlib.setShowWhitespace(self.txtSuffix)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), 0, 2, Qt.AlignTop)
        layout.addWidget(self.txtSuffix, 0, 3, Qt.AlignTop)

        # Row 1
        self.txtSeparator = QtWidgets.QLineEdit(", ")
        self.txtSeparator.editingFinished.connect(lambda: self.separatorChanged.emit(self.txtSeparator.text()))
        qtlib.setMonospace(self.txtSeparator)
        layout.addWidget(QtWidgets.QLabel("Separator:"), 1, 0, Qt.AlignTop)
        layout.addWidget(self.txtSeparator, 1, 1, Qt.AlignTop)

        self.txtBanned = QtWidgets.QPlainTextEdit()
        qtlib.setMonospace(self.txtBanned)
        qtlib.setTextEditHeight(self.txtBanned, 3)
        layout.addWidget(QtWidgets.QLabel("Banned:"), 1, 2, Qt.AlignTop)
        layout.addWidget(self.txtBanned, 1, 3, 2, 1, Qt.AlignTop)

        # Row 2
        self.chkAutoApply = QtWidgets.QCheckBox("Auto apply rules")
        self.chkRemoveDup = QtWidgets.QCheckBox("Remove duplicates")
        self.chkRemoveDup.setChecked(True)
        
        rowLayout = QtWidgets.QHBoxLayout()
        rowLayout.addWidget(self.chkAutoApply)
        rowLayout.addWidget(self.chkRemoveDup)
        layout.addLayout(rowLayout, 2, 0, 1, 2, Qt.AlignTop)

        btnAddBanned = QtWidgets.QPushButton("Ban")
        btnAddBanned.setFixedWidth(50)
        btnAddBanned.setFocusPolicy(Qt.NoFocus)
        btnAddBanned.clicked.connect(self.addBanned)
        layout.addWidget(btnAddBanned, 2, 2, Qt.AlignTop)
        
        # Row 3
        self.btnLoad = QtWidgets.QPushButton("Load preset ...")
        self.btnLoad.clicked.connect(self.loadPreset)
        layout.addWidget(self.btnLoad, 3, 0, 1, 2, Qt.AlignTop)

        self.btnSave = QtWidgets.QPushButton("Save preset as ...")
        self.btnSave.clicked.connect(self.savePreset)
        layout.addWidget(self.btnSave, 3, 2, 1, 2, Qt.AlignTop)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    def _buildGroups(self):
        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setContentsMargins(0, 0, 0, 0)

        btnAddGroup = QtWidgets.QPushButton("Add Group")
        btnAddGroup.clicked.connect(self.addGroup)
        self.groupLayout.addWidget(btnAddGroup)

        widget = QtWidgets.QWidget()
        widget.setLayout(self.groupLayout)
        return widget


    @property
    def prefix(self) -> str:
        return self.txtPrefix.toPlainText()

    @property
    def suffix(self) -> str:
        return self.txtSuffix.toPlainText()

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

    def getCaptionGroups(self) -> list[CaptionControlGroup]:
        groups = []
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                groups.append(widget)
        return groups


    @Slot()
    def addGroup(self):
        group = CaptionControlGroup(self, "Group")
        index = self.groupLayout.count() - 1 # Insert before button
        self.groupLayout.insertWidget(index, group)
        return group

    def removeGroup(self, group):
        dialog = QtWidgets.QMessageBox()
        dialog.setIcon(QtWidgets.QMessageBox.Question)
        dialog.setWindowTitle("Confirm group removal")
        dialog.setText(f"Remove group: {group.name}")
        dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        if dialog.exec() == QtWidgets.QMessageBox.Yes:
            self.groupLayout.removeWidget(group)
            group.deleteLater()

    def removeAllGroups(self):
        widgets = []
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                widgets.append(widget)

        for w in widgets:
            self.groupLayout.removeWidget(w)
            w.deleteLater()

    def moveGroup(self, group, move: int):
        count = self.groupLayout.count()
        index = self.groupLayout.indexOf(group)
        index += move
        if index >= 0 and index < count-1: # There's also a button at the bottom
            self.groupLayout.insertWidget(index, group)

    @Slot()
    def addBanned(self):
        caption = self._container.getSelectedCaption()
        text = self.txtBanned.toPlainText()
        if text:
            text += self.bannedSeparator
        text += caption
        self.txtBanned.setPlainText(text)
    
    @Slot()
    def savePreset(self):
        preset = CaptionPreset()
        preset.prefix = self.txtPrefix.toPlainText()
        preset.suffix = self.txtSuffix.toPlainText()
        preset.separator = self.txtSeparator.text()
        preset.autoApplyRules = self.chkAutoApply.isChecked()
        preset.removeDuplicates = self.chkRemoveDup.isChecked()
        preset.banned = self.bannedCaptions

        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                preset.addGroup(widget.name, widget.mutuallyExclusive, widget.captions)

        fileFilter = "JSON (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getSaveFileName(self, "Save preset", self._defaultPresetPath, fileFilter)
        if path:
            self._defaultPresetPath = os.path.dirname(path)
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
        self.chkAutoApply.setChecked(preset.autoApplyRules)
        self.chkRemoveDup.setChecked(preset.removeDuplicates)
        self.bannedCaptions = preset.banned

        self.removeAllGroups()
        for group in preset.groups:
            groupWidget = self.addGroup()
            groupWidget.name = group.name
            groupWidget.mutuallyExclusive = group.mutuallyExclusive
            for caption in group.captions:
                groupWidget.addCaption(caption)



class CaptionControlGroup(QtWidgets.QFrame):
    def __init__(self, captionControl, name):
        super().__init__()
        self._captionControl = captionControl
        self.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Raised)

        self._buildHeaderWidget(name)

        self.buttonLayout = qtlib.FlowLayout(spacing=1)
        self.buttonWidget = QtWidgets.QWidget()
        self.buttonWidget.setLayout(self.buttonLayout)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.headerWidget)
        layout.addWidget(self.buttonWidget)
        self.setLayout(layout)

    def _buildHeaderWidget(self, name):
        self.txtName = QtWidgets.QLineEdit(name)
        qtlib.setMonospace(self.txtName, 1.2, bold=True)

        btnAddCaption = QtWidgets.QPushButton("Add Caption")
        btnAddCaption.clicked.connect(self._addCaption)
        btnAddCaption.setFocusPolicy(Qt.NoFocus)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually Exclusive")

        btnMoveGroupUp = QtWidgets.QPushButton("Up")
        btnMoveGroupUp.clicked.connect(lambda: self._captionControl.moveGroup(self, -1))

        btnMoveGroupDown = QtWidgets.QPushButton("Down")
        btnMoveGroupDown.clicked.connect(lambda: self._captionControl.moveGroup(self, 1))

        btnRemoveGroup = QtWidgets.QPushButton("Remove Group")
        btnRemoveGroup.clicked.connect(lambda: self._captionControl.removeGroup(self))

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(self.txtName)
        
        self.headerLayout.addWidget(btnAddCaption)
        self.headerLayout.addWidget(self.chkExclusive)
        self.headerLayout.addStretch()
        self.headerLayout.addWidget(btnMoveGroupUp)
        self.headerLayout.addWidget(btnMoveGroupDown)
        self.headerLayout.addWidget(btnRemoveGroup)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)

    @property
    def name(self) -> str:
        return self.txtName.text()

    @name.setter
    def name(self, name):
        self.txtName.setText(name)

    @property
    def mutuallyExclusive(self) -> bool:
        return self.chkExclusive.isChecked()

    @mutuallyExclusive.setter
    def mutuallyExclusive(self, checked):
        self.chkExclusive.setChecked(checked)

    @property
    def captions(self) -> list:
        captions = []
        for i in range(self.buttonLayout.count()):
            widget = self.buttonLayout.itemAt(i).widget()
            if widget and isinstance(widget, qtlib.EditablePushButton):
                captions.append(widget.text)
        return captions
    
    def addCaption(self, text):
        button = qtlib.EditablePushButton(text)
        button.button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._captionControl.captionClicked)
        button.textEmpty.connect(self._removeCaption)
        self.buttonLayout.addWidget(button)
        return button
    
    @Slot()
    def _addCaption(self):
        caption = self._captionControl._container.getSelectedCaption()
        button = self.addCaption(caption)
        #button.setEditMode()

    @Slot()
    def _removeCaption(self, button):
        self.buttonLayout.removeWidget(button)
        button.deleteLater()

    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.