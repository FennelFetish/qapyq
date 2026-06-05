from __future__ import annotations
import enum, os, re
from typing import Generator, TYPE_CHECKING
from typing_extensions import override
from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Qt, Signal, Slot, QSignalBlocker
from lib import colorlib, qtlib
from lib.template_parser import TemplateVariableParser, VariableHighlighter
from lib.captionfile import CaptionFile, FileTypeSelector
from lib.cascade import CascadeUpdate, CascadeGraph
from ui.autocomplete import TemplateTextEdit
from config import Config
from .caption_tab import CaptionTab, MultiEditSupport
from .caption_list import KeyType

if TYPE_CHECKING:
    from .caption_context import CaptionContext
    from .caption_container import CaptionContainer


class CaptionCascade(CaptionTab):
    def __init__(self, container: CaptionContainer, context: CaptionContext):
        super().__init__(context)
        self.container = container

        self._needsReload = True

        self.parser = TemplateVariableParser()
        self.highlighter = VariableHighlighter()

        self._build()

        self.ctx.tab.filelist.addListener(self)


    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(0)
        layout.setColumnStretch(2, 1)

        row = 0
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs, row, 0, 1, 5)

        row += 1
        self.addEntrySelector = FileTypeSelector()
        self.addEntrySelector.type = FileTypeSelector.TYPE_TAGS
        self.addEntrySelector.name = ""
        layout.addLayout(self.addEntrySelector, row, 0)

        self.btnAddEntry = QtWidgets.QPushButton("✚ Add Key")
        self.btnAddEntry.setMinimumWidth(100)
        self.btnAddEntry.clicked.connect(self._addNewEntry)
        layout.addWidget(self.btnAddEntry, row, 1)

        self.statusBar = qtlib.ColoredMessageStatusBar()
        self.statusBar.layout().setContentsMargins(50, 0, 20, 0)
        self.statusBar.setSizeGripEnabled(False)
        layout.addWidget(self.statusBar, row, 2)

        self.btnReloadAll = qtlib.SaveButton("Reload All")
        self.btnReloadAll.setMinimumWidth(120)
        self.btnReloadAll.clicked.connect(self.reloadTabs)
        layout.addWidget(self.btnReloadAll, row, 3)

        self.btnSaveAll = qtlib.SaveButton("Save All")
        self.btnSaveAll.setMinimumWidth(120)
        self.btnSaveAll.clicked.connect(self.saveAllTabs)
        layout.addWidget(self.btnSaveAll, row, 4)

        self.setLayout(layout)


    @override
    def getMultiEditSupport(self) -> MultiEditSupport:
        return MultiEditSupport.Disabled

    @override
    def onTabEnabled(self):
        if self._needsReload:
            self.reloadTabs()


    def onFileChanged(self, currentFile: str):
        if self.ctx.currentWidget() is self:
            self.reloadTabs()
        else:
            self._needsReload = True

    def onFileListChanged(self, currentFile: str):
        self.onFileChanged(currentFile)


    def getTabs(self) -> Generator[CascadeTab]:
        for i in range(self.tabs.count()):
            tab: CascadeTab = self.tabs.widget(i)
            yield tab

    def _clearTabs(self):
        for tab in self.getTabs():
            tab.deleteLater()
        self.tabs.clear()

    @Slot()
    def reloadTabs(self):
        file = self.ctx.tab.filelist.currentFile
        self.parser.setup(file)
        self._clearTabs()

        parentTemplates = {}
        for jsonFile, name in zip(*CascadeUpdate.getJsonFiles(file)):
            if name.endswith(".json"):
                name = f"📄 {name}"
            else:
                name = f"📁 {name}"

            captionFile = CaptionFile(jsonFile)
            captionFile.loadFromJson()

            if captionFile.cascade:
                name = f"{name} ({len(captionFile.cascade)})"

            tab = CascadeTab(self, jsonFile, parentTemplates, captionFile.cascade)
            tab.entryEdited.connect(self._onEntryEdited)
            self.tabs.addTab(tab, name)

            parentTemplates.update(captionFile.cascade)

        self.tabs.setCurrentIndex(self.tabs.count()-1)
        self.btnSaveAll.setChanged(False)

        self._needsReload = False


    @Slot(object, object)
    def _onEntryEdited(self, tab: CascadeTab, entry: CascadeTemplateEntry):
        self.btnSaveAll.setChanged(True)

        tabIndex = self.tabs.indexOf(tab)
        self.tabs.tabBar().setTabTextColor(tabIndex, colorlib.RED)

        self._updateInheritance(tab, entry.key)

    def _updateInheritance(self, startTab: CascadeTab, key: str):
        template: str | None = None  # Accumulated template for this key
        update = False               # Only update tabs to the right of 'startTab'

        for tab in self.getTabs():
            with QSignalBlocker(tab): # Avoid recursion through 'CascadeTab.entryEdited'
                if entry := tab.getEntry(key):
                    if update:
                        entry.setInheritedText(template)
                    if entry.overrideEnabled:
                        template = entry.text

                elif update:
                    entry = tab.addNewEntry(key, template)
                    entry.setOverrideEnabled(False)

            update |= (tab is startTab)

    @Slot()
    def _addNewEntry(self):
        if self.tabs.count() == 0:
            self.statusBar.showColoredMessage("No file loaded", False)
            return

        keyName = self.addEntrySelector.name.strip()
        keyType = self.addEntrySelector.type

        if keyType == FileTypeSelector.TYPE_TXT:
            key = "text"
        else:
            if not keyName:
                self.statusBar.showColoredMessage("Empty key", False)
                return

            key = f"{keyType}.{keyName}"

        tab: CascadeTab = self.tabs.currentWidget()
        if tab.getEntry(key) is not None:
            self.statusBar.showColoredMessage("Key already exists", False)
            return

        self.addEntrySelector.name = ""

        entry = tab.addNewEntry(key)
        entry.setOverrideEnabled(True)  # Emits 'entryEdited' signal
        entry.textField.setFocus()


    @Slot()
    def saveAllTabs(self):
        if cyclePath := self._tryGetCycle():
            self.statusBar.showColoredMessage(f"Failed to save cascade templates: Cycle exists: {cyclePath}", False, 0)
            return

        errorCount: int = 0
        saveCount: int = 0
        templateCount: int = 0

        for tab in self.getTabs():
            try:
                numTemplatesSaved = tab.save()
                if numTemplatesSaved > 0:
                    saveCount += 1
                    templateCount += numTemplatesSaved
            except Exception as ex:
                errorCount += 1
                print(f"Failed to save cascade templates: {ex} ({type(ex).__name__})")

        if errorCount > 0:
            errStr = "error" if errorCount == 1 else "errors"
            self.statusBar.showColoredMessage(f"Failed to save cascade templates ({errorCount} {errStr})", False, 0)
            return

        if saveCount > 0:
            templateStr = "template" if templateCount == 1 else "templates"
            fileStr = "file" if saveCount == 1 else "files"
            self.statusBar.showColoredMessage(f"Saved {templateCount} cascade {templateStr} to {saveCount} json {fileStr}", True)
        else:
            self.statusBar.showColoredMessage(f"Nothing to write", True)

        self.btnSaveAll.setChanged(False)

        for i in range(self.tabs.count()):
            self.tabs.tabBar().setTabTextColor(i, "")

    def _tryGetCycle(self) -> str:
        templates = dict[str, str]()
        for tab in self.getTabs():
            tab.storeTemplates(templates)

        return CascadeGraph(templates).getFirstCycle()



class CascadeTab(QtWidgets.QWidget):
    entryEdited = Signal(object, object)  # CascadeTab, CascadeTemplateEntry

    def __init__(self, cascade: CaptionCascade, jsonPath: str, parentTemplates: dict[str, str], ownTemplates: dict[str, str]):
        super().__init__()
        self.cascade = cascade
        self.jsonPath = jsonPath

        self._layoutEntries = QtWidgets.QVBoxLayout()
        self._layoutEntries.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layoutEntries.setSpacing(0)

        self._build()
        self._initEntries(parentTemplates, ownTemplates)

    def _build(self):
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(4)
        layout.setVerticalSpacing(0)
        layout.setColumnStretch(2, 1)

        row = 0
        widget = QtWidgets.QWidget()
        widget.setLayout(self._layoutEntries)

        self._scrollArea = qtlib.RowScrollArea(widget)
        layout.addWidget(self._scrollArea, row, 0, 1, 6)

        self.setLayout(layout)

    def _initEntries(self, parentTemplates: dict[str, str], ownTemplates: dict[str, str]):
        templates = parentTemplates.copy()
        templates.update(ownTemplates)

        if not templates:
            self._addPlaceholder()
            return

        for key, template in sorted(templates.items(), key=self._entrySortKey):
            entry = self._addEntry(key, template, parentTemplates.get(key))
            entry.setOverrideEnabled(key in ownTemplates)

    @staticmethod
    def _entrySortKey(item: tuple[str, dict]) -> tuple[int, str]:
        key = item[0]
        if key == FileTypeSelector.TYPE_TXT:
            return (2, "")

        try:
            keyType, keyName = key.split(".")
        except ValueError:
            return (4, key)

        match keyType:
            case FileTypeSelector.TYPE_TAGS:
                return (0, keyName)
            case FileTypeSelector.TYPE_CAPTIONS:
                return (1, keyName)

        return (3, keyName)


    def _addPlaceholder(self):
        self._clearPlaceholder()
        self._layoutEntries.addWidget(PlaceholderWidget())

    def _clearPlaceholder(self):
        # Remove spacer and placeholder
        for i in range(self._layoutEntries.count()-1, -1, -1):
            item = self._layoutEntries.itemAt(i)
            if item and (widget := item.widget()) and not isinstance(widget, CascadeTemplateEntry):
                self._layoutEntries.takeAt(i)
                widget.deleteLater()


    @property
    def entries(self) -> Generator[CascadeTemplateEntry]:
        for i in range(self._layoutEntries.count()):
            item = self._layoutEntries.itemAt(i)
            if item and isinstance(widget := item.widget(), CascadeTemplateEntry):
                yield widget

    def getEntry(self, key: str) -> CascadeTemplateEntry | None:
        for entry in self.entries:
            if entry.key == key:
                return entry
        return None

    def addNewEntry(self, key: str, inheritedText: str | None = None):
        self._clearPlaceholder()
        entry = self._addEntry(key, "", inheritedText)
        return entry

    def _addEntry(self, key: str, text: str, inheritedText: str | None):
        entry = CascadeTemplateEntry(self, key, inheritedText)
        entry.text = text

        entry.modeChanged.connect(self._onEntryModeChanged)
        entry.textField.textChanged.connect(lambda: self.entryEdited.emit(self, entry))
        entry.textField.focusReceived.connect(self._scrollToTextField)
        entry.textField.save.connect(self.cascade.saveAllTabs)

        self._layoutEntries.addWidget(entry)
        return entry

    def _removeEntry(self, entry: CascadeTemplateEntry):
        self._layoutEntries.removeWidget(entry)
        entry.deleteLater()

        if sum(1 for e in self.entries) == 0:
            self._addPlaceholder()

    @Slot(object)
    def _onEntryModeChanged(self, entry: CascadeTemplateEntry):
        self.entryEdited.emit(self, entry)

        if not entry.overrideEnabled and entry.inheritedText is None:
            self._removeEntry(entry)


    @Slot(object)
    def _scrollToTextField(self, textEdit: CascadeTemplateTextEdit):
        self._scrollArea.ensureWidgetVisible(textEdit.parentWidget())


    def storeTemplates(self, templates: dict[str, str]):
        for entry in self.entries:
            if entry.overrideEnabled:
                templates[entry.key] = entry.text

    def save(self) -> int:
        captionFile = CaptionFile(self.jsonPath)
        if captionFile.jsonExists() and not captionFile.loadFromJson():
            raise RuntimeError(f"Could not load existing templates from '{self.jsonPath}'")

        templates = dict[str, str]()
        self.storeTemplates(templates)

        if not templates and not captionFile.cascade:
            return 0  # Nothing to write

        captionFile.cascade = templates
        captionFile.saveToJson()

        numTemplates = len(templates)
        print(f"Saved {numTemplates} cascade templates to '{self.jsonPath}'")
        return numTemplates



class CascadeTemplateEntry(QtWidgets.QWidget):
    modeChanged = Signal(object)

    def __init__(self, tab: CascadeTab, key: str, inheritedText: str | None):
        super().__init__()
        self.tab = tab

        self.key: str = key
        self.inheritedText: str | None = inheritedText
        self.overrideEnabled: bool = True

        self._build(key)

    def _build(self, key: str):
        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(2)

        col = 0
        self.btnToggle = EntryToggleButton()
        self.btnToggle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btnToggle.clicked.connect(self._toggleOverrideEnabled)
        layout.addWidget(self.btnToggle, 0, col)

        col += 1
        layout.setColumnMinimumWidth(col, 220)

        self.txtKey = QtWidgets.QLabel(key)
        self.txtKey.setTextFormat(Qt.TextFormat.PlainText)
        self.txtKey.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.txtKey.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        qtlib.setMonospace(self.txtKey)
        self._setKeyColor(self.txtKey, key)
        layout.addWidget(self.txtKey, 0, col)

        self.chkUseRules = QtWidgets.QCheckBox("Rules")
        self.chkUseRules.toggled.connect(self.setRulesMode)
        layout.addWidget(self.chkUseRules, 1, col, Qt.AlignmentFlag.AlignTop)
        layout.setRowStretch(1, 1)

        col += 1
        layout.setColumnMinimumWidth(col, 12)

        col += 1
        layout.setColumnStretch(col, 1)

        self.templateStack = self._buildTemplateStack()
        layout.addLayout(self.templateStack, 0, col, 2, 1, Qt.AlignmentFlag.AlignTop)

        col += 1
        layout.setColumnStretch(col, 1)

        self.txtPreview = QtWidgets.QPlainTextEdit()
        self.txtPreview.setReadOnly(True)
        self.txtPreview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.txtPreview.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        qtlib.setMonospace(self.txtPreview)
        qtlib.setShowWhitespace(self.txtPreview)
        qtlib.setTextEditHeight(self.txtPreview, 3, "min")

        # Wrap preview in another layout to fully stretch it vertically
        previewStretchLayout = QtWidgets.QVBoxLayout()
        previewStretchLayout.addWidget(self.txtPreview)
        layout.addLayout(previewStretchLayout, 0, col, 2, 1, Qt.AlignmentFlag.AlignTop)

        # Separator across all columns
        separatorLine = QtWidgets.QFrame()
        separatorLine.setFrameStyle(QtWidgets.QFrame.Shape.HLine | QtWidgets.QFrame.Shadow.Sunken)
        layout.addWidget(separatorLine, 2, 0, 1, 5)
        layout.setRowMinimumHeight(2, 12)

        self.setLayout(layout)

    def _buildTemplateStack(self):
        self.txtTemplate = CascadeTemplateTextEdit(self.tab.cascade.ctx.tab.templateAutoCompleteSources)
        self.txtTemplate.setTabChangesFocus(True)
        qtlib.setMonospace(self.txtTemplate)
        qtlib.setTextEditHeight(self.txtTemplate, 3, "min")
        self.txtTemplate.textChanged.connect(self.updateHighlight)

        self.rulesWidget = RuleChooserWidget()
        self.rulesWidget.ruleTemplateChanged.connect(self.txtTemplate.setPlainText)

        stack = QtWidgets.QStackedLayout()
        stack.addWidget(self.txtTemplate)
        stack.addWidget(self.rulesWidget)
        return stack

    @staticmethod
    def _setKeyColor(txtKey: QtWidgets.QLabel, key: str):
        if key.startswith("tags."):
            keyType = KeyType.Tags
        elif key.startswith("captions."):
            keyType = KeyType.Caption
        else:
            keyType = KeyType.TextFile

        match keyType:
            case KeyType.Tags:     keyColor = "#70C0C0"
            case KeyType.Caption:  keyColor = "#C0C070"
            case KeyType.TextFile: keyColor = "#C070C0"

        enabledColor  = colorlib.getHighlightColor(keyColor)
        disabledColor = enabledColor.darker(180)

        keyPalette = txtKey.palette()
        keyPalette.setColor(keyPalette.ColorGroup.Active, keyPalette.ColorRole.WindowText, enabledColor)
        keyPalette.setColor(keyPalette.ColorGroup.Active, keyPalette.ColorRole.Text, enabledColor)
        keyPalette.setColor(keyPalette.ColorGroup.Disabled, keyPalette.ColorRole.WindowText, disabledColor)
        keyPalette.setColor(keyPalette.ColorGroup.Disabled, keyPalette.ColorRole.Text, disabledColor)
        txtKey.setPalette(keyPalette)


    @property
    def textField(self) -> CascadeTemplateTextEdit:
        return self.txtTemplate

    @property
    def text(self):
        if self.chkUseRules.isChecked():
            return self.rulesWidget.getTemplate()
        else:
            return self.txtTemplate.toPlainText()

    @text.setter
    def text(self, text: str):
        self.txtTemplate.setPlainText(text)

        rulesPatternMatch = self.rulesWidget.fromTemplate(text)
        self.chkUseRules.setChecked(rulesPatternMatch)


    @Slot()
    def _toggleOverrideEnabled(self):
        self.setOverrideEnabled(not self.overrideEnabled)

    def setOverrideEnabled(self, enabled: bool):
        self.overrideEnabled = enabled
        for widget in (self.txtKey, self.txtTemplate, self.rulesWidget):
            widget.setEnabled(enabled)

        self.chkUseRules.setVisible(enabled)

        self.updateHighlight()
        self._updateMode()

    def _updateMode(self):
        if self.overrideEnabled:
            if self.inheritedText is None:
                mode = EntryToggleButton.Mode.Remove
            else:
                mode = EntryToggleButton.Mode.Inherit
        else:
            mode = EntryToggleButton.Mode.Add

            if self.inheritedText is not None:
                self.text = self.inheritedText

        self.btnToggle.setMode(mode)
        self.modeChanged.emit(self)


    @Slot(bool)
    def setRulesMode(self, rulesModeEnabled: bool):
        index = 1 if rulesModeEnabled else 0
        self.templateStack.setCurrentIndex(index)

        if rulesModeEnabled:
            self.rulesWidget.fromTemplate(self.text)


    def setInheritedText(self, text: str | None):
        self.inheritedText = text
        self._updateMode()

    @Slot()
    def updateHighlight(self):
        cascade = self.tab.cascade
        text, varPositions = cascade.parser.parseWithPositions(self.txtTemplate.toPlainText())
        self.txtPreview.setPlainText(text)
        disabled = not self.overrideEnabled
        cascade.highlighter.highlight(self.txtTemplate, self.txtPreview, varPositions, disabled)



class RuleChooserWidget(QtWidgets.QWidget):
    PATTERN_RULES = re.compile(r"^{{([^\.]+?\.[^\.]+?)#rules:([^:#]*?)}}$")

    DEFAULT_PATH = Config.pathExport

    ruleTemplateChanged = Signal(str) # template

    def __init__(self):
        super().__init__()

        layout = QtWidgets.QGridLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setContentsMargins(0, 0, 0, 0)

        row = 0
        self.srcSelector = FileTypeSelector(showTxtType=False)
        self.srcSelector.cboKey.wheelEvent  = self._disableWheelEvent
        self.srcSelector.cboType.wheelEvent = self._disableWheelEvent
        self.srcSelector.fileTypeUpdated.connect(self._onPathChanged)

        layout.addWidget(QtWidgets.QLabel("Source Key:"), row, 0)
        layout.addLayout(self.srcSelector, row, 1, 1, 2)

        row += 1
        self.txtRulesPath = QtWidgets.QLineEdit()
        qtlib.setMonospace(self.txtRulesPath)
        self.txtRulesPath.textChanged.connect(self._onPathChanged)
        layout.addWidget(QtWidgets.QLabel("Preset Path:"), row, 0)
        layout.addWidget(self.txtRulesPath, row, 1)

        self.btnChooseRulesPath = QtWidgets.QPushButton("Choose...")
        self.btnChooseRulesPath.clicked.connect(self._chooseFile)
        layout.addWidget(self.btnChooseRulesPath, row, 2)

        self.setLayout(layout)

    @staticmethod
    def _disableWheelEvent(event):
        pass

    @Slot()
    def _chooseFile(self):
        path = self.txtRulesPath.text() or RuleChooserWidget.DEFAULT_PATH
        path = os.path.join(Config.pathExport, path)

        fileFilter = "Rules Preset (*.json)"
        path, selectedFilter = QtWidgets.QFileDialog.getOpenFileName(self, "Load preset", path, fileFilter)

        if path:
            path = os.path.abspath(path)
            self.txtRulesPath.setText(path)
            RuleChooserWidget.DEFAULT_PATH = os.path.dirname(path)

    @Slot()
    def _onPathChanged(self):
        template = self.getTemplate()
        self.ruleTemplateChanged.emit(template)

    def getTemplate(self) -> str:
        key = f"{self.srcSelector.type}.{self.srcSelector.name.strip()}"
        path = self.txtRulesPath.text()
        return "{{" + f"{key}#rules:{path}" + "}}"

    @classmethod
    def isRulesTemplate(cls, template: str) -> bool:
        return cls.PATTERN_RULES.match(template) is not None

    def fromTemplate(self, template: str) -> bool:
        if match := self.PATTERN_RULES.match(template):
            keyType, keyName = match.group(1).split(".")
            if keyType not in (FileTypeSelector.TYPE_CAPTIONS, FileTypeSelector.TYPE_TAGS):
                return False

            self.srcSelector.type = keyType
            self.srcSelector.name = keyName

            path = match.group(2)
            self.txtRulesPath.setText(path)
            return True

        return False



class EntryToggleButton(QtWidgets.QPushButton):
    class Mode(enum.IntEnum):
        Add     = 0
        Remove  = 1
        Inherit = 2

    TEXT: dict[Mode, str] = {
        Mode.Add:     "+",
        Mode.Remove:  "⨯",
        Mode.Inherit: "⮜",
    }

    TOOLTIP: dict[Mode, str] = {
        Mode.Add:     "Current state: Inherited\nClick to add override at this level",
        Mode.Remove:  "Current state: Defined\nClick to remove template",
        Mode.Inherit: "Current state: Overridden\nClick to inherit template from previous level",
    }

    STYLE: dict[Mode, str] = {}
    FONT: QtGui.QFont = None

    def __init__(self):
        super().__init__("")
        self.setFixedWidth(18)
        self.setFixedHeight(18)
        self.setFont(EntryToggleButton.FONT)
        self.setMode(self.Mode.Add)

    @classmethod
    def initStyles(cls):
        if colorlib.DARK_THEME:
            addColor     = "#40D540"
            removeColor  = "#D54040"
            inheritColor = "#D5B040"
            bgColor, borderColor = "#1B1B1B", "#204020"
        else:
            addColor     = "#10E010"
            removeColor  = "#E01010"
            inheritColor = "#E0B010"
            bgColor, borderColor = "#DBDBDB", "#809080"

        cls.STYLE[cls.Mode.Add]     = cls._mkStyle(addColor, bgColor, borderColor)
        cls.STYLE[cls.Mode.Remove]  = cls._mkStyle(removeColor, bgColor, borderColor)
        cls.STYLE[cls.Mode.Inherit] = cls._mkStyle(inheritColor, bgColor, borderColor)

        font = qtlib.getMonospaceFont()
        font.setPointSizeF(12.0)
        EntryToggleButton.FONT = font

    @staticmethod
    def _mkStyle(textColor: str, bgColor: str, borderColor: str):
        return f".EntryToggleButton{{color: {textColor}; background-color: {bgColor}; " \
               f"border: 1px solid {borderColor}; border-radius: 4px; padding: 0px 0px 1px 0px}}"

    def setMode(self, mode: Mode):
        self.setText(self.TEXT[mode])
        self.setToolTip(self.TOOLTIP[mode])
        self.setStyleSheet(self.STYLE[mode])


EntryToggleButton.initStyles()



class CascadeTemplateTextEdit(TemplateTextEdit):
    focusReceived = Signal(object)
    save = Signal()  # Emitted in CaptionContainer._saveCaptionShortcut() that handles save shortcut for the window

    @override
    def focusInEvent(self, e: QtGui.QFocusEvent):
        super().focusInEvent(e)

        # Don't move cursor when autocomplete popup was closed
        if e.reason() != Qt.FocusReason.PopupFocusReason:
            self.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        self.focusReceived.emit(self)



class PlaceholderWidget(QtWidgets.QScrollArea):
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)

        title = QtWidgets.QLabel("No templates defined at this level")
        qtlib.setFontSize(title, 1.2)
        qtlib.setFontBold(title, True)

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.addWidget(title)

        layout.addWidget(QtWidgets.QLabel("Cascading updates work similar to Batch Apply, but they're automatic and resolve dependencies between templates."))
        layout.addWidget(QtWidgets.QLabel("Add a template for a key using the controls below. All tabs to the right of this level will inherit the template."))
        layout.addWidget(QtWidgets.QLabel("When you update a key in a JSON file, all templates that depend on this key are re-processed as well."))
        layout.addSpacing(12)
        layout.addWidget(QtWidgets.QLabel("For example, define a template <code>'{{captions.caption#oneline}} {{tags.tags#join:tags.quality}}'</code> for the 'text' key"))
        layout.addWidget(QtWidgets.QLabel("and it will always update the .txt file whenever you update 'captions.caption', 'tags.tags' or 'tags.quality' in the JSON file."))
        layout.addSpacing(12)
        layout.addWidget(QtWidgets.QLabel("Define templates at a folder level to apply them to all files in that folder and subfolders. The templates are stored in a 'qapyq_cascade.json' file per folder."))
        layout.addWidget(QtWidgets.QLabel("Define templates at the file level to override folder templates. These templates are stored in the same JSON file as the file's captions."))
        layout.addSpacing(12)
        layout.addWidget(QtWidgets.QLabel("Cascading updates are enabled by default but only effective when you define templates."))
        layout.addWidget(QtWidgets.QLabel("Use the toggle button in the bottom right corner of this Caption Window to disable them. The Batch and Gallery windows have a separate toggle."))

        layout.addStretch(1)
        self.setWidget(widget)
