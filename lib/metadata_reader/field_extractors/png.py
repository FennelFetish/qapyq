from typing import Iterator
from PIL import Image

from ..fields import FieldSource, MetadataField
from ..markers import field_name_is_marked


def _list_fields(img: Image.Image):
    # Some metadata is readable without loading the whole file - much faster
    if isinstance(img.info, dict):
        yield from img.info.items()

    # Fully load file only after some prompt extractors had the chance
    # to handle the initial img.info fields (potential early abort)
    img.load()

    # TODO: Is it necessary to check img.info again after full load?
    if isinstance(img.info, dict):
        yield from img.info.items()

    text_data = getattr(img, "text", None)
    if isinstance(text_data, dict):
        yield from text_data.items()


def extract_fields(path: str) -> Iterator[MetadataField]:
    """
    ComfyUI/InvokeAI/SwarmUI/Fooocus/NovelAI(legacy)/A1111 all store their
    metadata as tEXt/iTXt chunks. These trail the IDAT data for most
    writers, so Pillow only surfaces them in `im.text` once the file has
    been fully read - `im.load()` is required, we can't stop at header
    parsing the way we can for "is this even a PNG" sniffing.
    """

    with Image.open(path) as img:
        seen_names = set()

        for name, value in _list_fields(img):
            if field_name_is_marked(name) and name not in seen_names:
                seen_names.add(name)
                yield MetadataField(source=FieldSource.PNG_TEXT, name=name.strip().lower(), value=value)
