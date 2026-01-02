from __future__ import annotations
from typing import Iterable
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from ui.tab import ImgTab
from .caption_tab import CaptionTab, MultiEditSupport
from .caption_highlight import CaptionHighlight, HighlightDataSource, CaptionGroupData
from .caption_filter import CaptionRulesProcessor
from .caption_settings import CaptionSettings
from .caption_groups import CaptionGroups
from .caption_list import CaptionList
from ui.autocomplete import AutoCompleteSource, GroupNgramAutoCompleteSource, getCsvAutoCompleteSource


class CaptionContext(QtWidgets.QTabWidget):
    captionEdited       = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()
    multiEditToggled    = Signal(bool)


    def __init__(self, container, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self._cachedRulesProcessor: CaptionRulesProcessor | None = None

        # First slots
        self.controlUpdated.connect(self._invalidateRulesProcessor)
        self.separatorChanged.connect(lambda sep: self._invalidateRulesProcessor())
        self.multiEditToggled.connect(self._storeMultiEditState)

        # Create CaptionHighlight early to connect cache clearing to 'controlUpdated' before anything else
        self.highlight = CaptionHighlight(CaptionContextDataSource(self))

        from .caption_container import CaptionContainer
        self.container: CaptionContainer = container

        self.settings = CaptionSettings(self)
        self.groups = CaptionGroups(self)

        from .caption_conditionals import CaptionConditionals
        self.conditionals = CaptionConditionals(self)

        from .caption_focus import CaptionFocus
        self.focus = CaptionFocus(container, self)

        from .caption_generate import CaptionGenerate
        self.generate = CaptionGenerate(self)

        from .caption_text import CaptionTextEdit
        self.text = CaptionTextEdit(self, self._setupAutoCompleteSources())

        self.addTab(self.settings, "Rules")
        self.addTab(self.groups, "Groups")
        self.addTab(self.conditionals, "Conditionals")
        self.addTab(self.focus, "Focus")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")
        self.addTab(CaptionList(self), "List")

        self._activeWidget: CaptionTab = self.currentWidget()
        self.multiEditSupport: MultiEditSupport = self._activeWidget.getMultiEditSupport()
        self._activeWidget.onTabEnabled()

        self._multiEditReactivate: bool = False
        self._tabSwitching = False
        self.currentChanged.connect(self.onTabChanged)


    @Slot()
    def onTabChanged(self, index: int):
        if self._activeWidget:
            self._activeWidget.onTabDisabled()

        widget: CaptionTab = self.widget(index)
        if widget:
            self._checkMultiEditSupport(widget)
            self._activeWidget = widget
            widget.onTabEnabled()

    def _checkMultiEditSupport(self, widget: CaptionTab):
        self.multiEditSupport = widget.getMultiEditSupport()
        match self.multiEditSupport:
            case MultiEditSupport.Disabled:        checked, enabled = False, False
            case MultiEditSupport.PreferDisabled:  checked, enabled = False, True
            case MultiEditSupport.Full:
                checked = self._multiEditReactivate and bool(self.tab.filelist.selectedFiles)
                enabled = True

        try:
            self._tabSwitching = True
            btnMultiEdit = self.container.btnMultiEdit
            btnMultiEdit.setChecked(checked)
            btnMultiEdit.setEnabled(enabled)
        finally:
            self._tabSwitching = False

    @Slot()
    def _storeMultiEditState(self, state: bool):
        if not self._tabSwitching:
            self._multiEditReactivate = state


    @Slot()
    def _invalidateRulesProcessor(self):
        self._cachedRulesProcessor = None

    def rulesProcessor(self) -> CaptionRulesProcessor:
        if not self._cachedRulesProcessor:
            self._cachedRulesProcessor = self.createRulesProcessor()
        return self._cachedRulesProcessor

    def createRulesProcessor(self) -> CaptionRulesProcessor:
        cfg = self.settings

        rulesProcessor = CaptionRulesProcessor(cfg.separator, cfg.isRemoveDuplicates, cfg.isSortCaptions, cfg.isWhitelistGroups)
        rulesProcessor.setPrefixSuffix(cfg.prefix, cfg.suffix, cfg.isAddPrefixSeparator, cfg.isAddSuffixSeparator)
        rulesProcessor.setSearchReplacePairs(cfg.searchReplacePairs)
        rulesProcessor.setBannedCaptions(cfg.bannedCaptions)
        rulesProcessor.setCaptionGroups( (group.captionsExpandWildcards, group.exclusivity, group.combineTags) for group in self.groups.groups )
        rulesProcessor.setConditionalRules(self.conditionals.getFilterRules())
        return rulesProcessor


    def _setupAutoCompleteSources(self) -> list[AutoCompleteSource]:
        self.groupAutocompleteSource = GroupNgramAutoCompleteSource()
        self.controlUpdated.connect(self._updateGroupAutoComplete)
        self._updateGroupAutoComplete()

        return [self.groupAutocompleteSource, getCsvAutoCompleteSource()]

    @Slot()
    def _updateGroupAutoComplete(self):
        groups = (group.captionsExpandWildcards for group in self.groups.groups)
        self.groupAutocompleteSource.update(groups)



class CaptionContextDataSource(HighlightDataSource):
    def __init__(self, context: CaptionContext):
        super().__init__()
        self.ctx: CaptionContext = context

    def connectClearCache(self, slot: Slot):
        self.ctx.controlUpdated.connect(slot)

    def isHovered(self, caption: str) -> bool:
        return self.ctx.container.isHovered(caption)

    def getPresence(self) -> list[float] | None:
        return self.ctx.container.multiEdit.getTagPresence()

    def getTotalPresence(self, tags: list[str]) -> list[float] | None:
        matchNode = self.ctx.highlight.matchNode
        return self.ctx.container.multiEdit.getTotalTagPresence(tags, matchNode)

    def getFocusSet(self) -> set[str]:
        return self.ctx.focus.getFocusSet()

    def getBanned(self) -> Iterable[str]:
        return self.ctx.settings.bannedCaptions

    def getGroups(self) -> Iterable[CaptionGroupData]:
        highlightAll = not self.ctx.groups.filterMenu.filterHighlight
        return (
            CaptionGroupData(
                group.captionsExpandWildcards,
                group.charFormat,
                group.color
            )
            for group in self.ctx.groups.groups
            if highlightAll or group.enabled
        )
