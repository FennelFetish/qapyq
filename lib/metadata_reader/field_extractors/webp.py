from typing import Iterator
from PIL import Image

from ..fields import FieldSource, MetadataField
from ..markers import field_name_is_marked, value_has_marker
from .exif_shared import exif_fields


def _iter_riff_chunks(data: bytes) -> Iterator[tuple[str, bytes]]:
    """RIFF chunks: RIFF....WEBP [fourcc][size][payload], padded to even size."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return

    pos, n = 12, len(data)
    while pos + 8 <= n:
        fourcc = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        start, end = pos + 8, pos + 8 + size
        if end > n:
            return

        yield fourcc.decode("ascii", "replace"), data[start:end]
        pos = end + (size & 1)


def extract_fields(path: str) -> Iterator[MetadataField]:
    # Pillow surfaces WEBP's EXIF/XMP through the normal Image API - this
    # is what correctly decodes UTF-16 EXIF UserComment fields, so it must
    # run regardless of what the raw bytes look like (a raw substring
    # pre-filter would miss UTF-16 text, since `"prompt"` as UTF-16 bytes
    # doesn't contain the ASCII bytes b'"prompt"').
    with Image.open(path) as img:
        img.load()
        for name, value in (img.info or {}).items():
            if field_name_is_marked(name):
                yield MetadataField(source=FieldSource.RIFF_CHUNK, name=name.strip().lower(), value=value)

        try:
            yield from exif_fields(img.getexif())
        except Exception:
            pass

    # Fallback: some writers put an XMP/JSON packet directly in a RIFF
    # chunk without Pillow surfacing it via `img.info`. Only worth reading
    # the whole file for this if the cheap marker check on raw bytes hits.
    with open(path, "rb") as f:
        data = f.read()

    if not value_has_marker(data):
        return

    for fourcc, payload in _iter_riff_chunks(data):
        if fourcc.strip() in ("EXIF",):
            continue  # already handled via Pillow above
        if fourcc.strip() in ("XMP", "JSON", "META") and value_has_marker(payload):
            yield MetadataField(source=FieldSource.XMP if fourcc.strip() == "XMP" else FieldSource.RIFF_CHUNK,
                                 name="xmp" if fourcc.strip() == "XMP" else fourcc.strip().lower(),
                                 value=payload)
