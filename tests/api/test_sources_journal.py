# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""The three revisions, through a journal line and back.

Split from `test_sources`, which is about comparing two games. These are about
the round trip: a revision that is written and never read back is decoration,
and a journal from before any of this existed has to keep opening.
"""

from __future__ import annotations

import json

import pytest

from helpers_api import CATALOGUE, DECKS, RULES, SEATING, server, talking
from helpers_fakes import NoAnswers, NoCoach
from helpers_replay import recording
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from mtgcoach.api.reading import recorded
from mtgcoach.api.sources import Sources
from mtgcoach.core.revision import engine
from wire import decoded, obj

MINE = Sources(engine="engine-1", cards="cards-1", rules="August 7, 2026")


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


def test_a_revision_that_cannot_be_sent_is_not_kept() -> None:
    """One damaged byte in an optional field must not cost the journal.

    `json.loads` accepts an escaped lone surrogate as a perfectly good string,
    and Starlette then raises `UnicodeEncodeError` encoding the response -- so
    the whole journal became unreadable over a field that exists only to
    *explain* a game that will not open.
    """
    line = json.loads(recording().as_json())
    line["sources"] = {"engine": "\ud800", "cards": "c1", "rules": "August 7, 2026"}
    read = recorded(line)
    assert read is not None
    assert read.sources == Sources(cards="c1", rules="August 7, 2026")


def test_a_sources_field_that_is_not_an_object_is_ignored() -> None:
    line = json.loads(recording().as_json())
    line["sources"] = "engine-1"
    read = recorded(line)
    assert read is not None
    assert read.sources == Sources()


def test_a_revision_with_no_document_under_it_is_refused() -> None:
    """A server with no rules installed cannot know which revision it has.

    The claim would ride every board and be recorded on every game. Empty
    means "not recorded", which is true and useful; a revision nothing can be
    searched against is neither.
    """
    with pytest.raises(ValueError, match="no rules index"):
        Claude(rules_revision="August 7, 2026")


# --- and what the server says about itself ------------------------------------


def test_a_board_says_what_produced_it() -> None:
    """A client showing a position should be able to say what produced it."""
    with talking(server()) as client:
        started = decoded(client.post("/games", json={"mine": "green", "theirs": "other"}).json())
    assert obj(started, "sources") == {"engine": engine(), "cards": "", "rules": ""}


def test_a_server_with_a_rules_document_says_which_revision_it_is() -> None:
    """The document's own sentence, read off the copy actually installed."""
    app = create_app(
        CATALOGUE,
        DECKS,
        SEATING,
        Claude(
            explainer=NoCoach(),
            asker=NoAnswers(),
            rules=RULES,
            rules_revision="August 7, 2026",
        ),
    )
    with talking(app) as client:
        started = decoded(client.post("/games", json={"mine": "green", "theirs": "other"}).json())
    assert obj(started, "sources") == {
        "engine": engine(),
        "cards": "",
        "rules": "August 7, 2026",
    }
