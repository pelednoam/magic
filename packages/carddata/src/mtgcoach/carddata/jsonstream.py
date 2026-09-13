"""Reading a large JSON file one object at a time.

Scryfall's ``default-cards`` bulk file is a JSON *array* of several hundred
megabytes. ``json.load`` on that needs the whole document in memory before the
first card is available, which is the difference between this running on a
laptop and not -- and an earlier version of this module claimed to stream while
doing exactly that.

Rather than sniff the file's shape and route to one of two readers, this scans
for balanced top-level objects. That handles every form the same way: a
pretty-printed array, one object per line, a bare object, a byte-order mark, and
whatever whitespace or trailing commas surround them. Anything that is not a
top-level object -- the enclosing brackets, separating commas, stray scalars --
is simply not an object and is skipped.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.carddata.jsondata import require_object

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import TextIO

    from mtgcoach.carddata.jsondata import JsonObject

#: Read size. Large enough that the syscall cost disappears against the parse.
CHUNK = 1 << 16


@dataclass(slots=True)
class _Scanner:
    """Tracks brace depth while respecting strings.

    Brace counting has to know about strings, because card text is full of
    braces -- every mana symbol is one, and a ``{1}{B}`` inside an oracle_text
    field would otherwise close the object early.
    """

    depth: int = 0
    in_string: bool = False
    escaped: bool = False
    buffer: list[str] = field(default_factory=list[str])

    def feed(self, char: str) -> str | None:
        """Consume one character, returning a complete object's text if it ends here."""
        if self.depth:
            self.buffer.append(char)
        if self.in_string:
            self._advance_string(char)
            return None
        return self._advance_structure(char)

    def _advance_string(self, char: str) -> None:
        if self.escaped:
            self.escaped = False
        elif char == "\\":
            self.escaped = True
        elif char == '"':
            self.in_string = False

    def _advance_structure(self, char: str) -> str | None:
        if char == '"':
            self.in_string = True
        elif char == "{":
            self._open()
        elif char == "}":
            return self._close()
        return None

    def _open(self) -> None:
        if not self.depth:
            self.buffer = ["{"]
        self.depth += 1

    def _close(self) -> str | None:
        self.depth -= 1
        if self.depth:
            return None
        text = "".join(self.buffer)
        self.buffer = []
        return text


def _object_texts(handle: TextIO) -> Iterator[str]:
    """Yield the source text of each balanced top-level ``{...}``."""
    scanner = _Scanner()
    while chunk := handle.read(CHUNK):
        for char in chunk:
            text = scanner.feed(char)
            if text is not None:
                yield text


def stream_objects(path: Path) -> Iterator[JsonObject]:
    """Yield every top-level JSON object in ``path``, in order.

    Opened as ``utf-8-sig`` so a byte-order mark is consumed rather than
    becoming a parse error on the first object.
    """
    with path.open(encoding="utf-8-sig") as handle:
        for text in _object_texts(handle):
            # The scanner only ever emits balanced ``{...}``, so this always
            # narrows -- but saying so through the same checked helper as
            # everywhere else beats an unchecked cast, and leaves no branch here
            # that no input can reach.
            yield require_object(json.loads(text), path.name)
