from typing import ForwardRef
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from lib import qtlib, util

CaptionControlGroup = ForwardRef('CaptionControlGroup')


# TODO?: Per group matching method:
# - exact match (str1 == str2)
# - substring ('b c' in 'a b c d e', but not 'b d')
# - all words ('b c' in 'a b c d e', but not 'b f')
# - any word  ('b d' in 'a b c d e', also 'b f')

class CaptionGroups(QtWidgets.QWidget):
    HUE_OFFSET = 0.3819444 # 1.0 - inverted golden ratio, ~137.5°

    def __init__(self, context):
        super().__init__()
        self.ctx = context
        self._nextGroupHue = util.rnd01()

        self._build()
        self.addGroup()


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 0)
        layout.setColumnStretch(2, 1)
        layout.setColumnStretch(3, 0)
        layout.setColumnStretch(4, 0)
        layout.setColumnMinimumWidth(0, 40)
        layout.setColumnMinimumWidth(1, 12)
        layout.setColumnMinimumWidth(3, 12)
        layout.setColumnMinimumWidth(4, 40)

        row = 0
        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self.groupLayout, row, 0, 1, 5)

        row += 1
        layout.addWidget(Trash(), row, 0)

        btnAddGroup = QtWidgets.QPushButton("✚ Add Group")
        btnAddGroup.clicked.connect(self.addGroup)
        layout.addWidget(btnAddGroup, row, 2)

        layout.addWidget(Trash(), row, 4)

        self.setLayout(layout)


    @property
    def groups(self):
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                yield widget

    @Slot()
    def addGroup(self):
        group = CaptionControlGroup(self, "Group")
        group.color = util.hsv_to_rgb(self._nextGroupHue, 0.5, 0.25)
        self._nextGroupHue += self.HUE_OFFSET

        index = self.groupLayout.count()
        self.groupLayout.insertWidget(index, group)
        self.ctx.controlUpdated.emit()
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
            self._emitUpdatedApplyRules()

    def removeAllGroups(self):
        for widget in list(self.groups):
            self.groupLayout.removeWidget(widget)
            widget.deleteLater()

        self.ctx.controlUpdated.emit()

    def moveGroup(self, group, move: int):
        count = self.groupLayout.count()
        index = self.groupLayout.indexOf(group)
        index += move
        if 0 <= index < count:
            self.groupLayout.insertWidget(index, group)
            self._emitUpdatedApplyRules()


    def getCaptionColors(self):
        colors = {
            caption: group.color
            for group in self.groups
            for caption in group.captions
        }
        
        for banned in self.ctx.settings.bannedCaptions:
            colors[banned] = "#454545"
        return colors

    def getCaptionCharFormats(self) -> dict[str, QtGui.QTextCharFormat]:
        formats = {
            caption: group.charFormat
            for group in self.groups
            for caption in group.captions
        }

        bannedFormat = QtGui.QTextCharFormat()
        bannedFormat.setForeground(QtGui.QColor.fromHsvF(0, 0, 0.5))
        for banned in self.ctx.settings.bannedCaptions:
            formats[banned] = bannedFormat
        
        return formats


    def updateSelectedState(self, text):
        separator = self.ctx.settings.separator.strip()
        captions = { c.strip() for c in text.split(separator) }
        for group in self.groups:
            group.updateSelectedState(captions)
    

    def _emitUpdatedApplyRules(self):
        self.ctx.controlUpdated.emit()
        self.ctx.needsRulesApplied.emit()


    def saveToPreset(self, preset):
        for group in self.groups:
            preset.addGroup(group.name, group.color, group.mutuallyExclusive, group.captions)

    def loadFromPreset(self, preset):
        self.removeAllGroups()
        for group in preset.groups:
            groupWidget = self.addGroup()
            groupWidget.name = group.name
            groupWidget.color = group.color
            groupWidget.mutuallyExclusive = group.mutuallyExclusive
            for caption in group.captions:
                groupWidget.addCaption(caption)

            self._nextGroupHue = util.get_hue(group.color) + self.HUE_OFFSET


class CaptionControlGroup(QtWidgets.QFrame):
    def __init__(self, groups, name):
        super().__init__()
        self.groups = groups
        self.charFormat = QtGui.QTextCharFormat()
        self.setFrameStyle(QtWidgets.QFrame.Shape.Box | QtWidgets.QFrame.Shadow.Sunken)

        self._buildHeaderWidget(name)

        self.buttonLayout = qtlib.FlowLayout(spacing=1)
        self.buttonWidget = qtlib.ReorderWidget(giveDrop=True)
        self.buttonWidget.setLayout(self.buttonLayout)
        self.buttonWidget.setMinimumHeight(14)
        self.buttonWidget.orderChanged.connect(self.groups.ctx.needsRulesApplied)
        self.buttonWidget.dataCallback = lambda widget: widget.text
        self.buttonWidget.dropCallback = self._addCaptionDrop
        self.buttonWidget.updateCallback = self.groups._emitUpdatedApplyRules

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(self.headerWidget)
        layout.addWidget(self.buttonWidget)
        self.setLayout(layout)

    def _buildHeaderWidget(self, name):
        self.txtColor = QtWidgets.QLineEdit()
        self.txtColor.textChanged.connect(self._updateColor)
        self.txtColor.setFixedWidth(60)
        qtlib.setMonospace(self.txtColor, 0.8)
        self.color = "#000"

        self.txtName = QtWidgets.QLineEdit(name)
        self.txtName.setMinimumWidth(160)
        self.txtName.setMaximumWidth(300)
        qtlib.setMonospace(self.txtName, 1.2, bold=True)

        btnAddCaption = QtWidgets.QPushButton("Add Caption")
        btnAddCaption.clicked.connect(self._addCaptionClick)
        btnAddCaption.setFocusPolicy(Qt.NoFocus)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually Exclusive")

        btnMoveGroupUp = QtWidgets.QPushButton("Up")
        btnMoveGroupUp.clicked.connect(lambda: self.groups.moveGroup(self, -1))

        btnMoveGroupDown = QtWidgets.QPushButton("Down")
        btnMoveGroupDown.clicked.connect(lambda: self.groups.moveGroup(self, 1))

        btnRemoveGroup = QtWidgets.QPushButton("Remove Group")
        btnRemoveGroup.clicked.connect(lambda: self.groups.removeGroup(self))

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(self.txtColor)
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
    

    def updateSelectedState(self, captions: set):
        color = self.color
        for button in self.buttons:
            text = button.text.strip()
            if text in captions:
                button.setStyleSheet("color: #fff; background-color: " + color + "; border: 3px solid " + color + "; border-radius: 8px")
            else:
                button.setStyleSheet("color: #fff; background-color: #161616; border: 3px solid #161616; border-radius: 8px")


    @property
    def buttons(self):
        for i in range(self.buttonLayout.count()):
            widget = self.buttonLayout.itemAt(i).widget()
            if widget and isinstance(widget, qtlib.EditablePushButton):
                yield widget


    @property
    def name(self) -> str:
        return self.txtName.text()

    @name.setter
    def name(self, name):
        self.txtName.setText(name)

    @property
    def color(self) -> str:
        return self.txtColor.text()

    @color.setter
    def color(self, color):
        self.txtColor.setText(color)
        self._updateCharFormat(color)


    @Slot()
    def _updateColor(self, color):
        if util.isValidColor(color):
            self.txtColor.setStyleSheet(f"color: #fff; background-color: {color}")
            self._updateCharFormat(color)
            self.groups.ctx.controlUpdated.emit()
    
    def _updateCharFormat(self, color):
        self.charFormat.setForeground( qtlib.getHighlightColor(color) )


    @property
    def mutuallyExclusive(self) -> bool:
        return self.chkExclusive.isChecked()

    @mutuallyExclusive.setter
    def mutuallyExclusive(self, checked):
        self.chkExclusive.setChecked(checked)

    @property
    def captions(self) -> list:
        return [button.text for button in self.buttons]
    
    def addCaption(self, text):
        # Check if caption already exists in group
        for button in self.buttons:
            if text == button.text:
                return False

        button = qtlib.EditablePushButton(text, lambda w: qtlib.setMonospace(w, 1.05))
        button.button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self.groups.ctx.captionClicked)
        button.textEmpty.connect(self._removeCaption)
        button.textChanged.connect(lambda: self.groups._emitUpdatedApplyRules())
        self.buttonLayout.addWidget(button)
        return True
    
    @Slot()
    def _addCaptionClick(self):
        text = self.groups.ctx.getSelectedCaption()
        self._addCaptionDrop(text)

    def _addCaptionDrop(self, text):
        if self.addCaption(text):
            self.groups._emitUpdatedApplyRules()
        return True # Take drop

    @Slot()
    def _removeCaption(self, button):
        self.buttonLayout.removeWidget(button)
        button.deleteLater()
        self.groups._emitUpdatedApplyRules()

    def resizeEvent(self, event):
        self.layout().update()  # Weird: Needed for proper resize.



class Trash(QtWidgets.QLabel):
    def __init__(self):
        super().__init__("🗑")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Drag tags here to delete them")

        self.setHover(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self.setHover(True)
            event.accept()

    def dragLeaveEvent(self, event):
        self.setHover(False)
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        self.setHover(False)
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def setHover(self, hover: bool):
        style = "border: 1px solid #333333; font-size: 18px"
        if hover:
            style += "; background: #801616"

        self.setStyleSheet("QLabel{" + style + "}")
