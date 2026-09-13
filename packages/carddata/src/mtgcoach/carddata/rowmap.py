"""Turning database rows into cards.

Split from the store so that queries and row mapping can each be read on their
own, and so the store stays under the module size limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata.cards import Card, CardFace
from mtgcoach.carddata.schema import (
    as_optional_text,
    as_real,
    as_string_set,
    as_text,
)
from mtgcoach.core.ids import OracleId

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: Column order shared by the queries and the mappers below. Kept as constants
#: so a column added to one and forgotten in the other cannot silently shift
#: every field by one position.
CARD_COLUMNS = "oracle_id, name, cmc, layout, keywords, color_identity, produced_mana"
FACE_COLUMNS = "name, mana_cost, type_line, oracle_text, power, toughness, colors"


def face_from_row(row: tuple[object, ...]) -> CardFace:
    """Build a face from a row selected with ``FACE_COLUMNS``."""
    return CardFace(
        name=as_text(row[0], "name"),
        mana_cost=as_text(row[1], "mana_cost"),
        type_line=as_text(row[2], "type_line"),
        oracle_text=as_text(row[3], "oracle_text"),
        power=as_optional_text(row[4]),
        toughness=as_optional_text(row[5]),
        colors=as_string_set(row[6], "colors"),
    )


def card_from_row(row: tuple[object, ...], faces: Iterable[tuple[object, ...]]) -> Card:
    """Build a card from a row selected with ``CARD_COLUMNS`` and its faces."""
    return Card(
        oracle_id=OracleId(as_text(row[0], "oracle_id")),
        name=as_text(row[1], "name"),
        cmc=as_real(row[2], "cmc"),
        layout=as_text(row[3], "layout"),
        keywords=as_string_set(row[4], "keywords"),
        color_identity=as_string_set(row[5], "color_identity"),
        produced_mana=as_string_set(row[6], "produced_mana"),
        faces=tuple(face_from_row(face) for face in faces),
    )


def cards_from_rows(
    card_rows: Sequence[tuple[object, ...]],
    face_rows: Iterable[tuple[object, ...]],
) -> tuple[Card, ...]:
    """Build many cards from one card query and one face query.

    ``face_rows`` must start with ``oracle_id`` and be selected with
    ``FACE_COLUMNS`` after it; grouping here is what lets the store read a whole
    set with two queries instead of one per card.
    """
    grouped: dict[str, list[tuple[object, ...]]] = {}
    for face in face_rows:
        grouped.setdefault(as_text(face[0], "oracle_id"), []).append(face[1:])
    return tuple(
        card_from_row(row, grouped.get(as_text(row[0], "oracle_id"), [])) for row in card_rows
    )
