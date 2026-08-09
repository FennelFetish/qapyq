"""
Shared box-reading primitive for ISO-BMFF-family containers.

MP4/MOV and container-mode JPEG XL are both structured as a flat sequence
of [4-byte size][4-byte fourcc][payload] boxes (with a 64-bit extended
size when size == 1). This module knows nothing about what any particular
box *means* - that's up to the MP4 and JXL field extractors, which each
interpret the box stream differently but share this same low-level walk.
"""

from typing import BinaryIO, NamedTuple, Optional


class Box(NamedTuple):
    box_type: bytes
    payload_start: int
    payload_size: int
    next_offset: int


def read_box_header(f: BinaryIO, offset: int, end: int) -> Optional[Box]:
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

    return Box(box_type, payload_start, payload_size, next_offset)


def iter_boxes(f: BinaryIO, start: int, end: int):
    """Iterate sibling boxes in [start, end) - does not recurse into children."""
    offset = start
    while offset + 8 <= end:
        box = read_box_header(f, offset, end)
        if not box or box.next_offset <= offset:
            return
        yield box
        offset = box.next_offset


def read_at(f: BinaryIO, offset: int, size: int) -> bytes:
    if size <= 0:
        return b""
    f.seek(offset)
    return f.read(size)
