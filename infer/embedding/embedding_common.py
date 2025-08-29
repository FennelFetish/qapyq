from typing import NamedTuple


class EmbedSetting(NamedTuple):
    name: str
    cacheSuffix: str


PROCESSING = {
    "center-crop":              EmbedSetting("Center Crop", "centercrop"),
    "squish-resize":            EmbedSetting("Squish to Square", "squish"),
    "multipatch":               EmbedSetting("Multi Patch", "patches"),
    "multipatch-center-x":      EmbedSetting("Multi Patch (Force centering in landscape orientation)", "patches-x"),
    "multipatch-center-y":      EmbedSetting("Multi Patch (Force centering in portrait orientation)", "patches-y"),
    "multipatch-center-xy":     EmbedSetting("Multi Patch (Always force centering)", "patches-xy"),
}

DEFAULT_PROCESSING = "multipatch"
CONFIG_KEY_PROCESSING = "embed_method"


AGGREGATE = {
    "mean":     EmbedSetting("Mean", "mean"),
    "max":      EmbedSetting("Max", "max"),
}

DEFAULT_AGGREGATE = "mean"
CONFIG_KEY_AGGREGATE = "embed_aggregate"


CONFIG_KEY_PROMPT_TEMPLATE_FILE = "prompt_template_file"
CONFIG_KEY_PROMPT_TEMPLATES = "prompt_templates"
