"""The excerpt every rules test searches, parsed once."""

from __future__ import annotations

from pathlib import Path

from mtgcoach.rules.corpus import passages_in

EXCERPT = Path(__file__).resolve().parents[1] / "fixtures" / "rules_excerpt.txt"

#: Small enough to read, shaped exactly like the real document: a table of
#: contents whose words repeat later, headings, subrules and a glossary.
PASSAGES = passages_in(EXCERPT.read_text(encoding="utf-8"))
