"""
MetadataField: the common unit every field extractor produces and every
prompt extractor consumes, regardless of which container format it came
from (PNG chunk, EXIF tag, MP4/JXL box, RIFF chunk, ...).
"""

import json
from dataclasses import dataclass, field as _dc_field
from enum import Enum, auto
from typing import Any


_MISSING = object()  # sentinel: text() / json_data() not attempted yet


class FieldSource(Enum):
    PNG_TEXT            = auto()    # PNG tEXt/iTXt/zTXt chunk
    EXIF                = auto()    # EXIF tag (JPEG/WEBP/JXL)
    XMP                 = auto()    # XMP packet (JPEG/WEBP/JXL)
    RIFF_CHUNK          = auto()    # raw WEBP RIFF chunk (not EXIF/XMP)
    MP4_BOX             = auto()    # MP4/ISO-BMFF box or ilst item
    CONTAINER_METADATA  = auto()    # PyAV container/stream metadata dict entry


@dataclass
class MetadataField:
    """
    One named metadata value.

    `name` is always a lowercase, human-readable string normalized by the
    field extractor that produced it (e.g. an EXIF tag id 0x9286 becomes
    "usercomment") so prompt extractors and the shared marker allow-list
    never have to deal with format-specific key encodings.
    """

    source: FieldSource
    name: str
    value: Any  # str | bytes | dict | list

    _json_cache: Any = _dc_field(default=_MISSING, repr=False, compare=False)
    _text_cache: Any = _dc_field(default=_MISSING, repr=False, compare=False)

    def json_data(self) -> Any:
        """
        Lazily parse `value` as JSON and cache the result (or None on
        failure/non-JSON) on this field instance, so repeated matches()
        calls from different prompt extractors never re-parse it.
        """
        if self._json_cache is _MISSING:
            self._json_cache = _parse_json(self.value)
        return self._json_cache

    def text(self) -> str | None:
        """Value as decoded text, or None if it can't be made into text."""
        if self._text_cache is _MISSING:
            self._text_cache = _to_text(self.value)
        return self._text_cache



def _parse_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value

    text = _to_text(value)
    if not text:
        return None

    text = text.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None

    # Some writers JSON-encode the value twice.
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            pass

    return parsed


def _to_text(value: Any) -> str | None:
    """Best-effort decode of a metadata value (str/bytes) to text."""
    if value is None:
        return None

    if isinstance(value, str):
        return value.rstrip("\x00")

    if isinstance(value, (bytes, bytearray, memoryview)):
        b = bytes(value)

        # EXIF UserComment charset prefixes (8 bytes).
        if b.startswith(b"ASCII\x00\x00\x00"):
            b = b[8:]
        elif b.startswith(b"UNICODE\x00"):
            # Per spec this should follow the TIFF header's declared byte
            # order; in practice writers are inconsistent, so detect it
            # from the data itself. For ASCII-heavy text (the common case
            # here - JSON), UTF-16LE has a 0x00 high byte immediately
            # *after* each character (odd byte positions), while UTF-16BE
            # has it immediately *before* (even positions). Counting
            # replacement characters after a wrong-endianness decode
            # doesn't work: byte-swapped ASCII often lands on valid-but-
            # wrong CJK codepoints rather than producing U+FFFD.
            payload = b[8:]
            even_zeros = sum(1 for i in range(0, len(payload), 2) if payload[i:i + 1] == b"\x00")
            odd_zeros = sum(1 for i in range(1, len(payload), 2) if payload[i:i + 1] == b"\x00")
            endian = "utf-16-le" if odd_zeros >= even_zeros else "utf-16-be"
            return payload.decode(endian, "replace").rstrip("\x00")
        elif b[:2] == b"\xff\xfe":
            return b.decode("utf-16-le", "replace").rstrip("\x00")
        elif b[:2] == b"\xfe\xff":
            return b.decode("utf-16-be", "replace").rstrip("\x00")

        b = b.rstrip(b"\x00")
        try:
            return b.decode("utf-8")
        except UnicodeDecodeError:
            return b.decode("latin-1", "replace")

    if isinstance(value, (list, tuple)):
        try:
            return _to_text(bytes(value))
        except Exception:
            return None

    return str(value)
