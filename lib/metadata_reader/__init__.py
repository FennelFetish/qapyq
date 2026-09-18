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

import os
from itertools import chain
from typing import Iterator

from .fields import MetadataField
from .field_extraction import FIELD_EXTRACTORS
from .prompt_extraction import EARLY_EXIT_EXTRACTORS, FALLBACK_EXTRACTORS, PromptEntry, PromptKind
from .markers import field_name_is_marked, field_needs_decomposing

__all__ = ["extract_prompts", "PromptEntry", "PromptKind", "MetadataField"]


VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".qt", ".mp4v"}
_JXL_SIGNATURE = b"\x00\x00\x00\x0cJXL \r\n\x87\n"

def _detect_format(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        head = f.read(16)

    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "WEBP"
    if head.startswith(_JXL_SIGNATURE) or ext == ".jxl":
        return "JXL"
    if head[:2] == b"\xff\xd8":
        return "JPEG"
    if (len(head) >= 8 and head[4:8] in (b"ftyp", b"styp")) or ext in VIDEO_EXTENSIONS:
        return "MP4"

    return "UNKNOWN"


def extract_prompts(path: str, exhaustive: bool = False) -> list[PromptEntry]:
    fmt = _detect_format(os.fspath(path))
    field_extractor_type = FIELD_EXTRACTORS.get(fmt)
    if field_extractor_type is None:
        return []

    fields: dict[str, MetadataField] = {}

    with field_extractor_type(path) as field_extractor:
        # 1. Fast field extraction from accessible metadata only
        results = _try_extract_prompt(fields, field_extractor.extract_fields())
        if results is not None:
            return results

        # 2. Exhaustive search loads the full file, then retries field extraction
        if exhaustive:
            results = _try_extract_prompt(fields, field_extractor.extract_fields_slow())
            if results is not None:
                return results

        return []


def _try_extract_prompt(fields: dict[str, MetadataField], field_iter: Iterator[MetadataField]) -> list[PromptEntry] | None:
    seen_names = set[str]()
    for field in _with_json_decompose(field_iter):
        if not field.value:
            #print(f">>> EMPTY FIELD (ignore): {field.name}")
            continue

        if field.name not in seen_names:
            seen_names.add(field.name)
            fields[field.name] = field
        # else:
        #     print(f">>> DUPLICATE FIELD (ignore): {field.name}")

    #_print_fields(fields)

    for extractor in chain(EARLY_EXIT_EXTRACTORS, FALLBACK_EXTRACTORS):
        result = extractor.try_extract(fields)
        if result is not None:
            return result

    return None


def _with_json_decompose(fields: Iterator[MetadataField]) -> Iterator[MetadataField]:
    for field in fields:
        yield field

        if field_needs_decomposing(field.name):
            json_data = field.json_data()
            if isinstance(json_data, dict):
                yield from (
                    MetadataField(field.source, name, val) for name, val in json_data.items()
                    if field_name_is_marked(name)
                )


def _print_fields(fields: dict[str, MetadataField]):
    print(f"=== FIELDS ({len(fields)}) ===")
    for name, field in fields.items():
        text = field.text() or ""
        print(f"  {name}: {text[:150]}")
