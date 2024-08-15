
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal
import qtlib


class CaptionControl(QtWidgets.QTabWidget):
    captionClicked = Signal(str)

    def __init__(self, container):
        super().__init__()
        self._container = container
        self._settingsWidget = self._buildSettings()
        self._groupsWidget = self._buildGroups()
        self._bannedWidget = self._buildBanned()
        self.addTab(self._settingsWidget, "Settings")
        self.addTab(self._groupsWidget, "Groups")
        self.addTab(self._bannedWidget, "Banned")


    def _buildSettings(self):
        layout = QtWidgets.QGridLayout()

        # Row 0
        self.txtPrefix = QtWidgets.QTextEdit()
        self.txtPrefix.setAcceptRichText(False)
        qtlib.setTextEditHeight(self.txtPrefix, 2)
        layout.addWidget(QtWidgets.QLabel("Prefix:"), 0, 0)
        layout.addWidget(self.txtPrefix, 0, 1)

        self.txtSuffix = QtWidgets.QTextEdit()
        self.txtSuffix.setAcceptRichText(False)
        qtlib.setTextEditHeight(self.txtSuffix, 2)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), 0, 2)
        layout.addWidget(self.txtSuffix, 0, 3)
        
        # Row 1
        self.chkAutoApply = QtWidgets.QCheckBox("Auto apply rules")
        layout.addWidget(self.chkAutoApply, 1, 0, 1, 2)

        self.chkRemoveDup = QtWidgets.QCheckBox("Remove duplicates")
        layout.addWidget(self.chkRemoveDup, 1, 2, 1, 2)
        
        # Row 2
        self.btnLoad = QtWidgets.QPushButton("Load preset ...")
        layout.addWidget(self.btnLoad, 2, 0, 1, 2)

        self.btnSave = QtWidgets.QPushButton("Save preset as ...")
        layout.addWidget(self.btnSave, 2, 2, 1, 2)

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

    def _buildBanned(self):
        layout = QtWidgets.QVBoxLayout()

        self.txtBanned = QtWidgets.QTextEdit()
        self.txtBanned.setAcceptRichText(False)
        layout.addWidget(self.txtBanned)

        btnAddBanned = QtWidgets.QPushButton("Add banned caption")
        btnAddBanned.setFocusPolicy(Qt.NoFocus)
        btnAddBanned.clicked.connect(self.addBanned)
        layout.addWidget(btnAddBanned)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        return widget

    @Slot()
    def addGroup(self):
        group = CaptionControlGroup("Group", self.captionClicked, self._container)
        group.remove.connect(self.removeGroup)
        index = self.groupLayout.count() - 1
        self.groupLayout.insertWidget(index, group)

    @Slot()
    def removeGroup(self, group):
        dialog = QtWidgets.QMessageBox()
        dialog.setIcon(QtWidgets.QMessageBox.Question)
        dialog.setWindowTitle("Confirm group removal")
        dialog.setText(f"Remove group: {group.name}")
        dialog.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        if dialog.exec() == QtWidgets.QMessageBox.Yes:
            self.groupLayout.removeWidget(group)
            group.deleteLater()

    @Slot()
    def addBanned(self):
        caption = self._container.getSelectedCaption()
        text = self.txtBanned.toPlainText()
        if text:
            text += ", "
        text += caption
        self.txtBanned.setPlainText(text)




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


class CaptionControlGroup(QtWidgets.QFrame):
    remove = Signal(object)

    def __init__(self, name, signal, container):
        super().__init__()
        self._clickedSignal = signal
        self._container = container
        self.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Raised)

        self._buildHeaderWidget(name)

        self.buttonLayout = qtlib.FlowLayout()
        self.buttonWidget = QtWidgets.QWidget()
        self.buttonWidget.setLayout(self.buttonLayout)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.headerWidget)
        layout.addWidget(self.buttonWidget)
        self.setLayout(layout)

    def _buildHeaderWidget(self, name):
        self.txtName = QtWidgets.QLineEdit(name)
        font = self.txtName.font()
        font.setPointSizeF(font.pointSizeF() * 1.2)
        font.setBold(True)
        self.txtName.setFont(font)

        btnAddCaption = QtWidgets.QPushButton("Add Caption")
        btnAddCaption.clicked.connect(self._addCaption)
        btnAddCaption.setFocusPolicy(Qt.NoFocus)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually Exclusive")

        btnRemoveGroup = QtWidgets.QPushButton("Remove Group")
        btnRemoveGroup.clicked.connect(lambda: self.remove.emit(self))

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(self.txtName)
        
        self.headerLayout.addWidget(btnAddCaption)
        self.headerLayout.addWidget(self.chkExclusive)
        self.headerLayout.addStretch()
        self.headerLayout.addWidget(btnRemoveGroup)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)

    @property
    def name(self):
        return self.txtName.text()
    
    def addCaption(self, text):
        button = qtlib.EditablePushButton(text)
        button.button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._clickedSignal)
        button.textEmpty.connect(self._removeCaption)
        self.buttonLayout.addWidget(button)
        return button
    
    @Slot()
    def _addCaption(self):
        caption = self._container.getSelectedCaption()
        button = self.addCaption(caption)
        #button.setEditMode()

    @Slot()
    def _removeCaption(self, button):
        self.buttonLayout.removeWidget(button)
        button.deleteLater()

    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.