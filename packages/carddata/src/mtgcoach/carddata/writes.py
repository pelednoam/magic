"""Inserting cards and faces.

Split from the store so that the query surface and the write surface can each
be read on their own, and so both stay within the module size limit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata.schema import dump_strings

if TYPE_CHECKING:
    import sqlite3

    from mtgcoach.carddata.cards import Card

# An upsert, emphatically not INSERT OR REPLACE. REPLACE deletes the existing
# row before inserting, and with foreign keys on that delete cascades into
# `printings` -- so re-importing a card from one set silently erased every other
# set it had been printed in. ON CONFLICT ... DO UPDATE edits the row in place
# and leaves its printings alone.
_INSERT_CARD = (
    "INSERT INTO cards "
    "(oracle_id, name, cmc, layout, keywords, color_identity, produced_mana) "
    "VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(oracle_id) DO UPDATE SET "
    "name = excluded.name, cmc = excluded.cmc, layout = excluded.layout, "
    "keywords = excluded.keywords, color_identity = excluded.color_identity, "
    "produced_mana = excluded.produced_mana"
)

_INSERT_FACE = (
    "INSERT INTO faces "
    "(oracle_id, ordinal, name, mana_cost, type_line, oracle_text, power, "
    "toughness, colors) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def insert_card(connection: sqlite3.Connection, card: Card) -> None:
    """Write the oracle-level row for a card, updating any existing one."""
    connection.execute(
        _INSERT_CARD,
        (
            card.oracle_id,
            card.name,
            card.cmc,
            card.layout,
            dump_strings(card.keywords),
            dump_strings(card.color_identity),
            dump_strings(card.produced_mana),
        ),
    )


def insert_faces(connection: sqlite3.Connection, card: Card) -> None:
    """Replace a card's faces.

    Deleted first rather than upserted: a card that gains or loses a face in an
    oracle update would otherwise keep a stale row at the old ordinal, and a
    phantom back face is the kind of error that surfaces only when someone
    scans that card months later.
    """
    connection.execute("DELETE FROM faces WHERE oracle_id = ?", (card.oracle_id,))
    for ordinal, face in enumerate(card.faces):
        connection.execute(
            _INSERT_FACE,
            (
                card.oracle_id,
                ordinal,
                face.name,
                face.mana_cost,
                face.type_line,
                face.oracle_text,
                face.power,
                face.toughness,
                dump_strings(face.colors),
            ),
        )
