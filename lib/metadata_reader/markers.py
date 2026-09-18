"""
Shared, tool-agnostic allow-list used by *every* field extractor to reject
fields early, before any prompt extractor ever sees them. This is the
"step 2" cheap filter: a field extractor already has to touch a field's
name (and sometimes its raw bytes) to enumerate it at all, so checking it
against this list here is nearly free and cuts the candidate set down
before any JSON parsing or tool-specific logic runs.

Adding support for a new tool later means adding its field name here (and
a new prompt extractor) - field extractors themselves shouldn't need to
change.
"""

from typing import Any


# Field *names* (already normalized to lowercase by the field extractor
# that produced them) worth handing to the prompt-extractor stage.
FIELD_NAME_MARKERS = frozenset({
    "prompt", "workflow",                           # ComfyUI, "prompt" for EasyDiffusion
    "parameters",                                   # A1111/Forge/reForge/SD.Next/SwarmUI/Fooocus
    "invokeai_metadata", "invokeai_workflow",       # InvokeAI
    "usercomment",                                  # EXIF UserComment (A1111/SwarmUI/EasyDiffusion/NovelAI on JPEG/WEBP)
    "imagedescription", "description", "title",     # Midjourney / NovelAI legacy
    "comment", "fooocus",                           # Fooocus / NovelAI legacy
    "negative_prompt",                              # Easy Diffusion, when stored as its own chunk (PNG)
    "software",                                     # NovelAI detection helper
    "xmp",                                          # Draw Things and other XMP-based tools
})

# Raw byte substrings worth decoding+scanning when a field extractor finds
# an opaque blob (an MP4/JXL box payload, an unlabeled RIFF chunk, ...)
# that doesn't have a clean "name" the way a PNG chunk or EXIF tag does.
RAW_VALUE_MARKERS = (
    b'"prompt"',
    b'"workflow"',
    b'"negative_prompt"',
    b'"sui_image_params"',
    b'"invokeai_metadata"',
    b'"uc"',                    # NovelAI's "undesired content" (negative prompt) key
    b"Negative prompt:",
)


def field_name_is_marked(name: Any) -> bool:
    return isinstance(name, str) and name.strip().lower() in FIELD_NAME_MARKERS

def field_needs_decomposing(name: Any) -> bool:
    # "usercomment" fields should be parsed to JSON and its keys rechecked against FIELD_NAME_MARKERS
    return isinstance(name, str) and name.strip().lower() == "usercomment"

def value_has_marker(raw: bytes) -> bool:
    return any(marker in raw for marker in RAW_VALUE_MARKERS)
