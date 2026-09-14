"""Reading a citation as the rule it names.

A model shown ``[702.19b] (Trample) ...`` will sometimes cite "702.19b", and
sometimes "702.19b (Trample)", or "rule 702.19b", or "702.19b." -- all of which
name a rule it was given, and none of which is that rule's reference as
spelled. Every live answer in the first smoke test was thrown away for exactly
this.

So a citation is matched by what it *names*, then rewritten to the supplied
spelling -- which is also what the client needs to line an answer up against
the rules printed beside it. What is not relaxed is the part that matters: the
decoration comes off, the digits do not.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.rules.corpus import Passage

#: A citation written as "rule 702.19b" or "Rule 702.19b".
_PREFIX = re.compile(r"^rules?\s+", re.IGNORECASE)

#: The title a model copies out of the quoted passage: "702.19b (Trample)".
_TRAILING_TITLE = re.compile(r"\s*\([^()]*\)\s*$")


def resolved(citations: Sequence[str], supplied: Sequence[Passage]) -> tuple[str, ...]:
    """Each citation rewritten to the reference it names, duplicates removed.

    A key two supplied references share is left alone rather than resolved. The
    normalisation is lossy by design -- it takes decoration off -- so it can in
    principle map two of them together, and quietly picking one would rewrite a
    citation into a rule the model did not name. Left as written, it either
    matches something exactly or is reported by the caller.
    """
    known: dict[str, str] = {}
    ambiguous: set[str] = set()
    for passage in supplied:
        key = names(passage.reference)
        if key in known and known[key] != passage.reference:
            ambiguous.add(key)
        known[key] = passage.reference
    return tuple(
        dict.fromkeys(c if names(c) in ambiguous else known.get(names(c), c) for c in citations)
    )


def names(citation: str) -> str:
    """What a citation refers to, with the decoration taken off.

    Narrow on purpose. Brackets, a "rule" prefix, a trailing title and trailing
    punctuation all come off; the digits do not. "702.19b" and "702.19c" stay
    different, which is the only thing this must never get wrong.
    """
    bare = _PREFIX.sub("", citation.strip().strip("[]").strip())
    # Repeated, because the decorations combine: "rule 702.19b (Trample)." has
    # a title *and* a trailing stop, and taking them off in one fixed order
    # left whichever came second in place. Each pass removes at most one, so
    # this settles in two or three.
    while True:
        shorter = _TRAILING_TITLE.sub("", bare).strip().rstrip(".,;").strip()
        if shorter == bare:
            return bare.casefold()
        bare = shorter
