"""
JPEG XL field extractor.

A "container" JXL file is boxed exactly like MP4 (4-byte size + 4-byte
fourcc, size==1 for a 64-bit extended size) - it just carries different
box types: 'Exif' and 'xml ' for metadata, 'jxlc'/'jxlp' for the actual
codestream (which we never read - metadata doesn't require decoding
pixels, so no libjxl/decoder dependency is needed here at all). A "naked"
JXL (bare codestream, no box container) has no box structure and
therefore no metadata by construction - that's a legitimate empty result.
"""

import os
from typing import Iterator

from ..fields import FieldSource, MetadataField
from ..markers import value_has_marker
from .exif_shared import parse_raw_exif
from .isobmff import iter_boxes, read_at

_SIGNATURE = b"\x00\x00\x00\x0cJXL \r\n\x87\n"
_CODESTREAM_TYPES = {b"jxlc", b"jxlp", b"jbrd"}  # never worth reading as text
MAX_BOX_READ_BYTES = 50 * 1024 * 1024


def extract_fields(path: str) -> Iterator[MetadataField]:
    with open(path, "rb") as f:
        head = f.read(len(_SIGNATURE))
        if head != _SIGNATURE:
            return  # naked codestream, or not a JXL file at all

        file_size = os.fstat(f.fileno()).st_size

        for box in iter_boxes(f, 0, file_size):
            if box.box_type in _CODESTREAM_TYPES or box.payload_size > MAX_BOX_READ_BYTES:
                continue

            if box.box_type == b"Exif":
                payload = read_at(f, box.payload_start, box.payload_size)
                # First 4 bytes are a "TIFF header offset" per the JXL spec.
                tiff = payload[4:]
                yield from parse_raw_exif(tiff)
            elif box.box_type == b"xml ":
                payload = read_at(f, box.payload_start, box.payload_size)
                if value_has_marker(payload):
                    yield MetadataField(source=FieldSource.XMP, name="xmp", value=payload)
