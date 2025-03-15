from __future__ import annotations
from collections import Counter
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Slot, Signal
from lib import qtlib, util, colors
from ui.flow_layout import FlowLayout, ReorderWidget, ManualStartReorderWidget, ReorderDragHandle
from .caption_tab import CaptionTab
from .caption_preset import CaptionPreset, MutualExclusivity


# TODO?: Per group matching method:
# - exact match (str1 == str2)
# - substring ('b c' in 'a b c d e', but not 'b d')
# - all words ('b c' in 'a b c d e', but not 'b f')
# - any word  ('b d' in 'a b c d e', also 'b f')


class CaptionGroups(CaptionTab):
    HUE_OFFSET = 0.3819444 # 1.0 - inverted golden ratio, ~137.5°

    def __init__(self, context):
        super().__init__(context)

        self._nextGroupHue = util.rnd01()
        self.colorSet = CaptionColorSet(self)
        self.ctx.controlUpdated.connect(self.colorSet.clearCache)

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

        groupReorderWidget = ManualStartReorderWidget()
        groupReorderWidget.setLayout(self.groupLayout)
        groupReorderWidget.orderChanged.connect(self._emitUpdatedApplyRules)
        scrollGroup = qtlib.BaseColorScrollArea(groupReorderWidget)
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

        self.groupLayout.addWidget(group)
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
            self._emitUpdatedApplyRules()

    def removeAllGroups(self):
        for i in reversed(range(self.groupLayout.count())):
            item = self.groupLayout.takeAt(i)
            if widget := item.widget():
                widget.deleteLater()

        self.ctx.controlUpdated.emit()


    def getCaptionColors(self) -> dict[str, str]:
        return self.colorSet.colors

    def getCaptionCharFormats(self) -> dict[str, QtGui.QTextCharFormat]:
        return self.colorSet.charFormats

    def getCaptionCombineFormats(self) -> dict[str, CombineFormat]:
        return self.colorSet.combineFormats


    def updateSelectedState(self, captions: set[str], force: bool):
        captionWords: list[tuple[str, set[str]]] | None = None

        for group in self.groups:
            if group.combineTags:
                if captionWords is None:
                    captionWords = [
                        (words[-1], set(words[:-1])) # Tuple of: last word / set of remaining words
                        for words in (cap.split(" ") for cap in captions)
                    ]

                group.updateSelectedStateCombine(captionWords, force)
            else:
                group.updateSelectedState(captions, force)


    @Slot()
    def _emitUpdatedApplyRules(self):
        self.ctx.controlUpdated.emit()
        self.ctx.needsRulesApplied.emit()


    def saveToPreset(self, preset: CaptionPreset):
        for group in self.groups:
            preset.addGroup(group.name, group.color, group.exclusivity, group.combineTags, group.captions)

    def loadFromPreset(self, preset: CaptionPreset):
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

        self._combineWords = list[str]()

        self._buildHeaderWidget(name)

        self.buttonLayout = FlowLayout(spacing=1)
        self.buttonWidget = ReorderWidget(giveDrop=True, takeDrop=True)
        self.buttonWidget.setLayout(self.buttonLayout)
        self.buttonWidget.setMinimumHeight(14)
        self.buttonWidget.dragStartMinDistance = 4
        self.buttonWidget.dataCallback = lambda widget: widget.text
        self.buttonWidget.orderChanged.connect(self.groups._emitUpdatedApplyRules)
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

        btnRemoveGroup = QtWidgets.QPushButton("Remove Group")
        btnRemoveGroup.clicked.connect(lambda: self.groups.removeGroup(self))

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
        self.headerLayout.addWidget(btnRemoveGroup)
        self.headerWidget = QtWidgets.QWidget()
        self.headerWidget.setContentsMargins(0, 0, 0, 0)
        self.headerWidget.setLayout(self.headerLayout)


    def updateSelectedState(self, captions: set[str], force: bool):
        enabledColor, disabledColor = self.colorWidget.color, self.colorWidget.disabledColor
        for button in self.buttons:
            checked = button.text.strip() in captions
            color = enabledColor if checked else disabledColor
            button.setChecked(checked, color, force)

    def updateSelectedStateCombine(self, captionWords: list[tuple[str, set[str]]], force: bool):
        enabledColor, disabledColor = self.colorWidget.color, self.colorWidget.disabledColor
        for button in self.buttons:
            checked = self._checkSelectionStateCombine(button, captionWords)
            color = enabledColor if checked else disabledColor
            button.setChecked(checked, color, force)

    def _checkSelectionStateCombine(self, button: GroupButton, captionWords: list[tuple[str, set[str]]]) -> bool:
        buttonWords = button.words()
        for lastWord, captionWordSet in captionWords:
            if buttonWords[-1] == lastWord and captionWordSet.issuperset(buttonWords[:-1]):
                return True
        return False


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

    def _updateCombineWords(self):
        self._combineWords.clear()
        if self.combineTags:
            counter = Counter[str](
                button.text.strip().split(" ")[-1]
                for button in self.buttons
            )
            self._combineWords.extend(word for word, count in counter.items() if count > 1)

        self.lblCombineWords.setText(", ". join(self._combineWords))
        self.lblCombineWords.setStyleSheet(f"color: {self.colorWidget.highlightColor}")


    @property
    def captions(self) -> list[str]:
        return [button.text for button in self.buttons]

    def addCaption(self, text: str) -> bool:
        # Check if caption already exists in group
        for button in self.buttons:
            if text == button.text:
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
        text = self.groups.ctx.container.getSelectedCaption()
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
        # When the button is being unchecked, prepare words for removal from combined tags
        removeWords = None
        if self.combineTags and button.checked:
            words = button.words()
            lastWord = words[-1]
            removeWords = set(words[:-1])

            for otherButton in self.buttons:
                if otherButton is button:
                    continue
                if otherButton.checked and otherButton.text.rstrip().endswith(lastWord):
                    removeWords.difference_update(otherButton.words())

        # TODO: Send 'keepWords'?
        self.groups.ctx.container.toggleCaption(button.text, removeWords)


    def resizeEvent(self, event):
        self.buttonLayout.update()  # Weird: Needed for proper resize.



class GroupButton(qtlib.EditablePushButton):
    buttonClicked = Signal(object)

    def __init__(self, text):
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


    def words(self) -> list[str]:
        return [word for word in self.text.strip().split(" ") if word]

    @Slot()
    def _onClicked(self):
        self.buttonClicked.emit(self)



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
        self._disabledColor = colors.mixBubbleColor(color, 0.32, 0.1)
        self.setStyleSheet(f".GroupColor{{background-color: {color}}}")

        highlightColor = qtlib.getHighlightColor(color)
        self.charFormat.setForeground(highlightColor)
        self._highlightColor = highlightColor.name()

        self.colorChanged.emit(color)
        self.group.groups.ctx.controlUpdated.emit()



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



class CaptionColorSet:
    COLOR_FOCUS_DEFAULT = "#901313"
    COLOR_FOCUS_BAN     = "#686868"

    def __init__(self, groups: CaptionGroups):
        self.groups = groups
        self._nextGroupHue = util.rnd01()

        self._cachedColors: dict[str, str] | None = None
        self._cachedCharFormats: dict[str, QtGui.QTextCharFormat] | None = None
        self._cachedCombineFormats: dict[str, CombineFormat] | None = None

        self.bannedFormat = QtGui.QTextCharFormat()
        self.bannedFormat.setForeground(QtGui.QColor.fromHsvF(0, 0, 0.5))

        self.focusFormat = QtGui.QTextCharFormat()
        self.focusFormat.setForeground(qtlib.getHighlightColor(self.COLOR_FOCUS_DEFAULT))


    @property
    def colors(self) -> dict[str, str]:
        if not self._cachedColors:
            self.update()
        return self._cachedColors

    @property
    def charFormats(self) -> dict[str, QtGui.QTextCharFormat]:
        if not self._cachedCharFormats:
            self.update()
        return self._cachedCharFormats

    @property
    def combineFormats(self) -> dict[str, CombineFormat]:
        if not self._cachedCombineFormats:
            self.updateCombineFormats()
        return self._cachedCombineFormats


    def update(self):
        colors: dict[str, str] = dict()
        formats: dict[str, QtGui.QTextCharFormat] = dict()
        ctx = self.groups.ctx

        # First insert all focus tags. This is the default color if focus tags don't belong to groups.
        focusSet = ctx.focus.getFocusSet()
        for focusTag in focusSet:
            colors[focusTag] = self.COLOR_FOCUS_DEFAULT
            formats[focusTag] = self.focusFormat

        # Insert group colors
        for group in self.groups.groups:
            mutedColor, mutedFormat = self._getMuted(group.color) if focusSet else (group.color, group.charFormat)

            for caption in group.captions:
                if caption in focusSet:
                    colors[caption]  = group.color
                    formats[caption] = group.charFormat
                else:
                    colors[caption]  = mutedColor
                    formats[caption] = mutedFormat

        # Insert banned color. This will overwrite group colors.
        bannedColor, bannedFormat = self._getMuted(qtlib.COLOR_BUBBLE_BAN) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self.bannedFormat)
        bannedFocusColor, bannedFocusFormat = self._getMuted(self.COLOR_FOCUS_BAN, 1, 1) if focusSet else (qtlib.COLOR_BUBBLE_BAN, self.bannedFormat)
        for banned in ctx.settings.bannedCaptions:
            if banned in focusSet:
                colors[banned]  = bannedFocusColor
                formats[banned] = bannedFocusFormat
            else:
                colors[banned]  = bannedColor
                formats[banned] = bannedFormat

        # Hover color
        for caption, color in colors.items():
            if ctx.container.isHovered(caption):
                colors[caption], formats[caption] = self._getHovered(color)

        self._cachedColors = colors
        self._cachedCharFormats = formats


    def updateCombineFormats(self):
        # Last Word => CombineFormat
        formatMap = dict[str, CombineFormat]()

        for group in self.groups.groups:
            if not group.combineTags:
                continue

            groupFormat = group.charFormat
            groupWords = set[str]()
            groupLastWords = set[str]()

            for button in group.buttons:
                buttonWords = button.words()
                if len(buttonWords) < 2:
                    continue

                groupWords.update(buttonWords)

                lastWord = buttonWords[-1]
                groupLastWords.add(lastWord)

                for word in buttonWords[:-1]:
                    combineFormat = formatMap.get(lastWord)
                    if not combineFormat:
                        formatMap[lastWord] = combineFormat = CombineFormat(lastWord)

                    combineFormat.wordFormats[word] = groupFormat

                    wordSet = frozenset(buttonWords)
                    #combineFormat.tagSets.add(wordSet)
                    #combineFormat.tagFormats[wordSet] = groupFormat

            for lastWord in groupLastWords:
                wordSet = set(groupWords)
                wordSet.discard(lastWord)
                formatMap[lastWord].groupFormats.append(CombineFormat.GroupFormat(wordSet, groupFormat))

        # Remove entries with only one word
        self._cachedCombineFormats = {k: cf for k, cf in formatMap.items() if cf.finalize()}


    @Slot()
    def clearCache(self):
        self._cachedColors = None
        self._cachedCharFormats = None
        self._cachedCombineFormats = None


    def _getMuted(self, color: str, mixS=0.22, mixV=0.3):
        mutedColor = colors.mixBubbleColor(color, mixS, mixV)
        mutedFormat = QtGui.QTextCharFormat()
        mutedFormat.setForeground(qtlib.getHighlightColor(mutedColor))
        return mutedColor, mutedFormat

    def _getHovered(self, color: str):
        h, s, v = util.get_hsv(color)
        s = max(0.3, min(1.0, s*0.8))
        v = max(0.2, min(1.0, v*1.6))
        hoveredColor = util.hsv_to_rgb(h, s, v)

        hoveredFormat = QtGui.QTextCharFormat()
        hoveredFormat.setForeground(qtlib.getHighlightColor(hoveredColor))
        hoveredFormat.setFontUnderline(True)

        return hoveredColor, hoveredFormat



# One CombineFormat is shared by multiple groups.
# Retrieved from dict [ Last Word => CombineFormat ]
# That dict is uses for faster initial lookup, matching the last word.
class CombineFormat:
    class GroupFormat:
        def __init__(self, words: set[str], format: QtGui.QTextCharFormat):
            self.words = frozenset(words)
            self.format = format


    def __init__(self, lastWord: str):
        self.wordFormats = dict[str, QtGui.QTextCharFormat]()
        #self.tagSets = set[frozenset[str]]()

        #self.tagFormats = dict[frozenset[str], QtGui.QTextCharFormat]()
        #self._tagFormatsSorted = list[tuple[frozenset[str], QtGui.QTextCharFormat]]()

        self.lastWord = lastWord
        self.groupFormats = list[self.GroupFormat]()

    def finalize(self) -> bool:
        if len(self.wordFormats) < 2:
            return False

        # print("CombineFormat Tag Order:")
        # for k in self.tagFormats.keys():
        #     print(f"  {k}")

        # self._tagFormatsSorted = sorted(((k, v) for k, v in self.tagFormats.items()), key=lambda item: -len(item[0]))
        # self.tagFormats = None

        # print("CombineFormat Tag Order (sorted):")
        # for k, v in self._tagFormatsSorted:
        #     print(f"  {k}")


        self.groupFormats.sort(key=lambda item: -len(item.words))
        return True

    # def hasSubset(self, captionWords: list[str]) -> bool:
    #     captionWords = [word for word in captionWords if word]
    #     for tagSet in self.tagSets:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return True
    #     return False

    # def hasSubset(self, captionWords: list[str]) -> bool:
    #     captionWords = [word for word in captionWords if word]
    #     for tagSet, format in self._tagFormatsSorted:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return True
    #     return False


    # # Find group with longest match (maximum number of 'captionWords' in group tags)
    # def getFormat(self, captionWords: list[str]):
    #     captionWords = [word for word in captionWords if word]

    #     # TODO: Return set with words in group

    #     for tagSet, format in self._tagFormatsSorted:
    #         print(f"subset test: {tagSet} -> in caption -> {captionWords}")
    #         if tagSet.issubset(captionWords):
    #             print("  => True")
    #             return tagSet, format

    #     return None, None


    # Find group with longest match (maximum number of 'captionWords' in group tags)
    def getGroupFormat(self, captionWords: list[str]):
        captionWords = [word for word in captionWords if word and word != self.lastWord]
        if not captionWords:
            return None

        maxWords = 0
        bestFormat = None

        for groupFormat in self.groupFormats:
            intersection = groupFormat.words.intersection(captionWords)
            # Complete match: All caption words are members of the same group
            if len(intersection) == len(captionWords):
                return groupFormat

            if len(intersection) > maxWords:
                maxWords = len(intersection)
                bestFormat = groupFormat

        # if bestFormat:
        #     print(f"for caption: {captionWords}  => best group: {bestFormat.words}")
        return bestFormat



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
