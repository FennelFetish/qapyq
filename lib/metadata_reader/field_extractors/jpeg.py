from typing import Iterator
from PIL import Image

from ..fields import FieldSource, MetadataField
from ..markers import value_has_marker
from .exif_shared import exif_fields


def extract_fields(path: str) -> Iterator[MetadataField]:
    """
    JPEG has no PNG-style arbitrary tEXt chunk mechanism; A1111/SwarmUI/
    EasyDiffusion/NovelAI/Midjourney all place their data in EXIF
    (UserComment or ImageDescription), and some tools use XMP instead.
    """
    with Image.open(path) as img:
        img.load()
        try:
            yield from exif_fields(img.getexif())
        except Exception:
            pass

        xmp = (img.info or {}).get("xmp")
        if xmp:
            raw = xmp if isinstance(xmp, bytes) else str(xmp).encode("utf-8", "replace")
            if value_has_marker(raw):
                yield MetadataField(source=FieldSource.XMP, name="xmp", value=xmp)
