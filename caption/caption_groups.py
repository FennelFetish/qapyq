from typing import ForwardRef
from PySide6 import QtWidgets
from PySide6.QtCore import Qt, Slot
import qtlib, util

CaptionControlGroup = ForwardRef('CaptionControlGroup')


# TODO?: Per group matching method:
# - exact match (str1 == str2)
# - substring ('b c' in 'a b c d e', but not 'b d')
# - all words ('b c' in 'a b c d e', but not 'b f')
# - any word  ('b d' in 'a b c d e', also 'b f')

class CaptionGroups(QtWidgets.QWidget):
    def __init__(self, context):
        super().__init__()
        self.ctx = context

        self._build()
        self.addGroup()


    def _build(self):
        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setAlignment(Qt.AlignBottom)
        self.groupLayout.setContentsMargins(0, 0, 0, 0)

        btnAddGroup = QtWidgets.QPushButton("Add Group")
        btnAddGroup.clicked.connect(self.addGroup)
        self.groupLayout.addWidget(btnAddGroup)

        self.setLayout(self.groupLayout)


    @property
    def groups(self):
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                yield widget

    @Slot()
    def addGroup(self):
        group = CaptionControlGroup(self, "Group")
        index = self.groupLayout.count() - 1 # Insert before button
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
        if index >= 0 and index < count-1: # There's also a button at the bottom
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



class CaptionControlGroup(QtWidgets.QFrame):
    _nextHue = util.rnd01()

    def __init__(self, groups, name):
        super().__init__()
        self.groups = groups
        self.setFrameStyle(QtWidgets.QFrame.Panel | QtWidgets.QFrame.Raised)

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
        self.color = util.hsv_to_rgb(CaptionControlGroup._nextHue, 0.5, 0.25)
        CaptionControlGroup._nextHue += 0.3819444

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
        for i in range(self.buttonLayout.count()):
            widget = self.buttonLayout.itemAt(i).widget()
            if widget and isinstance(widget, qtlib.EditablePushButton):
                text = widget.text.strip()
                if text in captions:
                    widget.setStyleSheet("color: #fff; background-color: " + color + "; border: 3px solid " + color + "; border-radius: 8px")
                else:
                    widget.setStyleSheet("color: #fff; background-color: #161616; border: 3px solid #161616; border-radius: 8px")


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
        
    @Slot()
    def _updateColor(self, color):
        if util.isValidColor(color):
            self.txtColor.setStyleSheet(f"color: #fff; background-color: {color}")
            self.groups.ctx.controlUpdated.emit()

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
        # Check if caption already exists in group
        for i in range(self.buttonLayout.count()):
            widget = self.buttonLayout.itemAt(i).widget()
            if widget and isinstance(widget, qtlib.EditablePushButton) and text == widget.text:
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
