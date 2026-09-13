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

from typing import TYPE_CHECKING

from mtgcoach.carddata.cards import Card, CardFace
from mtgcoach.carddata.facecolors import colors_in
from mtgcoach.carddata.jsondata import (
    JsonObject,
    MalformedJsonError,
    nullable_str,
    object_list,
    optional_str,
    require_float,
    require_str,
    string_set,
)
from mtgcoach.carddata.jsonstream import stream_objects
from mtgcoach.carddata.paths import validate_set_code
from mtgcoach.core.ids import OracleId, SetCode

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: Re-exported so callers catch one error type from this module.
MalformedCardError = MalformedJsonError


def _face_from(obj: JsonObject, fallback_name: str) -> CardFace:
    """Build a face from either a ``card_faces`` entry or a whole card object.

    Adventure faces carry no ``colors`` field at all, and the card's top-level
    one is empty, so reading it directly made both halves of every adventure
    card colourless -- including the black half of a ``{1}{B}`` adventure. An
    absent field means undeclared, and CR 105.2 says the mana cost decides.
    """
    mana_cost = optional_str(obj, "mana_cost")
    declared = string_set(obj, "colors")
    return CardFace(
        name=optional_str(obj, "name", fallback_name),
        mana_cost=mana_cost,
        type_line=optional_str(obj, "type_line"),
        oracle_text=optional_str(obj, "oracle_text"),
        power=nullable_str(obj, "power"),
        toughness=nullable_str(obj, "toughness"),
        colors=declared if "colors" in obj else colors_in(mana_cost),
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


def cards_in(path: Path) -> Iterator[Card]:
    """Read every card in a file, whatever shape the file takes."""
    return (card_from_json(obj) for obj in stream_objects(path))


def printing_from_json(obj: JsonObject) -> tuple[Card, SetCode]:
    """Build a card and the set code of the printing it was read from.

    The set is taken from the document, never from a caller-supplied flag: a
    bulk file spans every set, and tagging its contents with whatever set the
    user asked for would quietly mislabel every card in it. It is validated
    like any other set code, so a malformed one cannot reach the database.
    """
    card = card_from_json(obj)
    code = SetCode(require_str(obj, "set", card.name).upper())
    try:
        validate_set_code(code)
    except ValueError as exc:
        msg = f"{card.name}: {exc}"
        raise MalformedJsonError(msg) from exc
    return card, code


def read_printings(
    path: Path,
    on_error: Callable[[MalformedJsonError], None] | None = None,
) -> Iterator[tuple[Card, SetCode]]:
    """Read every printing in a file.

    By default a malformed card stops the read, because silently dropping rules
    data is how a coach ends up confidently wrong. A caller that would rather
    import what it can -- a several-hundred-megabyte bulk file should not be
    abandoned over one odd card in a set you do not own -- passes ``on_error``
    and decides what to report.
    """
    for obj in stream_objects(path):
        try:
            yield printing_from_json(obj)
        except MalformedJsonError as exc:
            if on_error is None:
                raise
            on_error(exc)
