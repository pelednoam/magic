"""Every SQL statement the store runs.

Gathered here so the query surface can be read at a glance, and so the one
reason any of it is assembled with an f-string is stated once rather than at
each site: the only interpolated values are the column-name constants from
``rowmap``, which exist so that a column added to a query and forgotten in its
mapper cannot silently shift every field by one position.

No caller value is ever interpolated. Set and id lists arrive as a single JSON
array expanded by ``json_each``; everything else is a bound parameter. That is
what the S608 suppressions mean here -- not a shrug.
"""

from __future__ import annotations

from mtgcoach.carddata.rowmap import CARD_COLUMNS, FACE_COLUMNS

SELECT_CARD = f"SELECT {CARD_COLUMNS} FROM cards"  # noqa: S608
SELECT_FACES = f"SELECT {FACE_COLUMNS} FROM faces WHERE oracle_id = ? ORDER BY ordinal"  # noqa: S608
SELECT_FACES_FOR = (
    f"SELECT oracle_id, {FACE_COLUMNS} FROM faces "  # noqa: S608
    "WHERE oracle_id IN (SELECT value FROM json_each(?)) "
    "ORDER BY oracle_id, ordinal"
)
SELECT_BY_ORACLE_ID = f"{SELECT_CARD} WHERE oracle_id = ?"
SELECT_BY_NAME = f"{SELECT_CARD} WHERE name = ?"
SELECT_IN_SET = (
    f"{SELECT_CARD} WHERE oracle_id IN ("  # noqa: S608
    "  SELECT oracle_id FROM printings WHERE set_code = ?"
    ") ORDER BY name"
)
SELECT_IN_COLLECTION = (
    f"{SELECT_CARD} WHERE oracle_id IN ("  # noqa: S608
    "  SELECT oracle_id FROM printings "
    "  WHERE set_code IN (SELECT value FROM json_each(?))"
    ") OR oracle_id IN (SELECT value FROM json_each(?)) ORDER BY name"
)

SELECT_NAMES_IN_SET = (
    "SELECT c.name FROM cards c JOIN printings p USING (oracle_id) WHERE p.set_code = ?"
)
SELECT_SET_CODES = "SELECT DISTINCT set_code FROM printings ORDER BY set_code"
COUNT_IN_SET = "SELECT COUNT(*) FROM printings WHERE set_code = ?"
SELECT_OWNED_SETS = "SELECT set_code FROM owned_sets ORDER BY set_code"
SELECT_OWNED_CARDS = "SELECT oracle_id FROM owned_cards ORDER BY oracle_id"
INSERT_PRINTING = "INSERT OR IGNORE INTO printings (oracle_id, set_code) VALUES (?, ?)"
INSERT_OWNED_SET = "INSERT OR IGNORE INTO owned_sets (set_code) VALUES (?)"
INSERT_OWNED_CARD = "INSERT OR IGNORE INTO owned_cards (oracle_id) VALUES (?)"
DELETE_OWNED_SET = "DELETE FROM owned_sets WHERE set_code = ?"
