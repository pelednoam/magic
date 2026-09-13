"""The card database: schema, and reading rows back without ``Any``.

Two tables rather than one, because they answer different questions. ``cards``
holds oracle behaviour, keyed by ``oracle_id``; ``printings`` records which sets
a card appeared in. That split is what lets ``Card`` stay set-free -- two
printings behave identically and the engine must not distinguish them -- while
still allowing "which cards does this collection contain" to be answered.

``sqlite3`` hands back rows typed ``Any``. As with the JSON boundary, the cast is
made once, in one checked place, rather than spreading through every query.
"""

from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

SCHEMA: Final = """
CREATE TABLE IF NOT EXISTS cards (
    oracle_id      TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    cmc            REAL NOT NULL,
    layout         TEXT NOT NULL,
    keywords       TEXT NOT NULL,
    color_identity TEXT NOT NULL,
    produced_mana  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS faces (
    oracle_id   TEXT NOT NULL REFERENCES cards(oracle_id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    mana_cost   TEXT NOT NULL,
    type_line   TEXT NOT NULL,
    oracle_text TEXT NOT NULL,
    power       TEXT,
    toughness   TEXT,
    colors      TEXT NOT NULL,
    PRIMARY KEY (oracle_id, ordinal)
);

CREATE TABLE IF NOT EXISTS printings (
    oracle_id TEXT NOT NULL REFERENCES cards(oracle_id) ON DELETE CASCADE,
    set_code  TEXT NOT NULL,
    PRIMARY KEY (oracle_id, set_code)
);

CREATE TABLE IF NOT EXISTS owned_sets (
    set_code TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS owned_cards (
    oracle_id TEXT PRIMARY KEY
);

CREATE INDEX IF NOT EXISTS printings_by_set ON printings(set_code);
CREATE INDEX IF NOT EXISTS cards_by_name ON cards(name);
"""


def connect(path: str) -> sqlite3.Connection:
    """Open a database and make sure the schema is present."""
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def rows(
    connection: sqlite3.Connection, sql: str, params: Sequence[object] = ()
) -> list[tuple[object, ...]]:
    """Run a query and return its rows as plain objects.

    The one place ``sqlite3``'s ``Any`` is confined. Callers narrow each column
    explicitly through the helpers below, so a schema change that alters a column
    type surfaces as a clear error instead of an attribute error much later.
    """
    cursor = connection.execute(sql, tuple(params))
    return cast("list[tuple[object, ...]]", cursor.fetchall())


class SchemaError(RuntimeError):
    """A stored row does not have the type the schema promises."""


def as_text(value: object, column: str) -> str:
    """Read a NOT NULL text column."""
    if not isinstance(value, str):
        msg = f"column {column!r} should be text, got {type(value).__name__}"
        raise SchemaError(msg)
    return value


def as_optional_text(value: object) -> str | None:
    """Read a nullable text column."""
    return value if isinstance(value, str) else None


def as_real(value: object, column: str) -> float:
    """Read a NOT NULL numeric column."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        msg = f"column {column!r} should be numeric, got {type(value).__name__}"
        raise SchemaError(msg)
    return float(value)


def as_string_set(value: object, column: str) -> frozenset[str]:
    """Read a column holding a JSON array of strings."""
    try:
        decoded: object = json.loads(as_text(value, column))
    except json.JSONDecodeError as exc:
        msg = f"column {column!r} does not hold valid JSON"
        raise SchemaError(msg) from exc
    if not isinstance(decoded, list):
        msg = f"column {column!r} should hold a JSON array"
        raise SchemaError(msg)
    items = cast("list[object]", decoded)
    return frozenset(item for item in items if isinstance(item, str))


def dump_strings(values: frozenset[str]) -> str:
    """Serialise a set of strings for storage, sorted so rows are stable."""
    return json.dumps(sorted(values))
