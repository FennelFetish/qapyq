from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from lib import qtlib
from config import Config
from .caption_context import CaptionContext
from .caption_filter import CaptionRulesSettings


class RulesLoadMode(Enum):
    Empty    = "empty"
    Defaults = "defaults"
    Previous = "previous"


class CaptionMenu(QtWidgets.QMenu):
    countTokensToggled = Signal(bool)
    previewToggled = Signal(bool)
    rulesSettingsUpdated = Signal()


    def __init__(self, parent, context: CaptionContext):
        super().__init__(parent)
        self.ctx = context

        self._build()
        self.aboutToShow.connect(self._updateMenu)


    def _build(self):
        self.addSection("Tokenizer")

        actCountTokens = self.addAction("Count Tokens (CLIP)")
        actCountTokens.setCheckable(True)
        actCountTokens.setChecked(Config.captionCountTokens)
        actCountTokens.toggled.connect(self.countTokensToggled.emit)

        self.addSection("Caption Rules")

        self._buildOnNewTabSubmenu()
        self.addSeparator()

        actSaveDefaults = self.addAction("Save as Defaults...")
        actSaveDefaults.triggered.connect(self.ctx.settings.saveAsDefaultPreset)

        actLoadDefaults = self.addAction("Reset to Defaults...")
        actLoadDefaults.triggered.connect(self.ctx.settings.loadDefaultPreset)

        actClear = self.addAction("Clear...")
        actClear.triggered.connect(self.ctx.settings.clearPreset)

        self.addSeparator()

        actSave = self.addAction("Save As...")
        actSave.triggered.connect(self.ctx.settings.savePreset)

        actLoad = self.addAction("Load from File...")
        actLoad.triggered.connect(self.ctx.settings.loadPreset)

        self.addSeparator()

        self._buildApplyRulesSubmenu()

        actPreview = self.addAction("Show refined preview")
        actPreview.setCheckable(True)
        actPreview.setChecked(Config.captionShowPreview)
        actPreview.toggled.connect(self.previewToggled.emit)


    def _buildOnNewTabSubmenu(self):
        self.radioEmpty = QtWidgets.QRadioButton("Empty Rules")
        self.radioEmpty.toggled.connect(lambda checked: self._onLoadModeChanged(checked, RulesLoadMode.Empty))

        self.radioDefaults = QtWidgets.QRadioButton("Load Defaults")
        self.radioDefaults.toggled.connect(lambda checked: self._onLoadModeChanged(checked, RulesLoadMode.Defaults))

        self.radioPrevious = QtWidgets.QRadioButton("From previous Tab")
        self.radioPrevious.toggled.connect(lambda checked: self._onLoadModeChanged(checked, RulesLoadMode.Previous))

        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(0)
        layout.addWidget(self.radioEmpty)
        layout.addWidget(self.radioDefaults)
        layout.addWidget(self.radioPrevious)

        radioGroup = QtWidgets.QWidget()
        radioGroup.setLayout(layout)

        menuOnNewTab = self.addMenu("Rules for New Tab")
        action = QtWidgets.QWidgetAction(menuOnNewTab)
        action.setDefaultWidget(radioGroup)
        menuOnNewTab.addAction(action)


    def _buildApplyRulesSubmenu(self):
        self.menuApplyRules = qtlib.CheckboxMenu("Apply Rules")
        self.menuApplyRules.addCheckbox("replace",          "Search and replace")
        self.menuApplyRules.addCheckbox("banned",           "Remove banned tags")
        self.menuApplyRules.addCheckbox("remove_dup",       "Remove duplicates and subsets")
        self.menuApplyRules.addCheckbox("mutual_exclusive", "Remove mutually exclusive tags")
        self.menuApplyRules.addCheckbox("sort",             "Sort tags")
        self.menuApplyRules.addCheckbox("combine",          "Combine tags")
        self.menuApplyRules.addCheckbox("conditionals",     "Conditional rules")
        self.menuApplyRules.addCheckbox("prefix_suffix",    "Add prefix and suffix")

        self.menuApplyRules.setAllChecked(True)
        self.menuApplyRules.selectionChanged.connect(lambda: self.rulesSettingsUpdated.emit())

        # Two buttons for selecting All/None
        selectLayout = QtWidgets.QHBoxLayout()
        selectLayout.setContentsMargins(0, 4, 0, 4)
        selectLayout.setSpacing(4)

        lblSelectAll = QtWidgets.QPushButton("Select All")
        lblSelectAll.clicked.connect(lambda: self.menuApplyRules.setAllChecked(True))
        selectLayout.addWidget(lblSelectAll)

        lblSelectNone = QtWidgets.QPushButton("Unselect All")
        lblSelectNone.clicked.connect(lambda: self.menuApplyRules.setAllChecked(False))
        selectLayout.addWidget(lblSelectNone)

        self.menuApplyRules.widgetLayout().insertLayout(0, selectLayout)
        self.addMenu(self.menuApplyRules)

    def getCaptionRulesSettings(self):
        settings = CaptionRulesSettings()
        settings.searchReplace              = self.menuApplyRules.isChecked("replace")
        settings.ban                        = self.menuApplyRules.isChecked("banned")
        settings.removeDuplicates           = self.menuApplyRules.isChecked("remove_dup")
        settings.removeMutuallyExclusive    = self.menuApplyRules.isChecked("mutual_exclusive")
        settings.sort                       = self.menuApplyRules.isChecked("sort")
        settings.combineTags                = self.menuApplyRules.isChecked("combine")
        settings.conditionals               = self.menuApplyRules.isChecked("conditionals")
        settings.prefixSuffix               = self.menuApplyRules.isChecked("prefix_suffix")
        return settings


    @Slot()
    def _updateMenu(self):
        try:
            mode = RulesLoadMode(Config.captionRulesLoadMode)
            match mode:
                case RulesLoadMode.Empty:
                    self.radioEmpty.setChecked(True)
                case RulesLoadMode.Defaults:
                    self.radioDefaults.setChecked(True)
                case RulesLoadMode.Previous:
                    self.radioPrevious.setChecked(True)
        except ValueError:
            print(f"WARNING: Invalid caption rules load mode: {Config.captionRulesLoadMode}")


    def _onLoadModeChanged(self, checked: bool, mode: RulesLoadMode):
        if checked:
            Config.captionRulesLoadMode = mode.value
            self.close()
