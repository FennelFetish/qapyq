"""
MP4/ISO-BMFF field extractor.

ComfyUI's VideoHelperSuite (VHS_VideoCombine) node is the de facto way
local video-model output (Wan/HunyuanVideo/LTX-Video/...) gets muxed into
a file. For MP4 output specifically it writes the same "prompt"/"workflow"
keys as PNG, via a custom mdta 'keys' box + 'ilst' items (or via a plain
ffmpeg -metadata comment field, which PyAV/ffmpeg exposes as container
metadata). WebM output uses a completely different container (Matroska)
and is NOT handled here - it would need a separate extractor.
"""

import os
from typing import BinaryIO, Iterator
from itertools import chain

from ..fields import FieldSource, MetadataField
from ..markers import field_name_is_marked, value_has_marker
from .isobmff import Box, iter_boxes, read_at

_CONTAINER_TYPES = {b"moov", b"trak", b"mdia", b"minf", b"udta", b"edts", b"dinf"}
_SKIP_TYPES = {b"mdat", b"stbl", b"free", b"skip", b"wide"}
_METADATA_BOX_TYPES = {b"uuid", b"XMP_", b"\xa9cmt", b"desc", b"ldes"}
_COVER_ATOMS = {b"covr"}  # binary image data - never worth text-scanning

MAX_BOX_READ_BYTES = 50 * 1024 * 1024


def _parse_keys_box(f: BinaryIO, box: Box) -> dict[int, str]:
    """Parse an MP4 'keys' box (custom metadata key names some writers use)."""
    if box.payload_size <= 0 or box.payload_size > MAX_BOX_READ_BYTES:
        return {}

    data = read_at(f, box.payload_start, box.payload_size)
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


def _iter_ilst_items(f: BinaryIO, start: int, end: int, keys_map: dict[int, str]) -> Iterator[MetadataField]:
    for item in iter_boxes(f, start, end):
        if item.box_type in _COVER_ATOMS:
            continue

        name_text = None
        values = []
        for child in iter_boxes(f, item.payload_start, item.payload_start + item.payload_size):
            if child.box_type == b"data" and child.payload_size <= MAX_BOX_READ_BYTES:
                payload = read_at(f, child.payload_start, child.payload_size)
                # 'data' atom: 4B type indicator, 4B locale, then the value.
                values.append(payload[8:] if len(payload) > 8 else payload)
            elif child.box_type == b"name" and child.payload_size <= MAX_BOX_READ_BYTES:
                name_text = read_at(f, child.payload_start, child.payload_size).decode("utf-8", "replace")

        key_name = name_text or keys_map.get(int.from_bytes(item.box_type, "big"))
        if key_name and field_name_is_marked(key_name):
            for value in values:
                yield MetadataField(source=FieldSource.MP4_BOX, name=key_name.strip().lower(), value=value)


def _walk(f: BinaryIO, start: int, end: int, file_size: int, keys_map: dict[int, str], depth: int, in_udta: bool) -> Iterator[MetadataField]:
    if depth > 10 or start >= end:
        return

    for box in iter_boxes(f, start, end):
        if box.box_type == b"meta":
            # FullBox: first 4 bytes are version/flags.
            meta_start, meta_end = box.payload_start + 4, box.payload_start + box.payload_size
            local_keys = dict(keys_map)
            for child in iter_boxes(f, meta_start, meta_end):
                if child.box_type == b"keys":
                    local_keys.update(_parse_keys_box(f, child))

            yield from _walk(f, meta_start, meta_end, file_size, local_keys, depth + 1, True)

        elif box.box_type == b"ilst":
            yield from _iter_ilst_items(f, box.payload_start, box.payload_start + box.payload_size, keys_map)

        elif box.box_type in _SKIP_TYPES:
            pass  # e.g. mdat: the actual media payload, never read

        elif box.box_type in _CONTAINER_TYPES:
            yield from _walk(f, box.payload_start, box.payload_start + box.payload_size,
                              file_size, keys_map, depth + 1, in_udta or box.box_type == b"udta")

        elif in_udta or box.box_type in _METADATA_BOX_TYPES:
            if box.payload_size <= MAX_BOX_READ_BYTES:
                payload = read_at(f, box.payload_start, box.payload_size)
                if payload and value_has_marker(payload):
                    field_name = box.box_type.decode("ascii", "replace").strip().lower()
                    yield MetadataField(source=FieldSource.MP4_BOX, name=field_name, value=payload)


def _extract_boxes(path: str) -> Iterator[MetadataField]:
    try:
        with open(path, "rb") as f:
            file_size = os.fstat(f.fileno()).st_size
            yield from _walk(f, 0, file_size, file_size, keys_map={}, depth=0, in_udta=False)
    except OSError:
        return


def _extract_pyav_container_metadata(path: str) -> Iterator[MetadataField]:
    """Container/stream-level tags written via e.g. `ffmpeg -metadata comment=...`."""
    try:
        import av
    except ImportError:
        return

    try:
        with av.open(path, mode="r") as container:
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


def extract_fields(path: str) -> Iterator[MetadataField]:
    seen_names = set()
    for f in _extract_pyav_container_metadata(path):
        seen_names.add(f.name)
        yield f

    # The box walk is a fallback for what it missed
    for f in _extract_boxes(path):
        if f.name not in seen_names:
            seen_names.add(f.name)
            yield f
