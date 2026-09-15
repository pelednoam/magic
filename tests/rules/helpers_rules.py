"""The excerpt every rules test searches, parsed once -- and which revision it is.

`docs/DECISIONS.md` item 8 asks that each rules scenario record the document
version it was derived from, because the Comprehensive Rules are the authority
and an expectation derived from one revision is not evidence about another.
Every scenario in `tests/rules` is derived from this excerpt, so recording it
once here records it for all of them -- and `test_effective` asserts the
excerpt still says so, which is what stops the record drifting from the file.
"""

from __future__ import annotations

from pathlib import Path

from mtgcoach.rules.corpus import passages_in
from mtgcoach.rules.effective import effective_from

EXCERPT = Path(__file__).resolve().parents[1] / "fixtures" / "rules_excerpt.txt"

#: The excerpt, read once.
TEXT = EXCERPT.read_text(encoding="utf-8")

#: Which revision of the Comprehensive Rules every expectation in this
#: directory was derived from. Read off the excerpt rather than written out, so
#: that re-cutting the fixture from a newer document updates it and cannot
#: leave a stale date behind.
REVISION = effective_from(TEXT)

#: Small enough to read, shaped exactly like the real document: a table of
#: contents whose words repeat later, headings, subrules and a glossary.
PASSAGES = passages_in(TEXT)
