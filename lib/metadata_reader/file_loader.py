from __future__ import annotations

import os
from typing import Iterator

from .fields import MetadataField
from .field_extractors import jpeg, jxl, mp4, png, webp
from .markers import field_name_is_marked, field_needs_decomposing

VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov", ".qt", ".mp4v"}
_JXL_SIGNATURE = b"\x00\x00\x00\x0cJXL \r\n\x87\n"


def detect_format(path: str) -> str:
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


_EXTRACTORS = {
    "PNG":  png.extract_fields,
    "WEBP": webp.extract_fields,
    "JPEG": jpeg.extract_fields,
    "JXL":  jxl.extract_fields,
    "MP4":  mp4.extract_fields,
}


def load_fields(path: str) -> tuple[str, Iterator[MetadataField]]:
    """Returns (detected_format, iterator_of_fields). Unknown formats yield nothing."""
    path = os.fspath(path)
    fmt = detect_format(path)

    extractor = _EXTRACTORS.get(fmt)
    if extractor is None:
        return fmt, iter(())

    return fmt, _try_json_fields(extractor(path))


def _try_json_fields(fields: Iterator[MetadataField]) -> Iterator[MetadataField]:
    for field in fields:
        yield field

        if field_needs_decomposing(field.name):
            json_data = field.json_data()
            if isinstance(json_data, dict):
                yield from (
                    MetadataField(field.source, k, v) for k, v in json_data.items()
                    if field_name_is_marked(k)
                )
