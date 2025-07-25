from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot, QSignalBlocker
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
        self.chkRulesReplace = QtWidgets.QCheckBox("Search and replace")
        self.chkRulesBan = QtWidgets.QCheckBox("Remove banned tags")
        self.chkRulesRemoveDuplicates = QtWidgets.QCheckBox("Remove duplicates and subsets")
        self.chkRulesMutuallyExclusive = QtWidgets.QCheckBox("Remove mutually exclusive tags")
        self.chkRulesSort = QtWidgets.QCheckBox("Sort tags")
        self.chkRulesCombine = QtWidgets.QCheckBox("Combine tags")
        self.chkRulesConditionals = QtWidgets.QCheckBox("Conditional rules")
        self.chkRulesPrefixSuffix = QtWidgets.QCheckBox("Add prefix and suffix")

        self.allRulesCheckboxes = [
            self.chkRulesReplace,
            self.chkRulesBan,
            self.chkRulesRemoveDuplicates,
            self.chkRulesMutuallyExclusive,
            self.chkRulesSort,
            self.chkRulesCombine,
            self.chkRulesConditionals,
            self.chkRulesPrefixSuffix
        ]

        menuApplyRules = self.addMenu("Apply Rules")

        # Two buttons for selecting All/None
        selectLayout = QtWidgets.QHBoxLayout()
        selectLayout.setContentsMargins(4, 4, 4, 4)
        selectLayout.setSpacing(4)

        lblSelectAll = QtWidgets.QPushButton("Select All")
        lblSelectAll.clicked.connect(lambda: self._setRulesChecked(True))
        selectLayout.addWidget(lblSelectAll)

        lblSelectNone = QtWidgets.QPushButton("Unselect All")
        lblSelectNone.clicked.connect(lambda: self._setRulesChecked(False))
        selectLayout.addWidget(lblSelectNone)

        selectWidget = QtWidgets.QWidget()
        selectWidget.setLayout(selectLayout)

        actSelectWidget = QtWidgets.QWidgetAction(menuApplyRules)
        actSelectWidget.setDefaultWidget(selectWidget)
        menuApplyRules.addAction(actSelectWidget)

        # Checkboxes for rules
        rulesLayout = QtWidgets.QVBoxLayout()
        rulesLayout.setContentsMargins(6, 2, 2, 2)
        rulesLayout.setSpacing(0)

        toggleFunc = lambda: self.rulesSettingsUpdated.emit()
        for chk in self.allRulesCheckboxes:
            chk.toggled.connect(toggleFunc)
            rulesLayout.addWidget(chk)

        rulesWidget = QtWidgets.QWidget()
        rulesWidget.setLayout(rulesLayout)

        actRulesWidget = QtWidgets.QWidgetAction(menuApplyRules)
        actRulesWidget.setDefaultWidget(rulesWidget)
        menuApplyRules.addAction(actRulesWidget)

        self._setRulesChecked(True)

    def _setRulesChecked(self, checked: bool):
        with QSignalBlocker(self):
            for chk in self.allRulesCheckboxes:
                chk.setChecked(checked)
        self.rulesSettingsUpdated.emit()

    def getCaptionRulesSettings(self):
        settings = CaptionRulesSettings()
        settings.searchReplace              = self.chkRulesReplace.isChecked()
        settings.ban                        = self.chkRulesBan.isChecked()
        settings.removeDuplicates           = self.chkRulesRemoveDuplicates.isChecked()
        settings.removeMutuallyExclusive    = self.chkRulesMutuallyExclusive.isChecked()
        settings.sort                       = self.chkRulesSort.isChecked()
        settings.combineTags                = self.chkRulesCombine.isChecked()
        settings.conditionals               = self.chkRulesConditionals.isChecked()
        settings.prefixSuffix               = self.chkRulesPrefixSuffix.isChecked()
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
