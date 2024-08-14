
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal
from qtlib import FlowLayout, EditablePushButton


class CaptionControl(QtWidgets.QWidget):
    captionClicked = Signal(str)

    def __init__(self):
        super().__init__()

        self.baseControls = self._buildBaseControls()

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.baseControls)

        group1 = CaptionControlGroup("Hair", self.captionClicked)
        group1.addCaption("blonde hair")
        group1.addCaption("brunette hair")
        group1.addCaption("black hair")
        layout.addWidget(group1)

        group2 = CaptionControlGroup("Pose", self.captionClicked)
        group2.addCaption("standing")
        group2.addCaption("sitting")
        group2.addCaption("laying")
        layout.addWidget(group2)

        self.setLayout(layout)
    
    def _buildBaseControls(self):
        self.txtPrefix = QtWidgets.QLineEdit()
        self.txtSuffix = QtWidgets.QLineEdit()
        
        layout = QtWidgets.QGridLayout()
        layout.addWidget(QtWidgets.QLabel("Prefix:"), 0, 0)
        layout.addWidget(self.txtPrefix, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Suffix:"), 0, 2)
        layout.addWidget(self.txtSuffix, 0, 3)

        widget = QtWidgets.QGroupBox("Basic")
        widget.setLayout(layout)
        return widget


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
    def __init__(self, title, signal):
        super().__init__()
        self._clickedSignal = signal
        self.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Raised)

        self._buildHeaderWidget(title)

        self.buttonLayout = FlowLayout()
        self.buttonWidget = QtWidgets.QWidget()
        self.buttonWidget.setLayout(self.buttonLayout)

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.headerWidget)
        layout.addWidget(self.buttonWidget)
        self.setLayout(layout)

    def _buildHeaderWidget(self, title):
        lblTitle = QtWidgets.QLabel(title)
        font = lblTitle.font()
        font.setPointSizeF(font.pointSizeF() * 1.2)
        font.setBold(True)
        lblTitle.setFont(font)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually Exclusive")
        self.btnAddCaption = QtWidgets.QPushButton("Add Caption")
        self.btnAddCaption.clicked.connect(self._addCaption)

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(lblTitle)
        self.headerLayout.addStretch()
        self.headerLayout.addWidget(self.chkExclusive)
        self.headerLayout.addWidget(self.btnAddCaption)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)
    
    def addCaption(self, text):
        button = EditablePushButton(text)
        button.button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._clickedSignal)
        button.textEmpty.connect(self._removeCaption)
        self.buttonLayout.addWidget(button)
        return button
    
    @Slot()
    def _addCaption(self):
        button = self.addCaption("")
        button.setEditMode()

    @Slot()
    def _removeCaption(self, button):
        self.buttonLayout.removeWidget(button)
        button.deleteLater()

    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.