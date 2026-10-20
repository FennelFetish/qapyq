import os
from typing import Any, Iterator, BinaryIO, NamedTuple, Protocol
from abc import ABC, abstractmethod
from itertools import chain
from PIL import Image

from .fields import FieldSource, MetadataField
from .markers import value_has_marker, field_name_is_marked



# ---------------------------------------------------------------------
# interface
# ---------------------------------------------------------------------

class SupportsClose(Protocol):
    def close(self) -> Any: ...


class FieldExtractor(ABC):
    def __init__(self, path: str):
        self.path = path
        self._closables: list[SupportsClose] = []

    @abstractmethod
    def extract_fields(self) -> Iterator[MetadataField]:
        ...

    def extract_fields_slow(self) -> Iterator[MetadataField]:
        return iter(())

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        for closable in self._closables:
            closable.close()
        return False



# ---------------------------------------------------------------------
# utilities
# ---------------------------------------------------------------------

class ExifUtil:
    EXIF_IFD_POINTER = 0x8769  # "Exif IFD" - holds UserComment, among others

    # tag id -> friendly name, restricted to tags our supported tools actually use.
    _RELEVANT_EXIF_TAGS = {
        0x9286: "usercomment",       # UserComment (A1111/SwarmUI/EasyDiffusion/NovelAI)
        0x010E: "imagedescription",  # ImageDescription (Midjourney, some A1111 JPEG writers)
        0x0131: "software",          # Software (NovelAI detection helper: value == "NovelAI")
        0x9C9B: "title",             # XPTitle (occasionally used by Midjourney-adjacent tools)
    }


    @classmethod
    def exif_fields(cls, exif) -> Iterator[MetadataField]:
        """
        Yield MetadataFields for the relevant tags in a Pillow Exif object.

        UserComment lives in the Exif sub-IFD (pointer 0x8769), not the
        top-level 0th IFD, so it has to be fetched explicitly - `dict(exif)`
        alone misses it.
        """
        merged: dict[Any, Any] = dict()
        try:
            merged.update(exif)
            sub = exif.get_ifd(cls.EXIF_IFD_POINTER)
            if sub:
                merged.update(sub)
        except Exception:
            pass

        for tag_id, value in merged.items():
            if name := cls._RELEVANT_EXIF_TAGS.get(tag_id):
                yield MetadataField(source=FieldSource.EXIF, name=name, value=value)


    _TYPE_SIZES = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


    @classmethod
    def parse_raw_exif(cls, data: bytes) -> Iterator[MetadataField]:
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
                size = cls._TYPE_SIZES.get(typ, 1) * cnt

                value_off = entry + 8
                if size > 4:
                    value_off = u32(entry + 8)

                raw = data[value_off:value_off + size]

                if tag == 0x8769:  # ExifIFD pointer - the sub-IFD holding UserComment
                    yield from walk_ifd(u32(entry + 8), depth + 1)
                else:
                    name = cls._RELEVANT_EXIF_TAGS.get(tag)
                    if name is not None:
                        yield MetadataField(source=FieldSource.EXIF, name=name, value=raw)

                entry += 12

        yield from walk_ifd(u32(4))



class IsoBmffUtil:
    MAX_BOX_READ_BYTES = 50 * 1024 * 1024

    class Box(NamedTuple):
        box_type: bytes
        payload_start: int
        payload_size: int
        next_offset: int

    @classmethod
    def read_box_header(cls, f: BinaryIO, offset: int, end: int) -> Box | None:
        """Read one box header at `offset`, clamped to `end` (usually file size)."""
        if offset + 8 > end:
            return None

        f.seek(offset)
        header = f.read(8)
        if len(header) < 8:
            return None

        size = int.from_bytes(header[:4], "big")
        box_type = header[4:8]
        header_size = 8

        if size == 1:
            largesize = f.read(8)
            if len(largesize) < 8:
                return None
            size = int.from_bytes(largesize, "big")
            header_size = 16
        elif size == 0:
            size = end - offset  # box extends to end of the searched range

        if size < header_size:
            return None

        payload_start = offset + header_size
        payload_size = size - header_size
        next_offset = offset + size

        if next_offset > end:
            # Truncated/invalid; clamp instead of seeking past the range.
            payload_size = max(0, end - payload_start)
            next_offset = end

        return cls.Box(box_type, payload_start, payload_size, next_offset)

    @classmethod
    def iter_boxes(cls, f: BinaryIO, start: int, end: int):
        """Iterate sibling boxes in [start, end) - does not recurse into children."""
        offset = start
        while offset + 8 <= end:
            box = cls.read_box_header(f, offset, end)
            if not box or box.next_offset <= offset:
                return
            yield box
            offset = box.next_offset

    @staticmethod
    def read_at(f: BinaryIO, offset: int, size: int) -> bytes:
        if size <= 0:
            return b""
        f.seek(offset)
        return f.read(size)



# ---------------------------------------------------------------------
# file formats
# ---------------------------------------------------------------------

class JPEG(FieldExtractor):
    def __init__(self, path: str):
        super().__init__(path)
        self.img = Image.open(path)
        self._closables.append(self.img)

    def extract_fields(self) -> Iterator[MetadataField]:
        """
        JPEG has no PNG-style arbitrary tEXt chunk mechanism; A1111/SwarmUI/
        EasyDiffusion/NovelAI/Midjourney all place their data in EXIF
        (UserComment or ImageDescription), and some tools use XMP instead.
        """

        exif = getattr(self.img, "_exif", None)
        if not exif:
            exif = self.img.getexif() # Slow

        yield from ExifUtil.exif_fields(exif)

        if xmp := (self.img.info or {}).get("xmp"):
            raw = xmp if isinstance(xmp, bytes) else str(xmp).encode("utf-8", "replace")
            if value_has_marker(raw):
                yield MetadataField(source=FieldSource.XMP, name="xmp", value=xmp)

    def extract_fields_slow(self) -> Iterator[MetadataField]:
        self.img.load()
        yield from self.extract_fields()




class JXL(FieldExtractor):
    SIGNATURE = b"\x00\x00\x00\x0cJXL \r\n\x87\n"
    CODESTREAM_TYPES = {b"jxlc", b"jxlp", b"jbrd"}  # never worth reading as text

    def extract_fields(self) -> Iterator[MetadataField]:
        with open(self.path, "rb") as f:
            head = f.read(len(self.SIGNATURE))
            if head != self.SIGNATURE:
                return  # naked codestream, or not a JXL file at all

            file_size = os.fstat(f.fileno()).st_size

            for box in IsoBmffUtil.iter_boxes(f, 0, file_size):
                if box.box_type in self.CODESTREAM_TYPES or box.payload_size > IsoBmffUtil.MAX_BOX_READ_BYTES:
                    continue

                if box.box_type == b"Exif":
                    payload = IsoBmffUtil.read_at(f, box.payload_start, box.payload_size)
                    # First 4 bytes are a "TIFF header offset" per the JXL spec.
                    tiff = payload[4:]
                    yield from ExifUtil.parse_raw_exif(tiff)
                elif box.box_type == b"xml ":
                    payload = IsoBmffUtil.read_at(f, box.payload_start, box.payload_size)
                    if value_has_marker(payload):
                        yield MetadataField(source=FieldSource.XMP, name="xmp", value=payload)



class PNG(FieldExtractor):
    def __init__(self, path: str):
        super().__init__(path)
        self.img = Image.open(path)
        self._closables.append(self.img)

    def extract_fields(self) -> Iterator[MetadataField]:
        """
        ComfyUI/InvokeAI/SwarmUI/Fooocus/NovelAI(legacy)/A1111 all store their
        metadata as tEXt/iTXt chunks. These trail the IDAT data for most
        writers, so Pillow only surfaces them in `im.text` once the file has
        been fully read - `im.load()` is required, we can't stop at header
        parsing the way we can for "is this even a PNG" sniffing.
        """

        for name, value in (self.img.info or {}).items():
            if field_name_is_marked(name):
                yield MetadataField(source=FieldSource.PNG_TEXT, name=name.strip().lower(), value=value)

    def extract_fields_slow(self) -> Iterator[MetadataField]:
        # Some metadata is readable without loading the whole file - much faster.
        # Fully load file only after some prompt extractors had the chance
        # to handle the initial img.info fields (potential early abort)
        self.img.load()

        # TODO: Is it necessary to check img.info again after full load?
        yield from self.extract_fields()

        # Access to 'text' property of PIL.PngImagePlugin will load the file
        text_data = getattr(self.img, "text", None) or {}
        for name, value in text_data.items():
            if field_name_is_marked(name):
                yield MetadataField(source=FieldSource.PNG_TEXT, name=name.strip().lower(), value=value)



class WEBP(FieldExtractor):
    def __init__(self, path: str):
        super().__init__(path)
        self.img = Image.open(self.path)
        self._closables.append(self.img)

    def extract_fields(self) -> Iterator[MetadataField]:
        # Pillow surfaces WEBP's EXIF/XMP through the normal Image API - this
        # is what correctly decodes UTF-16 EXIF UserComment fields, so it must
        # run regardless of what the raw bytes look like (a raw substring
        # pre-filter would miss UTF-16 text, since `"prompt"` as UTF-16 bytes
        # doesn't contain the ASCII bytes b'"prompt"').
        for name, value in (self.img.info or {}).items():
            if field_name_is_marked(name):
                yield MetadataField(source=FieldSource.RIFF_CHUNK, name=name.strip().lower(), value=value)

        exif = getattr(self.img, "_exif", None)
        if not exif:
            exif = self.img.getexif() # Slow

        yield from ExifUtil.exif_fields(exif)

    def extract_fields_slow(self) -> Iterator[MetadataField]:
        self.img.load()
        yield from self.extract_fields()

        # Fallback: some writers put an XMP/JSON packet directly in a RIFF
        # chunk without Pillow surfacing it via `img.info`. Only worth reading
        # the whole file for this if the cheap marker check on raw bytes hits.
        file = open(self.path, "rb")
        self._closables.append(file)
        data = file.read() # Reading the file twice (PIL and here) is actually a bit faster than feeding the bytes to PIL

        if not value_has_marker(data):
            return

        for fourcc, payload in self._iter_riff_chunks(data):
            fourcc_type = fourcc.strip()
            if fourcc_type == "EXIF":
                continue  # already handled via Pillow above

            if fourcc_type in ("XMP", "JSON", "META") and value_has_marker(payload):
                source = FieldSource.XMP if fourcc_type == "XMP" else FieldSource.RIFF_CHUNK
                yield MetadataField(source=source, name=fourcc_type.lower(), value=payload)

    @staticmethod
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



class MP4(FieldExtractor):
    CONTAINER_TYPES = {b"moov", b"trak", b"mdia", b"minf", b"udta", b"edts", b"dinf"}
    SKIP_TYPES = {b"mdat", b"stbl", b"free", b"skip", b"wide"}
    METADATA_BOX_TYPES = {b"uuid", b"XMP_", b"\xa9cmt", b"desc", b"ldes"}
    COVER_ATOMS = {b"covr"}  # binary image data - never worth text-scanning


    def extract_fields(self) -> Iterator[MetadataField]:
        """Container/stream-level tags written via e.g. `ffmpeg -metadata comment=...`."""
        try:
            import av
        except ImportError:
            return

        try:
            with av.open(self.path, mode="r") as container:
                metadatas = chain(
                    (getattr(container, "metadata", None),),
                    (getattr(stream, "metadata", None) for stream in container.streams)
                )

                for meta in filter(None, metadatas):
                    for name, value in dict(meta).items():
                        if field_name_is_marked(name):
                            yield MetadataField(source=FieldSource.CONTAINER_METADATA, name=str(name).strip().lower(), value=value)

        except Exception:
            return


    def extract_fields_slow(self) -> Iterator[MetadataField]:
        try:
            with open(self.path, "rb") as f:
                file_size = os.fstat(f.fileno()).st_size
                yield from self._walk(f, 0, file_size, file_size, keys_map={}, depth=0, in_udta=False)
        except OSError:
            return


    @classmethod
    def _parse_keys_box(cls, f: BinaryIO, box: IsoBmffUtil.Box) -> dict[int, str]:
        """Parse an MP4 'keys' box (custom metadata key names some writers use)."""
        if box.payload_size <= 0 or box.payload_size > IsoBmffUtil.MAX_BOX_READ_BYTES:
            return {}

        data = IsoBmffUtil.read_at(f, box.payload_start, box.payload_size)
        if len(data) < 8:
            return {}

        count = int.from_bytes(data[4:8], "big")  # FullBox: 4B version/flags, 4B count
        keys: dict[int, str] = {}
        pos = 8

        for i in range(1, count + 1):
            if pos + 8 > len(data):
                break
            key_size = int.from_bytes(data[pos:pos + 4], "big")
            if key_size < 8 or pos + key_size > len(data):
                break
            keys[i] = data[pos + 8:pos + key_size].decode("utf-8", "replace")
            pos += key_size

        return keys


    @classmethod
    def _iter_ilst_items(cls, f: BinaryIO, start: int, end: int, keys_map: dict[int, str]) -> Iterator[MetadataField]:
        for item in IsoBmffUtil.iter_boxes(f, start, end):
            if item.box_type in cls.COVER_ATOMS:
                continue

            name_text = None
            values = []
            for child in IsoBmffUtil.iter_boxes(f, item.payload_start, item.payload_start + item.payload_size):
                if child.box_type == b"data" and child.payload_size <= IsoBmffUtil.MAX_BOX_READ_BYTES:
                    payload = IsoBmffUtil.read_at(f, child.payload_start, child.payload_size)
                    # 'data' atom: 4B type indicator, 4B locale, then the value.
                    values.append(payload[8:] if len(payload) > 8 else payload)
                elif child.box_type == b"name" and child.payload_size <= IsoBmffUtil.MAX_BOX_READ_BYTES:
                    name_text = IsoBmffUtil.read_at(f, child.payload_start, child.payload_size).decode("utf-8", "replace")

            key_name = name_text or keys_map.get(int.from_bytes(item.box_type, "big"))
            if key_name and field_name_is_marked(key_name):
                for value in values:
                    yield MetadataField(source=FieldSource.MP4_BOX, name=key_name.strip().lower(), value=value)

    @classmethod
    def _walk(cls, f: BinaryIO, start: int, end: int, file_size: int, keys_map: dict[int, str], depth: int, in_udta: bool) -> Iterator[MetadataField]:
        if depth > 10 or start >= end:
            return

        for box in IsoBmffUtil.iter_boxes(f, start, end):
            if box.box_type == b"meta":
                # FullBox: first 4 bytes are version/flags.
                meta_start, meta_end = box.payload_start + 4, box.payload_start + box.payload_size
                local_keys = dict(keys_map)
                for child in IsoBmffUtil.iter_boxes(f, meta_start, meta_end):
                    if child.box_type == b"keys":
                        local_keys.update(cls._parse_keys_box(f, child))

                yield from cls._walk(f, meta_start, meta_end, file_size, local_keys, depth + 1, True)

            elif box.box_type == b"ilst":
                yield from cls._iter_ilst_items(f, box.payload_start, box.payload_start + box.payload_size, keys_map)

            elif box.box_type in cls.SKIP_TYPES:
                pass  # e.g. mdat: the actual media payload, never read

            elif box.box_type in cls.CONTAINER_TYPES:
                yield from cls._walk(f, box.payload_start, box.payload_start + box.payload_size,
                                file_size, keys_map, depth + 1, in_udta or box.box_type == b"udta")

            elif in_udta or box.box_type in cls.METADATA_BOX_TYPES:
                if box.payload_size <= IsoBmffUtil.MAX_BOX_READ_BYTES:
                    payload = IsoBmffUtil.read_at(f, box.payload_start, box.payload_size)
                    if payload and value_has_marker(payload):
                        field_name = box.box_type.decode("ascii", "replace").strip().lower()
                        yield MetadataField(source=FieldSource.MP4_BOX, name=field_name, value=payload)



FIELD_EXTRACTORS: dict[str, type[FieldExtractor]] = {
    "JPEG": JPEG,
    "JXL":  JXL,
    "MP4":  MP4,
    "PNG":  PNG,
    "WEBP": WEBP,
}
