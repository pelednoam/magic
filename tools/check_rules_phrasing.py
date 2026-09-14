"""Check that every phrase ``rules.phrasing`` adds is really in the rules.

``phrasing`` maps a beginner's paraphrase to the wording the Comprehensive
Rules use, so that a question can match a rule it shares no words with. That
only works while the wording is still the document's. Wizards revise the rules
with every set, and a target they have reworded stops matching anything: the
question goes back to retrieving the wrong passages, the answer goes back to
"the rules I was given don't cover this", and *nothing else notices*. The unit
tests check the map against a hand-written excerpt, which is by construction a
document where the phrases are still right.

So this reads the installed rules and looks for each phrase. No model call, no
network, a second on a one-megabyte file.

The list of phrases is imported rather than copied. A copy is the same failure
one level up: somebody adds an entry to ``phrasing`` and not here, and the
check passes having looked for the old ones.

Skipped, loudly, when the rules are not installed. They are not vendored --
they are Wizards' document and a stale copy is exactly the confidently-wrong
answer this project exists to avoid -- so a fresh checkout has none, and a
machine without them cannot answer a rules question anyway. The skip prints
rather than passing silently, because a green run there says nothing about the
phrases.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

from mtgcoach.rules.library import rules_path
from mtgcoach.rules.phrasing import TARGETS

#: Where the server looks for the document by default; ``serve --data`` can
#: point elsewhere, and this check is about the ordinary case.
DEFAULT_DATA: Final = Path("data")


def missing(document: str, targets: frozenset[str] = TARGETS) -> list[str]:
    """Every target the document does not contain, in a stable order.

    Compared lowercased. The document's curly quotes are left alone, which
    matters only for a target with an apostrophe in it -- there is none, and a
    comment in ``phrasing`` is a better place to keep it that way than a
    normalising pass here that would hide the problem.
    """
    lowered = document.lower()
    return sorted(target for target in targets if target.lower() not in lowered)


def main() -> int:
    """Check the phrases, or say why the check was skipped."""
    rules = rules_path(DEFAULT_DATA)
    if not rules.is_file():
        print(f"== rules phrasing    SKIPPED: {rules} is not installed")
        return 0
    try:
        document = rules.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"could not read {rules}: {type(exc).__name__}")
        return 1
    absent = missing(document)
    for phrase in absent:
        print(f"{rules} no longer contains {phrase!r}, which rules/phrasing.py searches for")
    if absent:
        print("A reworded target matches nothing. Update phrasing.py and its tests.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
