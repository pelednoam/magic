"""Reading the field names off both sides of the wire.

Kept apart from the test so that what the test reads is a turn being played and
two sets being compared, rather than a regular expression and a tree walk.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The app's hand-written wire types. A folder, not a file: they were split in
#: two when the file-length gate learned to look at TypeScript, and a check
#: that read only one half would have gone quietly half-blind.
WIRE = Path(__file__).resolve().parents[2] / "apps" / "mobile" / "src" / "wire"

#: Keys that are data rather than fields: the server maps player ids to their
#: state, and those ids are values the app reads at runtime, not names it can
#: declare. Everything else in the payload is a field with a type.
DYNAMIC_KEYS = frozenset({"you", "them"})

#: Any field in a TypeScript interface, `readonly` or not. Matching only
#: `readonly` ones let a field added without the modifier escape the check in
#: both directions -- and the check exists precisely for the fields nobody
#: thought about carefully.
FIELD = re.compile(r"^\s*(?:readonly\s+)?(\w+)\??:\s", re.MULTILINE)


def keys(value: object) -> Iterator[str]:
    """Every field name anywhere in a payload."""
    if isinstance(value, dict):
        for key, nested in cast("dict[object, object]", value).items():
            assert isinstance(key, str)
            yield key
            yield from keys(nested)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            yield from keys(item)


def declared() -> frozenset[str]:
    """Every field the app's types declare, across the whole wire folder."""
    found: set[str] = set()
    for path in sorted(WIRE.glob("*.ts")):
        found.update(FIELD.findall(path.read_text(encoding="utf-8")))
    return frozenset(found)


def wire_files() -> list[str]:
    """The names of the wire modules, so a rename cannot silently empty this."""
    return sorted(path.name for path in WIRE.glob("*.ts"))
