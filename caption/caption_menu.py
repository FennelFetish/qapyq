from enum import Enum
from PySide6 import QtWidgets
from PySide6.QtCore import Signal, Slot
from config import Config


class RulesLoadMode(Enum):
    Empty    = "empty"
    Defaults = "defaults"
    Previous = "previous"


class CaptionMenu(QtWidgets.QMenu):
    previewToggled = Signal(bool)


    def __init__(self, parent, context):
        super().__init__(parent)

        from .caption_container import CaptionContext
        self.ctx: CaptionContext = context

        self._build()
        self.aboutToShow.connect(self._updateMenu)


    def _build(self):
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

        actPreview = self.addAction("Show refined preview")
        actPreview.setCheckable(True)
        actPreview.setChecked(Config.captionShowPreview)
        actPreview.toggled.connect(self.previewToggled)


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
