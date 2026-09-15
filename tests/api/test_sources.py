# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""Which engine, card data and rules a game was played under.

`docs/DECISIONS.md` item 5: a journal recorded its events and not the versions
that produced them, "which is exactly what made item 6 a question, and what
made a whole directory of journals unreadable when priority arrived with
nothing recording that they predated it."

Two things are being checked. That the three revisions survive a round trip
through a journal line -- a revision that is written and not read back is
decoration. And that comparing them is *useful*: a journal that recorded
nothing must read as old rather than as three things having changed, because
the difference worth seeing is the one field that moved.
"""

from __future__ import annotations

from dataclasses import fields

from mtgcoach.api.recording import SOURCE_FIELDS
from mtgcoach.api.sources import UNRECORDED, Sources

MINE = Sources(engine="engine-1", cards="cards-1", rules="August 7, 2026")


# --- comparing two games ------------------------------------------------------


def test_the_same_revisions_differ_in_nothing() -> None:
    assert MINE.differs_from(MINE) == ()


def test_each_revision_is_named_when_it_moves() -> None:
    moved = Sources(engine="engine-2", cards="cards-2", rules="July 1, 2024")
    assert MINE.differs_from(moved) == ("engine", "card data", "rules")


def test_only_what_moved_is_named() -> None:
    """The case worth seeing: two of three the same, one not."""
    newer = Sources(engine="engine-2", cards="cards-1", rules=MINE.rules)
    assert MINE.differs_from(newer) == ("engine",)


def test_a_revision_nobody_recorded_is_not_a_difference() -> None:
    """Otherwise an old journal reports all three as changed.

    Which says nothing except that the journal is old, and would drown the one
    case a person needs to see.
    """
    assert MINE.differs_from(Sources()) == ()
    assert Sources().differs_from(MINE) == ()


def test_a_missing_field_does_not_hide_the_ones_that_are_there() -> None:
    """A journal that records two of three still says what it knows."""
    partly = Sources(engine="engine-2", cards=UNRECORDED, rules=MINE.rules)
    assert MINE.differs_from(partly) == ("engine",)


def test_the_field_names_the_journal_uses_are_the_fields_there_are() -> None:
    """`reading` builds a `Sources` by keyword from these names.

    So a field renamed on one side and not the other is a `TypeError` on the
    first journal read -- or, if the rename went the other way, a revision
    written and silently never read back. One list, asserted against the type.
    """
    assert set(SOURCE_FIELDS) == {one.name for one in fields(Sources)}
