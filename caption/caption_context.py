from __future__ import annotations
from typing import Iterable
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from ui.tab import ImgTab
from .caption_highlight import CaptionHighlight, HighlightDataSource, CaptionGroupData
from .caption_filter import CaptionRulesProcessor
from .caption_settings import CaptionSettings
from .caption_groups import CaptionGroups
from .caption_list import CaptionList
from .caption_multi_edit import TagPresence


class CaptionContext(QtWidgets.QTabWidget):
    captionEdited       = Signal(str)
    separatorChanged    = Signal(str)
    controlUpdated      = Signal()
    needsRulesApplied   = Signal()


    def __init__(self, container, tab: ImgTab):
        super().__init__()
        self.tab = tab

        self._cachedRulesProcessor: CaptionRulesProcessor | None = None
        self.controlUpdated.connect(self._invalidateRulesProcessor) # First Slot for controlUpdated

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
        self.text = CaptionTextEdit(self)
        self.highlight = CaptionHighlight(CaptionContextDataSource(self))

        self.addTab(self.settings, "Rules")
        self.addTab(self.groups, "Groups")
        self.addTab(self.conditionals, "Conditionals")
        self.addTab(self.focus, "Focus")
        #self.addTab(QtWidgets.QWidget(), "Folder Overrides") # Let variables from json override settings?
        self.addTab(self.generate, "Generate")
        self.addTab(CaptionList(self), "List")

        self._activeWidget = None
        self.currentChanged.connect(self.onTabChanged)
        self.onTabChanged(0)

    @Slot()
    def onTabChanged(self, index: int):
        if self._activeWidget:
            self._activeWidget.onTabDisabled()

        if widget := self.widget(index):
            self._activeWidget = widget
            widget.onTabEnabled()


    @Slot()
    def _invalidateRulesProcessor(self):
        self._cachedRulesProcessor = None

    def rulesProcessor(self) -> CaptionRulesProcessor:
        if not self._cachedRulesProcessor:
            self._cachedRulesProcessor = self.createRulesProcessor()
        return self._cachedRulesProcessor

    def createRulesProcessor(self) -> CaptionRulesProcessor:
        removeDup = self.settings.isRemoveDuplicates
        sortCaptions = self.settings.isSortCaptions
        separator = self.settings.separator

        rulesProcessor = CaptionRulesProcessor()
        rulesProcessor.setup(self.settings.prefix, self.settings.suffix, separator, removeDup, sortCaptions)
        rulesProcessor.setSearchReplacePairs(self.settings.searchReplacePairs)
        rulesProcessor.setBannedCaptions(self.settings.bannedCaptions)
        rulesProcessor.setCaptionGroups( (group.captionsExpandWildcards, group.exclusivity, group.combineTags) for group in self.groups.groups )
        rulesProcessor.setConditionalRules(self.conditionals.getFilterRules())
        return rulesProcessor



class CaptionContextDataSource(HighlightDataSource):
    def __init__(self, context: CaptionContext):
        super().__init__()
        self.ctx: CaptionContext = context

    def connectClearCache(self, slot: Slot):
        self.ctx.controlUpdated.connect(slot)

    def isHovered(self, caption: str) -> bool:
        return self.ctx.container.isHovered(caption)

    def getPresence(self, caption: str) -> TagPresence:
        multiEdit = self.ctx.container.multiEdit
        if multiEdit.active:
            return multiEdit.getPresence(caption)
        return TagPresence.FullPresence

    def getFocusSet(self) -> set[str]:
        return self.ctx.focus.getFocusSet()

    def getBanned(self) -> Iterable[str]:
        return self.ctx.settings.bannedCaptions

    def getGroups(self) -> Iterable[CaptionGroupData]:
        return (
            CaptionGroupData(group.captionsExpandWildcards, group.charFormat, group.color)
            for group in self.ctx.groups.groups
        )
