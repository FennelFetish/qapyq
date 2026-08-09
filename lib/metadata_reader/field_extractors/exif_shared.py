"""
Shared EXIF-mapping logic used by the JPEG, WEBP, and JXL field extractors.

Only a small, known allow-list of EXIF tags is ever relevant to the tools
we support - translating tag ids to friendly names here, and dropping
everything else immediately, *is* this format's version of the cheap
"step 2" filter (see markers.py for the name-based version used by other
formats).
"""

from typing import Any, Iterator
from ..fields import FieldSource, MetadataField


EXIF_IFD_POINTER = 0x8769  # "Exif IFD" - holds UserComment, among others

# tag id -> friendly name, restricted to tags our supported tools actually use.
_RELEVANT_EXIF_TAGS = {
    0x9286: "usercomment",       # UserComment (A1111/SwarmUI/EasyDiffusion/NovelAI)
    0x010E: "imagedescription",  # ImageDescription (Midjourney, some A1111 JPEG writers)
    0x0131: "software",          # Software (NovelAI detection helper: value == "NovelAI")
    0x9C9B: "title",             # XPTitle (occasionally used by Midjourney-adjacent tools)
}


def exif_fields(exif) -> Iterator[MetadataField]:
    """
    Yield MetadataFields for the relevant tags in a Pillow Exif object.

    UserComment lives in the Exif sub-IFD (pointer 0x8769), not the
    top-level 0th IFD, so it has to be fetched explicitly - `dict(exif)`
    alone misses it.
    """
    merged: dict[Any, Any] = dict()
    try:
        merged.update(exif)
        sub = exif.get_ifd(EXIF_IFD_POINTER)
        if sub:
            merged.update(sub)
    except Exception:
        pass

    for tag_id, value in merged.items():
        if name := _RELEVANT_EXIF_TAGS.get(tag_id):
            yield MetadataField(source=FieldSource.EXIF, name=name, value=value)


_TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def parse_raw_exif(data: bytes) -> Iterator[MetadataField]:
    """
    Manual TIFF/IFD walk over a raw EXIF byte blob, for containers (JXL)
    where we deliberately avoid a full image decode just to read metadata,
    so a Pillow Exif object isn't available.
    """
    if len(data) < 8:
        return

    if data[:2] == b"II":
        endian = "little"
    elif data[:2] == b"MM":
        endian = "big"
    else:
        return

    def u16(o: int) -> int:
        return int.from_bytes(data[o:o + 2], endian)

    def u32(o: int) -> int:
        return int.from_bytes(data[o:o + 4], endian)

    def walk_ifd(offset: int, depth: int = 0):
        if depth > 4 or offset + 2 > len(data):
            return

        count = u16(offset)
        entry = offset + 2

        for _ in range(count):
            if entry + 12 > len(data):
                break

            tag, typ, cnt = u16(entry), u16(entry + 2), u32(entry + 4)
            size = _TYPE_SIZES.get(typ, 1) * cnt

            value_off = entry + 8
            if size > 4:
                value_off = u32(entry + 8)

            raw = data[value_off:value_off + size]

            if tag == 0x8769:  # ExifIFD pointer - the sub-IFD holding UserComment
                yield from walk_ifd(u32(entry + 8), depth + 1)
            else:
                name = _RELEVANT_EXIF_TAGS.get(tag)
                if name is not None:
                    yield MetadataField(source=FieldSource.EXIF, name=name, value=raw)

            entry += 12

    yield from walk_ifd(u32(4))
