from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot
from lib import qtlib, util
from .caption_preset import CaptionPreset


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
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
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
        self.groupLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groupLayout.setContentsMargins(0, 0, 0, 0)
        self.groupLayout.setSpacing(0)

        self.groupWidget = GroupReorderWidget()
        self.groupWidget.setLayout(self.groupLayout)
        self.groupWidget.orderChanged.connect(self._emitUpdatedApplyRules)
        scrollGroup = qtlib.BaseColorScrollArea(self.groupWidget)
        scrollGroup.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        layout.addWidget(scrollGroup, row, 0, 1, 5)

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
        dialog = QtWidgets.QMessageBox(group)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm group removal")
        dialog.setText(f"Remove group: {group.name}")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.groupLayout.removeWidget(group)
            group.deleteLater()
            self._emitUpdatedApplyRules()

    def removeAllGroups(self):
        for widget in list(self.groups):
            self.groupLayout.removeWidget(widget)
            widget.deleteLater()

        self.ctx.controlUpdated.emit()

    # def moveGroup(self, group, move: int):
    #     count = self.groupLayout.count()
    #     index = self.groupLayout.indexOf(group)
    #     index += move
    #     if 0 <= index < count:
    #         self.groupLayout.insertWidget(index, group)
    #         self._emitUpdatedApplyRules()


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
    

    @Slot()
    def _emitUpdatedApplyRules(self):
        self.ctx.controlUpdated.emit()
        self.ctx.needsRulesApplied.emit()


    def saveToPreset(self, preset: CaptionPreset):
        for group in self.groups:
            preset.addGroup(group.name, group.color, group.mutuallyExclusive, group.combineTags, group.captions)

    def loadFromPreset(self, preset: CaptionPreset):
        self.removeAllGroups()
        for group in preset.groups:
            groupWidget: CaptionControlGroup = self.addGroup()
            groupWidget.name = group.name
            groupWidget.color = group.color
            groupWidget.mutuallyExclusive = group.mutuallyExclusive
            groupWidget.combineTags = group.combineTags
            for caption in group.captions:
                groupWidget.addCaption(caption)

            self._nextGroupHue = util.get_hue(group.color) + self.HUE_OFFSET



class CaptionControlGroup(QtWidgets.QWidget):
    def __init__(self, groups: CaptionGroups, name: str):
        super().__init__()
        self.groups = groups
        self.charFormat = QtGui.QTextCharFormat()
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)

        self._buildHeaderWidget(name)

        self.buttonLayout = qtlib.FlowLayout(spacing=1)
        self.buttonWidget = qtlib.ReorderWidget(giveDrop=True)
        self.buttonWidget.setLayout(self.buttonLayout)
        self.buttonWidget.setMinimumHeight(14)
        self.buttonWidget.orderChanged.connect(self.groups.ctx.needsRulesApplied)
        self.buttonWidget.dataCallback = lambda widget: widget.text
        self.buttonWidget.dropCallback = self._addCaptionDrop
        self.buttonWidget.updateCallback = self.groups._emitUpdatedApplyRules

        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(3, 5, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(GroupDragHandle(self, self.groups.groupWidget), 0, 0, 2, 1)
        layout.setColumnMinimumWidth(0, 10)
        layout.addWidget(self.headerWidget, 0, 1)
        layout.addWidget(self.buttonWidget, 1, 1)

        layout.setRowMinimumHeight(2, 3)
        layout.addWidget(separatorLine, 3, 0, 1, 2)

        self.setLayout(layout)

    def _buildHeaderWidget(self, name):
        self.colorWidget = GroupColor(self)

        self.txtName = QtWidgets.QLineEdit(name)
        self.txtName.setMinimumWidth(160)
        self.txtName.setMaximumWidth(300)
        qtlib.setMonospace(self.txtName, 1.2, bold=True)

        btnAddCaption = QtWidgets.QPushButton("Add Caption")
        btnAddCaption.clicked.connect(self._addCaptionClick)
        btnAddCaption.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.chkExclusive = QtWidgets.QCheckBox("Mutually Exclusive")
        self.chkCombine = QtWidgets.QCheckBox("Combine Tags")

        btnRemoveGroup = QtWidgets.QPushButton("Remove Group")
        btnRemoveGroup.clicked.connect(lambda: self.groups.removeGroup(self))

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(self.colorWidget)
        self.headerLayout.addWidget(self.txtName)
        self.headerLayout.addWidget(btnAddCaption)
        self.headerLayout.addWidget(self.chkExclusive)
        self.headerLayout.addWidget(self.chkCombine)
        self.headerLayout.addStretch()

        self.headerLayout.addWidget(btnRemoveGroup)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)


    # TODO: When 'combine tags' is enabled, match: *prefix words* word
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
        return self.colorWidget.color

    @color.setter
    def color(self, color):
        self.colorWidget.color = color


    def _updateCharFormat(self, color):
        self.charFormat.setForeground( qtlib.getHighlightColor(color) )


    @property
    def mutuallyExclusive(self) -> bool:
        return self.chkExclusive.isChecked()

    @mutuallyExclusive.setter
    def mutuallyExclusive(self, checked: bool):
        self.chkExclusive.setChecked(checked)


    @property
    def combineTags(self) -> bool:
        return self.chkCombine.isChecked()
    
    @combineTags.setter
    def combineTags(self, checked: bool):
        self.chkCombine.setChecked(checked)


    @property
    def captions(self) -> list:
        return [button.text for button in self.buttons]
    
    def addCaption(self, text):
        # Check if caption already exists in group
        for button in self.buttons:
            if text == button.text:
                return False

        button = qtlib.EditablePushButton(text, lambda w: qtlib.setMonospace(w, 1.05))
        button.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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
        self.buttonLayout.update()  # Weird: Needed for proper resize.



class GroupColor(QtWidgets.QFrame):
    def __init__(self, group: CaptionControlGroup):
        super().__init__()
        self.group = group
        self._color = "#000"

        self.setToolTip("Choose Color")
        self.setMinimumWidth(30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setFrameShape(QtWidgets.QFrame.Shape.Box)
        self.setFrameShadow(QtWidgets.QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setMidLineWidth(0)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        color = QtWidgets.QColorDialog.getColor(self.color, self, f"Choose Color for '{self.group.name}'")
        if color.isValid():
            self.color = color.name()

    @property
    def color(self) -> str:
        return self._color
    
    @color.setter
    def color(self, color: str):
        if not util.isValidColor(color):
            return

        self._color = color
        self.setStyleSheet(".GroupColor{background-color: " + color + "}")
        self.group._updateCharFormat(color)
        self.group.groups.ctx.controlUpdated.emit()



class GroupReorderWidget(qtlib.ReorderWidget):
    def __init__(self):
        super().__init__(False)
        self.showCursorPicture = False

    def dragEnterEvent(self, e):
        if not e.mimeData().hasText():
            e.accept()

    def mouseMoveEvent(self, e):
        pass



class GroupDragHandle(QtWidgets.QWidget):
    def __init__(self, group: CaptionControlGroup, reorderWidget: GroupReorderWidget):
        super().__init__()
        self.group = group
        self.reorderWidget = reorderWidget

        self.setContentsMargins(0, 0, 0, 0)
        self.setCursor(Qt.CursorShape.DragMoveCursor)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._buildFrame())
        layout.addWidget(self._buildFrame())
        self.setLayout(layout)

    def _buildFrame(self):
        frame = QtWidgets.QFrame()
        frame.setFixedWidth(2)
        frame.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        frame.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        frame.setLineWidth(1)
        frame.setMidLineWidth(1)
        return frame

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.reorderWidget._startDrag(self.group)



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
