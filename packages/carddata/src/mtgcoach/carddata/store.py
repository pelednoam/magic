"""Reading and writing cards.

The store is the only component that knows which set a card was printed in, so
it is the only one that can scope a ``Collection``. Everything above it works on
oracle cards, which is what stops a reprint becoming a different card.

Every query is fully parameterised. Set lists are passed as a single JSON array
and expanded with ``json_each`` rather than by building a row of ``?`` markers,
so no SQL is assembled from Python values anywhere in this module.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self

from mtgcoach.carddata.collection import Collection
from mtgcoach.carddata.rowmap import CARD_COLUMNS, FACE_COLUMNS, card_from_row
from mtgcoach.carddata.schema import as_real, as_text, connect, rows
from mtgcoach.carddata.writes import insert_card, insert_faces
from mtgcoach.core.ids import OracleId, SetCode

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterable
    from types import TracebackType

    from mtgcoach.carddata.cards import Card

# Every query is a constant here. The only interpolated values are the column-name
# constants from rowmap, which exist so a column added to a query and forgotten in
# its mapper cannot silently shift every field by one position. No caller value is
# ever interpolated -- set lists arrive as a single JSON array expanded by
# json_each, everything else is a bound parameter. That is what the S608
# suppressions mean here; they are not a shrug.
_SELECT_CARD = f"SELECT {CARD_COLUMNS} FROM cards"  # noqa: S608
_SELECT_FACES = f"SELECT {FACE_COLUMNS} FROM faces WHERE oracle_id = ? ORDER BY ordinal"  # noqa: S608
_SELECT_BY_ORACLE_ID = f"{_SELECT_CARD} WHERE oracle_id = ?"
_SELECT_BY_NAME = f"{_SELECT_CARD} WHERE name = ?"
_SELECT_IN_SET = (
    f"{_SELECT_CARD} WHERE oracle_id IN ("  # noqa: S608
    "  SELECT oracle_id FROM printings WHERE set_code = ?"
    ") ORDER BY name"
)
_SELECT_IN_COLLECTION = (
    f"{_SELECT_CARD} WHERE oracle_id IN ("  # noqa: S608
    "  SELECT oracle_id FROM printings "
    "  WHERE set_code IN (SELECT value FROM json_each(?))"
    ") OR oracle_id IN (SELECT value FROM json_each(?)) ORDER BY name"
)


class CardStore:
    """A SQLite-backed card database."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Wrap an open connection. Prefer ``CardStore.open``."""
        self._connection = connection

    @classmethod
    def open(cls, path: str = ":memory:") -> Self:
        """Open (or create) a store, in memory by default."""
        return cls(connect(path))

    def __enter__(self) -> Self:
        """Enter a context manager that closes the store on exit."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit and close on leaving the context."""
        self.close()

    def close(self) -> None:
        """Commit and close the connection."""
        self._connection.commit()
        self._connection.close()

    def add(self, cards: Iterable[tuple[Card, SetCode]]) -> int:
        """Insert or replace cards, recording the set each was seen in.

        Idempotent, which matters because the bulk file is refreshed daily and
        re-importing is the normal way to pick up an oracle text change.
        """
        written = 0
        with self._connection:
            for card, set_code in cards:
                insert_card(self._connection, card)
                insert_faces(self._connection, card)
                self._connection.execute(
                    "INSERT OR IGNORE INTO printings (oracle_id, set_code) VALUES (?, ?)",
                    (card.oracle_id, set_code),
                )
                written += 1
        return written

    def _hydrate(self, row: tuple[object, ...]) -> Card:
        oracle_id = as_text(row[0], "oracle_id")
        return card_from_row(row, rows(self._connection, _SELECT_FACES, (oracle_id,)))

    def get(self, oracle_id: OracleId) -> Card | None:
        """Return one card by oracle id, or None."""
        found = rows(self._connection, f"{_SELECT_CARD} WHERE oracle_id = ?", (oracle_id,))
        return self._hydrate(found[0]) if found else None

    def by_name(self, name: str) -> Card | None:
        """Return one card by exact name, or None."""
        found = rows(self._connection, _SELECT_BY_NAME, (name,))
        return self._hydrate(found[0]) if found else None

    def names_in(self, set_code: SetCode) -> frozenset[str]:
        """Every card name printed in one set.

        The membership oracle that deck verification checks against, so a list
        naming a card that does not exist cannot pass.
        """
        found = rows(
            self._connection,
            "SELECT c.name FROM cards c JOIN printings p USING (oracle_id) WHERE p.set_code = ?",
            (set_code,),
        )
        return frozenset(as_text(row[0], "name") for row in found)

    def cards_in(self, collection: Collection) -> tuple[Card, ...]:
        """Every card the collection contains, ordered by name."""
        found = rows(
            self._connection,
            _SELECT_IN_COLLECTION,
            (
                json.dumps(sorted(collection.sets)),
                json.dumps(sorted(collection.extra_cards)),
            ),
        )
        return tuple(self._hydrate(row) for row in found)

    def cards_in_set(self, set_code: SetCode) -> tuple[Card, ...]:
        """Every card printed in one set, ordered by name.

        Distinct from ``cards_in``: auditing a set asks about the set itself,
        which is a question you want answered *before* deciding to own it.
        """
        found = rows(self._connection, _SELECT_IN_SET, (set_code,))
        return tuple(self._hydrate(row) for row in found)

    def set_codes(self) -> tuple[SetCode, ...]:
        """Every set with at least one stored card."""
        found = rows(self._connection, "SELECT DISTINCT set_code FROM printings ORDER BY set_code")
        return tuple(SetCode(as_text(row[0], "set_code")) for row in found)

    def count_in(self, set_code: SetCode) -> int:
        """How many cards are stored for one set."""
        found = rows(
            self._connection,
            "SELECT COUNT(*) FROM printings WHERE set_code = ?",
            (set_code,),
        )
        return int(as_real(found[0][0], "count"))

    # -- the collection -----------------------------------------------------

    def collection(self) -> Collection:
        """The sets and singles currently marked as owned."""
        sets = rows(self._connection, "SELECT set_code FROM owned_sets ORDER BY set_code")
        cards = rows(self._connection, "SELECT oracle_id FROM owned_cards ORDER BY oracle_id")
        return Collection(
            sets=frozenset(SetCode(as_text(r[0], "set_code")) for r in sets),
            extra_cards=frozenset(OracleId(as_text(r[0], "oracle_id")) for r in cards),
        )

    def enable_set(self, set_code: SetCode) -> None:
        """Mark a set as owned. Idempotent."""
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO owned_sets (set_code) VALUES (?)", (set_code,)
            )

    def enable_card(self, oracle_id: OracleId) -> None:
        """Mark one single as owned, outside any set. Idempotent.

        There is deliberately no ``disable_card`` yet: nothing removes a single,
        and an unused method is one more thing to keep correct. It arrives with
        the screen that needs it.
        """
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO owned_cards (oracle_id) VALUES (?)", (oracle_id,)
            )

    def disable_set(self, set_code: SetCode) -> None:
        """Mark a set as not owned. Idempotent, and never deletes card data."""
        with self._connection:
            self._connection.execute("DELETE FROM owned_sets WHERE set_code = ?", (set_code,))
