"""When the installed Comprehensive Rules took effect.

The document says so on its third line:

    Magic: The Gathering Comprehensive Rules

    These rules are effective as of August 7, 2026.

That sentence is the revision. Wizards publish a new document with every set
and the URL carries a date, but the URL is not in the file and an operator who
renamed the download has lost it -- so the date is read out of the text, which
travels with the copy actually being quoted.

``docs/DECISIONS.md`` items 5 and 8 both ask for this. Item 5 wants a game
pinned to the versions it was played under; item 8 wants each rules scenario to
record the document version it was derived from. Both are the same sentence.

**Why it is not parsed into a date.** It is carried as the document's own
words. A ``date`` would need a format, a locale and a decision about what to do
with a line that does not match -- and every use of this is comparison or
display, neither of which is helped by having thrown the original away.
"""

from __future__ import annotations

import re
from typing import Final

#: How much of the line can be a date. A bound, because whatever is captured
#: rides every board on the wire, every recorded game and the retrieval
#: check's output: a line far longer than a date is not a date, and is better
#: recorded as ``UNKNOWN`` than carried around as one.
LONGEST: Final = 64

#: The sentence, as the document writes it. Anchored to the line so that a
#: rule *quoting* the phrase later in the document cannot be mistaken for it,
#: and tolerant of the exact date format, which is Wizards' to change.
#:
#: ``[^\n]`` and ``[ \t]*`` rather than ``.`` and ``\s*``: under
#: ``MULTILINE`` both of the latter can reach past the end of the line -- and
#: the lazy capture with ``\s*$`` behind it is the shape that backtracks
#: quadratically on a long line of whitespace.
_EFFECTIVE: Final = re.compile(
    rf"^These rules are effective as of (?P<when>[^\n]{{1,{LONGEST}}}?)\.?[ \t]*$",
    re.MULTILINE,
)

#: What a document with no such line is recorded as. Empty rather than a guess:
#: "we do not know which revision this was" is a fact worth keeping, and a
#: plausible-looking date nobody read off the file is not.
UNKNOWN: Final = ""


def effective_from(text: str) -> str:
    """The date the document says it takes effect, or ``UNKNOWN``.

    The first match only. The phrase appears once in the real document; taking
    the first keeps a fixture that happens to quote it in an excerpt from
    turning one document into two answers.
    """
    found = _EFFECTIVE.search(text)
    return found.group("when").strip() if found is not None else UNKNOWN
