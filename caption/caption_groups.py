from __future__ import annotations
from collections import Counter
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal
from lib import qtlib, util, colors
from ui.flow_layout import FlowLayout, ReorderWidget, ManualStartReorderWidget, ReorderDragHandle
from .caption_tab import CaptionTab
from .caption_preset import CaptionPreset, MutualExclusivity
from .caption_wildcard import WildcardWindow, expandWildcards


# TODO?: Per group matching method:
# - exact match (str1 == str2)
# - substring ('b c' in 'a b c d e', but not 'b d')
# - all words ('b c' in 'a b c d e', but not 'b f')
# - any word  ('b d' in 'a b c d e', also 'b f')


class CaptionGroups(CaptionTab):
    HUE_OFFSET = 0.3819444 # 1.0 - inverted golden ratio, ~137.5°

    def __init__(self, context):
        super().__init__(context)

        self.wildcards: dict[str, list[str]] = dict()
        self._nextGroupHue = util.rnd01()

        self._build()
        self.addGroup()


    def _build(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.groupLayout = QtWidgets.QVBoxLayout()
        self.groupLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.groupLayout.setContentsMargins(0, 0, 0, 0)
        self.groupLayout.setSpacing(0)

        groupReorderWidget = ManualStartReorderWidget()
        groupReorderWidget.setLayout(self.groupLayout)
        groupReorderWidget.orderChanged.connect(self._emitUpdatedApplyRules)
        scrollGroup = qtlib.RowScrollArea(groupReorderWidget, True)
        scrollGroup.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)

        layout.addWidget(scrollGroup)
        layout.addWidget(self._buildBar())
        self.setLayout(layout)

    def _buildBar(self):
        barLayout = QtWidgets.QHBoxLayout()
        barLayout.setContentsMargins(0, 1, 0, 1)
        barLayout.setSpacing(0)

        barLayout.addWidget(Trash())
        barLayout.addSpacing(12)

        btnAddGroup = QtWidgets.QPushButton("✚ Add Group")
        btnAddGroup.clicked.connect(self.addGroup)
        barLayout.addWidget(btnAddGroup, 1)

        barLayout.addSpacing(4)

        btnOpenWildcards = QtWidgets.QPushButton("Wildcards...")
        btnOpenWildcards.setMinimumWidth(100)
        btnOpenWildcards.clicked.connect(self._openWildcardWindow)
        barLayout.addWidget(btnOpenWildcards, 1)

        self.lblStatus = QtWidgets.QLabel()
        barLayout.addWidget(self.lblStatus, 4, Qt.AlignmentFlag.AlignCenter)

        self.filter = qtlib.LayoutFilter(self.groupLayout, self._getFilterTexts)
        self.filter.setStatusLabel("Groups", self.lblStatus)
        barLayout.addLayout(self.filter, 2)

        barLayout.addSpacing(12)
        barLayout.addWidget(Trash())

        frame = QtWidgets.QFrame()
        frame.setFrameStyle(QtWidgets.QFrame.Shape.Panel | QtWidgets.QFrame.Shadow.Sunken)
        frame.setLayout(barLayout)
        return frame


    @Slot()
    def _openWildcardWindow(self):
        win = WildcardWindow(self, self.wildcards)
        if win.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.wildcards = win.wildcards
            self.ctx.controlUpdated.emit()

    @staticmethod
    def _getFilterTexts(group: CaptionControlGroup):
        yield group.name
        yield from group.captionsExpandWildcards


    @property
    def groups(self):
        for i in range(self.groupLayout.count()):
            widget = self.groupLayout.itemAt(i).widget()
            if widget and isinstance(widget, CaptionControlGroup):
                yield widget


    def _createGroup(self):
        group = CaptionControlGroup(self, "Group")
        group.color = util.hsv_to_rgb(self._nextGroupHue, 0.5, 0.25)
        self._nextGroupHue += self.HUE_OFFSET
        return group

    @Slot()
    def addGroup(self):
        group = self._createGroup()
        self.groupLayout.addWidget(group)
        self.filter.updateStatus()
        self.ctx.controlUpdated.emit()
        return group

    def addGroupAt(self, index: int):
        group = self._createGroup()
        self.groupLayout.insertWidget(index, group)
        self.filter.updateStatus()
        self.ctx.controlUpdated.emit()
        return group

    def removeGroup(self, group):
        dialog = QtWidgets.QMessageBox(group)
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowTitle("Confirm group removal")
        dialog.setText(f"Remove group: {group.name}")
        dialog.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)

        if dialog.exec() == QtWidgets.QMessageBox.StandardButton.Yes:
            self.groupLayout.removeWidget(group)
            group.deleteLater()
            self.filter.updateStatus()
            self._emitUpdatedApplyRules()

    def removeAllGroups(self):
        for i in reversed(range(self.groupLayout.count())):
            item = self.groupLayout.takeAt(i)
            if widget := item.widget():
                widget.deleteLater()

        self.filter.clearFilterText()
        self.filter.updateStatus()
        self.ctx.controlUpdated.emit()


    def updateSelectedState(self, captions: list[str], force: bool):
        captionSet = set(self.ctx.highlight.matchNode.splitAll(captions))
        for group in self.groups:
            group.updateSelectedState(captionSet, force)


    @Slot()
    def _emitUpdatedApplyRules(self):
        self.ctx.controlUpdated.emit()
        self.ctx.needsRulesApplied.emit()


    def saveToPreset(self, preset: CaptionPreset):
        preset.wildcards = dict(self.wildcards)
        for group in self.groups:
            preset.addGroup(group.name, group.color, group.exclusivity, group.combineTags, group.captions)

    def loadFromPreset(self, preset: CaptionPreset):
        self.wildcards = dict(preset.wildcards)

        with self.filter.postponeUpdates():
            self.removeAllGroups()
            for group in preset.groups:
                groupWidget: CaptionControlGroup = self.addGroup()
                groupWidget.name = group.name
                groupWidget.color = group.color
                groupWidget.exclusivity = group.exclusivity
                groupWidget.combineTags = group.combineTags
                groupWidget.addAllCaptions(group.captions)

                self._nextGroupHue = util.get_hue(group.color) + self.HUE_OFFSET



# TODO: Add preview for combine-tags (right to the combine checkbox, a disabled QLineEdit so it will not affect minimum window width).
#       Only show it when hovering over the group.
class CaptionControlGroup(QtWidgets.QWidget):
    def __init__(self, groups: CaptionGroups, name: str):
        super().__init__()
        self.groups = groups
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed)

        self._buildHeaderWidget(name)

        self.buttonLayout = FlowLayout(spacing=1)
        self.buttonWidget = ReorderWidget(giveDrop=True, takeDrop=True)
        self.buttonWidget.setLayout(self.buttonLayout)
        self.buttonWidget.setMinimumHeight(14)
        self.buttonWidget.dragStartMinDistance = 6
        self.buttonWidget.dataCallback = lambda widget: widget.text
        self.buttonWidget.orderChanged.connect(self.groups._emitUpdatedApplyRules)
        self.buttonWidget.orderChanged.connect(self._updateCombineWords)
        self.buttonWidget.receivedDrop.connect(self._addCaptionDrop)

        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(3, 5, 5, 0)
        layout.setSpacing(4)

        layout.addWidget(ReorderDragHandle(self), 0, 0, 2, 1)
        layout.setColumnMinimumWidth(0, 10)
        layout.addWidget(self.headerWidget, 0, 1)
        layout.addWidget(self.buttonWidget, 1, 1)

        layout.setRowMinimumHeight(2, 3)
        layout.addWidget(separatorLine, 3, 0, 1, 2)

        self.setLayout(layout)

    def _buildHeaderWidget(self, name):
        self.colorWidget = GroupColor(self)
        self.colorWidget.colorChanged.connect(lambda: self._updateCombineWords())

        self.txtName = QtWidgets.QLineEdit(name)
        self.txtName.setMinimumWidth(160)
        self.txtName.setMaximumWidth(300)
        qtlib.setMonospace(self.txtName, 1.2, bold=True)

        self.cboExclusive = ExclusivityComboBox()
        # Emit signal to update preview, but don't apply rules, as this settings can remove tags.
        self.cboExclusive.currentIndexChanged.connect(lambda: self.groups.ctx.controlUpdated.emit())

        self.chkCombine = QtWidgets.QCheckBox("Combine Tags")
        self.chkCombine.toggled.connect(self._onCombineToggled)

        self.lblCombineWords = QtWidgets.QLabel()
        qtlib.setMonospace(self.lblCombineWords, 0.8)

        btnAddCaption = QtWidgets.QPushButton("Add Tag")
        btnAddCaption.clicked.connect(self._addCaptionClick)
        btnAddCaption.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        btnGroupMenu = QtWidgets.QPushButton("☰")
        btnGroupMenu.setFixedWidth(40)
        btnGroupMenu.setMenu(GroupMenu(self))

        self.headerLayout = QtWidgets.QHBoxLayout()
        self.headerLayout.setContentsMargins(0, 0, 0, 0)
        self.headerLayout.addWidget(self.colorWidget)
        self.headerLayout.addWidget(self.txtName)
        self.headerLayout.addSpacing(8)
        self.headerLayout.addWidget(QtWidgets.QLabel("Mutually Exclusive:"))
        self.headerLayout.addWidget(self.cboExclusive)
        self.headerLayout.addWidget(self.chkCombine)
        self.headerLayout.addWidget(self.lblCombineWords)

        self.headerLayout.addStretch()

        self.headerLayout.addWidget(btnAddCaption)
        self.headerLayout.addWidget(btnGroupMenu)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)


    @property
    def index(self) -> int:
        return self.groups.groupLayout.indexOf(self)


    def updateSelectedState(self, captions: set[str], force: bool):
        enabledColor, disabledColor = self.colorWidget.color, self.colorWidget.disabledColor
        wildcards = self.groups.wildcards

        for button in self.buttons:
            checked = not captions.isdisjoint( expandWildcards(button.text.strip(), wildcards) )
            color = enabledColor if checked else disabledColor
            button.setChecked(checked, color, force)


    @property
    def buttons(self):
        for i in range(self.buttonLayout.count()):
            widget = self.buttonLayout.itemAt(i).widget()
            if widget and isinstance(widget, GroupButton):
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

    @property
    def charFormat(self) -> QtGui.QTextCharFormat:
        return self.colorWidget.charFormat


    @property
    def exclusivity(self) -> MutualExclusivity:
        return self.cboExclusive.currentData()

    @exclusivity.setter
    def exclusivity(self, exclusivity: MutualExclusivity):
        index = self.cboExclusive.findData(exclusivity)
        self.cboExclusive.setCurrentIndex(index)


    @property
    def combineTags(self) -> bool:
        return self.chkCombine.isChecked()

    @combineTags.setter
    def combineTags(self, checked: bool):
        self.chkCombine.setChecked(checked)

    @Slot()
    def _onCombineToggled(self, checked: bool):
        self.chkCombine.setText("Combine Tags:" if checked else "Combine Tags")
        self._updateCombineWords()

        # Emit signal to update preview, but don't apply rules, as this settings can remove tags.
        self.groups.ctx.controlUpdated.emit()

    @Slot()
    def _updateCombineWords(self):
        if not self.combineTags:
            self.lblCombineWords.setText("")
            self.lblCombineWords.setStyleSheet("")
            return

        counter = Counter[tuple[str, str, int]]()
        for button in self.buttons:
            words = [word for word in button.text.strip().split(" ") if word]
            for length in range(len(words)):
                suffixWords = words[length:]
                suffix = " ".join(suffixWords)
                counter[(suffix, words[-1], len(suffixWords))] += 1

        sortedSuffixes = sorted((
            ((suffix, lastWord), (count, suffixLen))
            for (suffix, lastWord, suffixLen), count in counter.items()
            if count > 1
        ), key=lambda entry: entry[1], reverse=True)

        combineWords = list[str]()
        usedLastWords = set[str]()
        for (suffix, lastWord), _ in sortedSuffixes:
            if lastWord not in usedLastWords:
                combineWords.append(suffix)
                usedLastWords.add(lastWord)

        self.lblCombineWords.setText(", ".join(combineWords))
        self.lblCombineWords.setStyleSheet(f"color: {self.colorWidget.highlightColor}")


    @property
    def captions(self) -> list[str]:
        return [button.text for button in self.buttons]

    @property
    def captionsExpandWildcards(self) -> list[str]:
        return [
            tag
            for button in self.buttons
            for tag in expandWildcards(button.text, self.groups.wildcards)
        ]

    def addCaption(self, text: str) -> bool:
        # Check if caption already exists in group
        if any(text == button.text for button in self.buttons):
            return False

        self._addCaption(text)
        self._updateCombineWords()
        return True

    def addAllCaptions(self, captions: list[str]):
        existing = {button.text for button in self.buttons}
        for text in captions:
            if text not in existing:
                existing.add(text)
                self._addCaption(text)

        self._updateCombineWords()

    def _addCaption(self, text: str):
        button = GroupButton(text)
        button.button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.buttonClicked.connect(self._onButtonClicked)
        button.textEmpty.connect(self._removeCaption)
        button.textChanged.connect(lambda: self.groups._emitUpdatedApplyRules())
        self.buttonLayout.addWidget(button)


    @Slot()
    def _addCaptionClick(self):
        text = self.groups.ctx.text.getSelectedCaption()
        self._addCaptionDrop(text)

    @Slot()
    def _addCaptionDrop(self, text: str):
        if self.addCaption(text):
            self.groups._emitUpdatedApplyRules()

    @Slot()
    def _removeCaption(self, button):
        self.buttonLayout.removeWidget(button)
        button.deleteLater()
        self._updateCombineWords()
        self.groups._emitUpdatedApplyRules()


    @Slot()
    def _onButtonClicked(self, button: GroupButton):
        wildcardTags = expandWildcards(button.text, self.groups.wildcards)
        if len(wildcardTags) <= 1:
            self._toggleCaption(button, wildcardTags[0])
            return

        # Build and show menu for expanded wildcards
        textField = self.groups.ctx.text
        captions = textField.getCaption().split(textField.separator.strip())
        captions = (cap for c in captions if (cap := c.strip()))
        captions = set(self.groups.ctx.highlight.matchNode.splitAll(captions))

        menu = QtWidgets.QMenu("Expanded Wildcards")
        for tag in wildcardTags:
            checked = tag in captions
            act = menu.addAction(tag)
            act.setCheckable(True)
            act.setChecked(checked)
            act.triggered.connect(lambda checked, button=button, cap=tag: self._toggleCaption(button, cap))

        menu.exec( button.mapToGlobal(button.rect().bottomLeft()) )

    @Slot()
    def _toggleCaption(self, button: GroupButton, caption: str):
        # When the button is being unchecked, prepare words for removal from combined tags
        removeWords = None
        if self.combineTags and button.checked:
            words = [word for word in caption.strip().split(" ") if word]
            lastWord = words[-1]
            removeWords = set(words[:-1])

            for otherButton in self.buttons:
                if otherButton is button:
                    continue
                if otherButton.checked and otherButton.text.rstrip().endswith(lastWord):
                    removeWords.difference_update(otherButton.words())

        self.groups.ctx.text.toggleCaption(caption, removeWords)


    def resizeEvent(self, event):
        self.buttonLayout.update()  # Weird: Needed for proper resize.



class GroupButton(qtlib.EditablePushButton):
    buttonClicked = Signal(object)

    def __init__(self, text: str):
        super().__init__(text, self.stylerFunc, extraWidth=3)
        self.clicked.connect(self._onClicked)

        self.checked = False
        self.color = ""

    @staticmethod
    def stylerFunc(button):
        qtlib.setMonospace(button, 1.05)

    def setChecked(self, checked: bool, color: str, force=False):
        self.checked = checked
        if color != self.color or force:
            self.color = color
            self.setStyleSheet(qtlib.bubbleStylePad(color))

    @Slot()
    def _onClicked(self):
        self.buttonClicked.emit(self)


    def words(self) -> list[str]:
        return [word for word in self.text.strip().split(" ") if word]



class GroupColor(QtWidgets.QFrame):
    colorChanged = Signal(str)

    def __init__(self, group: CaptionControlGroup):
        super().__init__()
        self.group = group
        self._color = "#000"
        self._highlightColor = "#000"
        self._disabledColor = qtlib.COLOR_BUBBLE_BLACK
        self.charFormat = QtGui.QTextCharFormat()

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

    @property
    def highlightColor(self) -> str:
        return self._highlightColor

    @property
    def disabledColor(self) -> str:
        return self._disabledColor

    @color.setter
    def color(self, color: str):
        if not util.isValidColor(color):
            return

        self._color = color
        self._disabledColor = colors.mixBubbleColor(color, 0.35, 0.17)
        self.setStyleSheet(f".GroupColor{{background-color: {color}}}")

        highlightColor = qtlib.getHighlightColor(color)
        self.charFormat.setForeground(highlightColor)
        self._highlightColor = highlightColor.name()

        self.colorChanged.emit(color)
        self.group.groups.ctx.controlUpdated.emit()



class GroupMenu(QtWidgets.QMenu):
    def __init__(self, group: CaptionControlGroup):
        super().__init__()
        self.group = group
        self._build()

    def _build(self):
        groups = self.group.groups

        actFocus = self.addAction("Append Tags to Focus")
        actFocus.triggered.connect(self._addToFocus)

        self.addSeparator()

        actNewGroupAbove = self.addAction("Create Group Above")
        actNewGroupAbove.triggered.connect(lambda: groups.addGroupAt(self.group.index))

        actRemoveGroup = self.addAction("Remove Group")
        actRemoveGroup.triggered.connect(lambda: groups.removeGroup(self.group))

    @Slot()
    def _addToFocus(self):
        focusTab = self.group.groups.ctx.focus
        focusTab.appendFocusTags(self.group.captionsExpandWildcards)


class Trash(QtWidgets.QLabel):
    def __init__(self):
        super().__init__("🗑")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("Drag tags here to delete them")

        self.setHover(False)
        self.setMinimumWidth(40)

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



class ExclusivityComboBox(qtlib.NonScrollComboBox):
    def __init__(self):
        super().__init__()

        self.addItem("Disabled", MutualExclusivity.Disabled)
        self.addItem("Keep Last", MutualExclusivity.KeepLast)
        self.addItem("Keep First", MutualExclusivity.KeepFirst)
        self.addItem("Priority", MutualExclusivity.Priority)

        self._origFont = self.font()
        self._boldFont = QtGui.QFont(self._origFont)
        self._boldFont.setBold(True)

        self.currentIndexChanged.connect(self._onModeChanged)

    @Slot()
    def _onModeChanged(self, index: int):
        enabled = self.itemData(index) != MutualExclusivity.Disabled
        self.setFont(self._boldFont if enabled else self._origFont)
