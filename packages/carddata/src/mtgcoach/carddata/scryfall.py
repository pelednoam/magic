"""Turning Scryfall JSON into ``Card`` objects.

Scryfall's card object is not uniform, and the differences are not cosmetic:

- A ``transform`` card has **no** top-level ``mana_cost`` or ``oracle_text``.
  Both live on the faces. Reading the top level gets ``None``.
- An ``adventure`` card *does* have a top-level ``mana_cost``, but it is the
  combined string ``{3} // {1}{B}`` -- worse than missing, because it parses.
- ``cmc`` is top-level only; faces do not carry their own.
- ``power`` is a string. ``*`` is a real value, as is ``1+*``.

So faces are the unit, and a single-faced card gets a one-element tuple built
from the top level. Anything Scryfall adds later is ignored rather than
rejected: a card we can partly understand is more useful than an import that
fails on an unfamiliar key.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mtgcoach.carddata.cards import Card, CardFace
from mtgcoach.carddata.jsondata import (
    JsonObject,
    MalformedJsonError,
    as_array,
    as_object,
    nullable_str,
    object_list,
    optional_str,
    require_float,
    require_str,
    string_set,
)
from mtgcoach.core.ids import OracleId, SetCode

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: Re-exported so callers catch one error type from this module.
MalformedCardError = MalformedJsonError


def _face_from(obj: JsonObject, fallback_name: str) -> CardFace:
    """Build a face from either a ``card_faces`` entry or a whole card object."""
    return CardFace(
        name=optional_str(obj, "name", fallback_name),
        mana_cost=optional_str(obj, "mana_cost"),
        type_line=optional_str(obj, "type_line"),
        oracle_text=optional_str(obj, "oracle_text"),
        power=nullable_str(obj, "power"),
        toughness=nullable_str(obj, "toughness"),
        colors=string_set(obj, "colors"),
    )


def card_from_json(obj: JsonObject) -> Card:
    """Build a ``Card`` from one Scryfall card object.

    Raises:
        MalformedJsonError: If ``name``, ``oracle_id`` or ``cmc`` is missing or
            has the wrong type.
    """
    name = require_str(obj, "name", "card")
    faces_json = object_list(obj, "card_faces")
    faces = (
        tuple(_face_from(face, name) for face in faces_json)
        if faces_json
        else (_face_from(obj, name),)
    )
    return Card(
        oracle_id=OracleId(require_str(obj, "oracle_id", name)),
        name=name,
        cmc=require_float(obj, "cmc", name),
        layout=optional_str(obj, "layout", "normal"),
        keywords=string_set(obj, "keywords"),
        color_identity=string_set(obj, "color_identity"),
        produced_mana=string_set(obj, "produced_mana"),
        faces=faces,
    )


def _objects(raw: object) -> Iterator[JsonObject]:
    items = as_array(raw)
    if items is None:
        return
    for item in items:
        obj = as_object(item)
        if obj is not None:
            yield obj


def cards_from_json_array(path: Path) -> Iterator[Card]:
    """Read a JSON array of Scryfall card objects."""
    with path.open(encoding="utf-8") as handle:
        raw: object = json.load(handle)
        yield from (card_from_json(obj) for obj in _objects(raw))


def cards_from_jsonl(path: Path) -> Iterator[Card]:
    """Read Scryfall's bulk format: one card object per line.

    Streamed rather than loaded. The ``default-cards`` bulk file is hundreds of
    megabytes, and holding it in memory to import a few hundred cards from one
    set is the difference between this running on a laptop and not.
    """
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip().rstrip(",")
            if not stripped or stripped in {"[", "]"}:
                continue
            parsed: object = json.loads(stripped)
            obj = as_object(parsed)
            if obj is not None:
                yield card_from_json(obj)


def printing_from_json(obj: JsonObject) -> tuple[Card, SetCode]:
    """Build a card and the set code of the printing it was read from.

    The set is taken from the document, never from a caller-supplied flag: a
    bulk file spans every set, and tagging its contents with whatever set the
    user asked for would quietly mislabel every card in it.
    """
    card = card_from_json(obj)
    return card, SetCode(require_str(obj, "set", card.name).upper())


def printings_from_json_array(path: Path) -> Iterator[tuple[Card, SetCode]]:
    """Read a JSON array, yielding each card with its set code."""
    with path.open(encoding="utf-8") as handle:
        raw: object = json.load(handle)
        yield from (printing_from_json(obj) for obj in _objects(raw))


def printings_from_jsonl(path: Path) -> Iterator[tuple[Card, SetCode]]:
    """Read Scryfall's bulk format, yielding each card with its set code."""
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip().rstrip(",")
            if not stripped or stripped in {"[", "]"}:
                continue
            parsed: object = json.loads(stripped)
            obj = as_object(parsed)
            if obj is not None:
                yield printing_from_json(obj)


def read_printings(path: Path) -> Iterator[tuple[Card, SetCode]]:
    """Read either shape, choosing by the file's first non-blank character.

    Scryfall's own bulk downloads are JSON arrays; exports and hand-made slices
    are often one object per line. Sniffing beats asking the user which it is.
    """
    with path.open(encoding="utf-8") as handle:
        first = handle.read(1)
        while first and first.isspace():
            first = handle.read(1)
    if first == "[":
        yield from printings_from_json_array(path)
    else:
        yield from printings_from_jsonl(path)
