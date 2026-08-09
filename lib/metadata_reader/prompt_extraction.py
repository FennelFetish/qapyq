"""
Prompt extraction: one function per supported tool, plus two ordered
dispatch lists.

Two tiers:

EARLY_EXIT_EXTRACTORS - tools whose data is self-contained in one field
    whose shape can't plausibly belong to any other tool (ComfyUI,
    SwarmUI, InvokeAI). Checked after every new field arrives, against the
    full list of fields accumulated so far; the moment one commits,
    dispatch stops and no further fields are even read from the file.

FALLBACK_EXTRACTORS - tools that need to correlate several fields
    together, or whose single-field signal is genuinely ambiguous with
    another tool's (NovelAI's positive prompt can live in a separate
    "description" field from its "uc"/negative pair, with only a
    "software" field tying them together; a bare text field alone looks
    identical to Midjourney's). These only run once field extraction is
    exhausted, over the complete field list, in a fixed priority order -
    never mid-stream, since committing early here could preempt a later
    field that would tell a different, more correct story (this is
    exactly how a NovelAI image was once misclassified as Midjourney: a
    bare "description" field looked like a Midjourney prompt before the
    "software"/"comment" fields further along the stream ever got a
    chance to say otherwise).

Each function takes the full list of fields collected so far and returns:
    None       - not our tool (based on what's been seen so far)
    []         - our tool, but nothing to extract
    [entries]  - success
"""

from __future__ import annotations

import enum, re
from typing import Any, Iterator, NamedTuple, TypeVar

from .fields import MetadataField


class PromptKind(enum.IntEnum):
    POSITIVE = 1    # Start with 1, all truthy values
    NEGATIVE = 2
    TEXT     = 3    # generic text - most ComfyUI node inputs land here,
                    # since positive/negative isn't resolvable without
                    # following graph links (deferred to a later pass)

    def key(self, default: str = "other"):
        return PROMPT_KIND_KEYS.get(self, default)


PROMPT_KIND_KEYS = {
    PromptKind.POSITIVE: "prompt",
    PromptKind.NEGATIVE: "negative_prompt",
    PromptKind.TEXT:     "text",
}


class PromptEntry(NamedTuple):
    text: str
    kind: PromptKind

    def __lt__(self, other: PromptEntry) -> bool:
        return self.kind.value < other.kind.value


Fields = list[MetadataField]
Result = list[PromptEntry] | None


# ---------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------

def _find(fields: Fields, name: str) -> MetadataField | None:
    return next((f for f in fields if f.name == name), None)

def _find_json_dict(fields: Fields, *, has_all: tuple = (), has_any: tuple = ()) -> tuple[MetadataField, dict] | None:
    """First field whose JSON value is a dict satisfying the key requirements."""
    for f in fields:
        data = f.json_data()
        if not isinstance(data, dict):
            continue

        if has_all and not all(k in data for k in has_all):
            continue

        if has_any and not any(k in data for k in has_any):
            continue

        return f, data

    return None


def _entry(value, kind: PromptKind) -> PromptEntry | None:
    return PromptEntry(text=value, kind=kind) if isinstance(value, str) and value else None


# ---------------------------------------------------------------------
# early-exit: self-contained, structurally distinctive single fields
# ---------------------------------------------------------------------

class ComfyUI:
    INPUT_PREFIXES = ("text", "value", "string", "prompt")

    @classmethod
    def try_extract(cls, fields: Fields) -> Result:
        """
        Reads the API-format "prompt" graph: {"<node_id>": {"class_type": ..., "inputs": {...}}, ...}.
        """
        field = _find(fields, "prompt")
        if field is None:
            return None

        graph = field.json_data()
        if not isinstance(graph, dict):
            return None

        entries: list[PromptEntry] = []
        seen_nodes: set[str] = set()
        other_texts: list[tuple[str, str]] = []

        for node_id, node in graph.items():
            for input_name, value in cls._walk_node_inputs(node):
                if isinstance(value, list):
                    # Add text as positive/negative prompts
                    if kind := cls._try_get_kind(input_name):
                        entries.extend( cls._graph_resolve_link(graph, value, kind, seen_nodes) )

                elif cls._is_prompt(input_name, value):
                    # Remember all other texts
                    other_texts.append((node_id, value))

        # Add remembered texts if they weren't already found by _graph_resolve_link()
        entries.extend(
            PromptEntry(text=value, kind=PromptKind.TEXT)
            for node_id, value in other_texts
            if node_id not in seen_nodes
        )

        return entries


    K = TypeVar("K")
    @staticmethod
    def _try_get_kind(input_name: str, default: K = None) -> PromptKind | K:
        if "pos" in input_name:
            return PromptKind.POSITIVE
        if "neg" in input_name:
            return PromptKind.NEGATIVE

        return default

    @classmethod
    def _is_prompt(cls, input_name: str, value) -> bool:
        return isinstance(value, str) and bool(value) and input_name.startswith(cls.INPUT_PREFIXES)

    @staticmethod
    def _walk_node_inputs(node) -> Iterator[tuple[str, Any]]:
        if isinstance(node, dict):
            inputs = node.get("inputs")
            if isinstance(inputs, dict):
                yield from inputs.items()

    @classmethod
    def _graph_resolve_link(cls, graph: dict, link: list, kind: PromptKind, seen_nodes: set[str]) -> Iterator[PromptEntry]:
        node_id: str = link[0]
        stack = [(node_id, kind)]

        while stack:
            node_id, kind = stack.pop()

            # Need to check for nodes that were pushed on stack but were already reached through different path later
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)

            node = graph.get(node_id)
            for input_name, value in cls._walk_node_inputs(node):
                if isinstance(value, list):
                    target_id = value[0]
                    if target_id not in seen_nodes:
                        subkind = cls._try_get_kind(input_name, kind)
                        stack.append((target_id, subkind))

                elif cls._is_prompt(input_name, value):
                    yield PromptEntry(text=value, kind=kind)



class SwarmUI:
    @staticmethod
    def try_extract(fields: Fields) -> Result:
        """SwarmUI wraps its flat parameter dict under a distinctive "sui_image_params" key."""
        found = _find_json_dict(fields, has_all=("sui_image_params",))
        if found is None:
            return None

        data = found[1]
        entries = []

        params = data["sui_image_params"]
        if not isinstance(params, dict):
            return entries

        if e := _entry(params.get("prompt"), PromptKind.POSITIVE):
            entries.append(e)

        if e := _entry(params.get("negativeprompt") or params.get("negative_prompt"), PromptKind.NEGATIVE):
            entries.append(e)

        return entries


class InvokeAI:
    POSITIVE_KEYS = ("positive_prompt", "prompt")
    NEGATIVE_KEYS = ("negative_prompt", "negative_style_prompt")

    @classmethod
    def try_extract(cls, fields: Fields) -> Result:
        """InvokeAI's metadata schema has shifted across versions; check a few known aliases."""
        field = _find(fields, "invokeai_metadata")
        if field is None:
            return None

        data = field.json_data()
        if not isinstance(data, dict):
            return None

        entries = []

        for key in cls.POSITIVE_KEYS:
            if e := _entry(data.get(key), PromptKind.POSITIVE):
                entries.append(e)
                break

        for key in cls.NEGATIVE_KEYS:
            if e := _entry(data.get(key), PromptKind.NEGATIVE):
                entries.append(e)
                break

        return entries



# ---------------------------------------------------------------------
# fallback: needs the complete field picture, or genuinely ambiguous
# ---------------------------------------------------------------------

class NovelAI:
    @staticmethod
    def try_extract(fields: Fields) -> Result:
        """
        Legacy chunk format only (current NovelAI hides data steganographically
        in pixel LSBs instead - not handled here, would need a field extractor
        that reads raw pixel data, not text/EXIF metadata). No single field is
        reliably self-contained: some samples put both "prompt" and "uc" in
        one Comment JSON blob; others put the positive prompt in a separate
        plain "Description" field and only "uc" in Comment, with a
        "Software: NovelAI" field as the only thing tying them together - so
        this can't be an early-exit extractor.
        """
        comment = _find(fields, "comment")
        data = comment.json_data() if comment else None
        if not isinstance(data, dict) or "uc" not in data:
            return None

        software = _find(fields, "software")
        if "prompt" not in data and not (software and software.text() == "NovelAI"):
            return None  # "uc" alone isn't a distinctive enough signal on its own

        entries = []
        e = _entry(data.get("prompt"), PromptKind.POSITIVE)
        if not e:
            description = _find(fields, "description")
            e = _entry(description.text() if description else None, PromptKind.POSITIVE)
        if e:
            entries.append(e)

        if e := _entry(data.get("uc"), PromptKind.NEGATIVE):
            entries.append(e)

        return entries


class Fooocus:
    MARKER_KEYS = ("styles", "performance", "sharpness", "aspect_ratios_selection")

    @classmethod
    def try_extract(cls, fields: Fields) -> Result:
        """
        A bare "prompt" key isn't a safe enough signal by itself - Easy
        Diffusion's flat JSON has one too. Fooocus's UI concepts (style
        presets, performance/sharpness sliders, aspect-ratio selector) aren't
        shared with other tools, so require at least one of those alongside it.
        """
        found = _find_json_dict(fields, has_all=("prompt",))
        if found is None:
            return None

        field, data = found
        if field.name not in ("comment", "fooocus", "parameters"):
            return None

        if not any(k in data for k in cls.MARKER_KEYS):
            return None

        entries = []
        if e := _entry(data.get("prompt"), PromptKind.POSITIVE):
            entries.append(e)

        if e := _entry(data.get("negative_prompt"), PromptKind.NEGATIVE):
            entries.append(e)

        return entries


class EasyDiffusion:
    @staticmethod
    def try_extract(fields: Fields) -> Result:
        """
        Easy Diffusion has shown up in two shapes: a single flat JSON blob
        (PNG "parameters" / JPEG "usercomment"), and separate plain-text
        "prompt"/"negative_prompt" chunks (PNG). On at least one JPEG sample
        both a JSON blob AND separate plain fields were present simultaneously
        (the same data written twice) - the JSON blob is treated as canonical
        whenever one is present, so the redundant plain fields are never
        looked at, instead of extracting both and duplicating the output.

        NOTE: exactly which EXIF/XMP mechanism produces that JPEG duplicate
        wasn't confirmed against the real sample file - this is a defensive-
        by-construction fix (prefer the richer/JSON source, ignore likely
        echoes) rather than one targeted at a specific field name. Worth
        re-checking against the actual sample if duplicates still show up.
        """
        # TODO: Rely on try_decompose instead of parsing the json here
        found = _find_json_dict(fields, has_all=("negative_prompt",))
        if found is not None:
            data = found[1]
            if "sui_image_params" in data or any(k in data for k in Fooocus.MARKER_KEYS):
                return None  # SwarmUI/Fooocus already own this shape

            entries = []
            if e := _entry(data.get("prompt"), PromptKind.POSITIVE):
                entries.append(e)

            if e := _entry(data.get("negative_prompt"), PromptKind.NEGATIVE):
                entries.append(e)

            return entries

        # No JSON blob anywhere - fall back to separate plain-text chunks.
        prompt_field = _find(fields, "prompt")
        negative_field = _find(fields, "negative_prompt")
        if prompt_field is None and negative_field is None:
            return None

        if ((prompt_field and prompt_field.json_data() is not None) or (negative_field and negative_field.json_data() is not None)):
            return None  # JSON-shaped - belongs to some other tool, not this plain-text path

        entries = []

        if e := _entry(prompt_field.text() if prompt_field else None, PromptKind.POSITIVE):
            entries.append(e)

        if e := _entry(negative_field.text() if negative_field else None, PromptKind.NEGATIVE):
            entries.append(e)

        return entries if entries else None


class A1111:
    NEGATIVE_MARKER = "\nNegative prompt:"
    PATTERN_SETTINGS_LINE = re.compile(r"\n(?=Steps:\s*\d)")
    PATTERN_PARAMS = re.compile(r"^\s*parameters\s*\n", flags=re.IGNORECASE)

    @classmethod
    def try_extract(cls, fields: Fields) -> Result:
        """
        Covers A1111, Forge, reForge, and SD.Next (a direct A1111 fork).
        All write the identical plain-text "parameters" format, not JSON.
        """
        field = _find(fields, "parameters") or _find(fields, "usercomment")
        if field is None or field.json_data() is not None:
            return None

        text = field.text()
        if not text or (cls.NEGATIVE_MARKER not in text and not cls.PATTERN_SETTINGS_LINE.search(text)):
            return None

        text = cls.PATTERN_PARAMS.sub("", text, count=1)
        negative_idx = text.find(cls.NEGATIVE_MARKER)
        if negative_idx != -1:
            positive = text[:negative_idx].strip()
            rest = text[negative_idx + len(cls.NEGATIVE_MARKER):]
        else:
            positive, rest = None, text

        settings_match = cls.PATTERN_SETTINGS_LINE.search(rest)
        negative = (rest[:settings_match.start()] if settings_match else rest).strip()
        if negative_idx == -1:
            # No "Negative prompt:" marker - what we split off as "negative"
            # is actually the positive prompt with the settings tail stripped.
            positive, negative = negative, None

        entries = []

        if e := _entry(positive, PromptKind.POSITIVE):
            entries.append(e)

        if e := _entry(negative, PromptKind.NEGATIVE):
            entries.append(e)

        return entries


class Midjourney:
    MAX_LEN = 4000  # guards against accidentally claiming a large unrelated text blob

    @classmethod
    def try_extract(cls, fields: Fields) -> Result:
        """
        Embeds the full prompt (often with trailing --params) as plain text
        directly in EXIF ImageDescription/Title - no JSON, no positive/negative split.
        Runs last: only claims a field once nothing JSON-shaped, A1111-shaped, or NovelAI's multi-field signature matched it.
        """
        for name in ("imagedescription", "title", "description"):
            field = _find(fields, name)
            if field is None or field.json_data() is not None:
                continue

            text = field.text()
            if text and 0 < len(text) <= cls.MAX_LEN:
                return [PromptEntry(text=text.strip(), kind=PromptKind.TEXT)]

        return None



EARLY_EXIT_EXTRACTORS = (
    ComfyUI,
    SwarmUI,
    InvokeAI,
)

FALLBACK_EXTRACTORS = (
    NovelAI,
    Fooocus,
    EasyDiffusion,
    A1111,
    Midjourney,
)
