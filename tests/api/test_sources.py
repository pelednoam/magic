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

import json

from helpers_api import CATALOGUE, DECKS, SEATING, server, talking
from helpers_fakes import NoAnswers, NoCoach
from helpers_replay import recording
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from mtgcoach.api.reading import recorded
from mtgcoach.api.sources import UNRECORDED, Sources
from mtgcoach.core.revision import engine
from wire import decoded, obj

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


# --- through a journal line ---------------------------------------------------


def _roundtripped(sources: Sources) -> Sources:
    """What a recording's revisions read back as, after a trip through JSON."""
    read = recorded(json.loads(recording(sources).as_json()))
    assert read is not None
    return read.sources


def test_the_revisions_survive_a_journal_line() -> None:
    """Written and read back by the two halves of the format.

    A revision that is written and never read is decoration, and this is the
    same round trip `test_eventspec` asserts over events -- for the same
    reason: a recorded game is only as good as what comes back out of it.
    """
    assert _roundtripped(MINE) == MINE


def test_a_game_that_recorded_nothing_reads_back_as_nothing() -> None:
    assert _roundtripped(Sources()) == Sources()


def test_a_journal_line_with_no_revisions_at_all_is_readable() -> None:
    """Every journal on disk is one of these.

    Refusing them in order to fix journals being unreadable would be a poor
    trade.
    """
    line = json.loads(recording().as_json())
    del line["sources"]
    read = recorded(line)
    assert read is not None
    assert read.sources == Sources()


def test_something_that_is_not_a_revision_is_not_recorded_as_one() -> None:
    """A number or a null where a revision should be is not a revision.

    Recording it as "3" would put a claim in front of somebody that nothing
    supports -- and the whole value of these is that they are either true or
    absent.
    """
    line = json.loads(recording().as_json())
    line["sources"] = {"engine": 3, "cards": None, "rules": "August 7, 2026"}
    read = recorded(line)
    assert read is not None
    assert read.sources == Sources(rules="August 7, 2026")


def test_a_sources_field_that_is_not_an_object_is_ignored() -> None:
    line = json.loads(recording().as_json())
    line["sources"] = "engine-1"
    read = recorded(line)
    assert read is not None
    assert read.sources == Sources()


# --- and what the server says about itself ------------------------------------


def test_a_board_says_what_produced_it() -> None:
    """A client showing a position should be able to say what produced it."""
    with talking(server()) as client:
        started = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
    assert obj(started, "sources") == {"engine": engine(), "cards": "", "rules": ""}


def test_a_server_with_a_rules_document_says_which_revision_it_is() -> None:
    """The document's own sentence, read off the copy actually installed."""
    app = create_app(
        CATALOGUE,
        DECKS,
        SEATING,
        Claude(explainer=NoCoach(), asker=NoAnswers(), rules_revision="August 7, 2026"),
    )
    with talking(app) as client:
        started = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
    assert obj(started, "sources") == {
        "engine": engine(),
        "cards": "",
        "rules": "August 7, 2026",
    }
