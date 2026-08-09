"""
Extract generation prompts from image/video files across multiple
generative AI tools (ComfyUI, A1111/Forge/reForge/SD.Next, InvokeAI,
SwarmUI, Fooocus, Easy Diffusion, NovelAI legacy, Midjourney) and
container formats (PNG, WEBP, JPEG, JXL, MP4).

Architecture:
    file_loader         -> picks a field extractor by container format
    field extractor     -> yields MetadataField objects, cheaply pre-filtered
                           against the shared marker allow-list (markers.py)
    prompt_extraction   -> two-tier dispatch over the accumulated fields:
                           EARLY_EXIT_EXTRACTORS are tried after every new
                           field arrives and stop the whole process (and any
                           further file reads) the instant one commits;
                           FALLBACK_EXTRACTORS only run once field extraction
                           is exhausted, over the complete field list, in a
                           fixed priority order.

Public API:
    extract_prompts(path) -> list[PromptEntry]
    extract_fields(path)  -> (format, list[MetadataField])   [for debugging]
"""

from .fields import MetadataField
from .file_loader import load_fields
from .prompt_extraction import EARLY_EXIT_EXTRACTORS, FALLBACK_EXTRACTORS, PromptEntry, PromptKind

__all__ = ["extract_prompts", "extract_fields", "PromptEntry", "PromptKind", "MetadataField"]


def extract_fields(path: str) -> tuple[str, list[MetadataField]]:
    """Low-level: the detected format and every field that survived the marker filter."""
    fmt, fields = load_fields(path)
    return fmt, list(fields)


def extract_prompts(path: str) -> list[PromptEntry]:
    """
    Extract every prompt found in `path`. Stops reading the file the
    moment an early-exit-eligible tool (ComfyUI/SwarmUI/InvokeAI) commits;
    otherwise falls back to a fixed-priority pass over every field once
    extraction is exhausted.
    """
    fmt, field_iter = load_fields(path)
    fields: list[MetadataField] = []

    try:
        for f in field_iter:
            fields.append(f)

            for extractor in EARLY_EXIT_EXTRACTORS:
                result = extractor.try_extract(fields)
                if result is not None:
                    #print(f"{path}: recognized as {extractor.__name__} (early-exit, {len(accumulated)} field(s))")
                    return result

    finally:
        # Stop any in-progress file reads if we returned early above -
        # field extractors are generators wrapping an open file; a plain
        # iterator (e.g. the empty one for an unrecognized format) has no
        # close() to call.
        if close := getattr(field_iter, "close", None):
            close()

    for extractor in FALLBACK_EXTRACTORS:
        result = extractor.try_extract(fields)
        if result is not None:
            #print(f"{path}: recognized as {extractor.__name__} (fallback, {len(accumulated)} field(s))")
            return result

    return []
