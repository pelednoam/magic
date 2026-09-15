"""One damaged game must not take a season with it.

Split from ``test_replay_damage``, which is about a journal that cannot be read
at all. These are about a journal that reads fine and holds one game that will
not rebuild -- the shape a killed run leaves, and the shape a game recorded
before the engine grew stricter leaves. Neither may be a 500, and neither may
quietly move the games around it.

Such a game is *listed*, with no moments and the reason it has none. It used to
be dropped, which threw away the one thing that explains it: the recording says
which engine played it, and "played under a different engine" is what turns a
game that will not open from a puzzle into a fact.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from helpers_journal import journalled
from helpers_replay import NAME, SEED, SOURCES, recording
from mtgcoach.api.recording import KIND
from mtgcoach.api.replays import UnknownReplayError, games_in
from mtgcoach.api.sources import Sources
from mtgcoach.core.events import PlayLand
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from pathlib import Path

#: How many decisions the fixture journal holds.
DECISIONS = 3


def test_a_game_that_will_not_rebuild_does_not_take_the_season_with_it(
    tmp_path: Path,
) -> None:
    """A library too short for an opening hand raises out of ``start_game``.

    It used to raise all the way out of the route, so a journal with one bad
    game in it answered 500 and every good game in it became unreadable.
    """
    path = journalled(tmp_path)
    broken = recording()
    with path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "kind": KIND,
                    "seed": 8,
                    "decks": ["green", "other"],
                    "first": "you",
                    "libraries": {"you": [["a", "Forest"]], "them": [["b", "Forest"]]},
                    "events": [],
                }
            )
            + "\n"
        )
        file.write(broken.as_json() + "\n")
    played = games_in(tmp_path, NAME)
    assert [game.seed for game in played] == [SEED, 8, SEED]
    damaged = played[1]
    assert damaged.moments == (), "nothing to walk"
    assert "opening hand" in damaged.problem, "and the reason, where it is read"
    # This one was written by hand above with no revisions in it, which is what
    # every journal on disk looks like; the one below records them.
    assert damaged.sources == Sources()


def test_a_journal_with_no_recording_in_it_says_so(tmp_path: Path) -> None:
    """The shape a killed run leaves: decisions, and no game written down.

    Rather than an empty screen, or a 500. A journal whose recordings are
    *there* and will not rebuild is a different thing and is listed -- this is
    about one that never got as far as recording a game.
    """
    path = tmp_path / "selfplay" / "wrecked.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"seed": 8, "turn": 1, "step": "upkeep", "player": "you"}\n', encoding="utf-8")
    with pytest.raises(UnknownReplayError, match="no game recorded"):
        games_in(tmp_path, "wrecked")


def test_a_damaged_deal_takes_only_its_own_game(tmp_path: Path) -> None:
    """A library with a card that is not a card is refused, not repaired."""
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(
                {
                    "kind": KIND,
                    "seed": 9,
                    "decks": ["green", "other"],
                    "first": "you",
                    "libraries": {"you": [["a"], ["b", "Forest"]]},
                }
            )
            + "\n"
        )
    # Not listed at all, unlike a game that *reads* and will not rebuild: a
    # library with a non-card in it is refused while the line is being read,
    # so there is no recording to list. Dropping one card and carrying on
    # would deal different hands and different draws from the game that was
    # played, with nothing on screen saying so.
    played = games_in(tmp_path, NAME)
    assert [game.seed for game in played] == [SEED]


def test_two_decisions_in_one_step_are_both_kept(tmp_path: Path) -> None:
    """The defender is asked at declare-blockers, which the rules require.

    The harness does not do that yet. The journal line has always carried a
    player, and a key that threw it away would have kept the last of the two
    and shown one player's advice as the other's -- silently, the day somebody
    added blocking.
    """
    journalled(
        tmp_path,
        extra=[
            '{"seed": 7, "turn": 1, "step": "declare_blockers", "player": "them"}',
            '{"seed": 7, "turn": 1, "step": "declare_blockers", "player": "you"}',
        ],
    )
    (game,) = games_in(tmp_path, NAME)
    blocking = [one.player for one in game.moments if one.step is Step.DECLARE_BLOCKERS]
    assert sorted(blocking) == ["them", "you"]


def test_a_game_whose_events_the_engine_now_refuses_is_skipped(tmp_path: Path) -> None:
    """The scenario docs/SELFPLAY.md says to expect, as a test.

    Replaying against a stricter engine diverges: a move that was legal when it
    was recorded can be refused today. That comes out of `apply` as an
    `IllegalEventError`, which is not a `ValueError` -- so an `except
    ValueError` around the rebuild let it reach the route as a 500, taking every
    good game in the journal with it.
    """
    path = journalled(tmp_path)
    refused = replace(
        recording(),
        seed=8,
        # A land drop naming a card that is not in the game. Whatever the
        # engine refuses today is what a game recorded before it grew stricter
        # looks like; this is the cheapest thing it refuses.
        events=(PlayLand(PlayerId("you"), InstanceId("nobody")),),
    )
    with path.open("a", encoding="utf-8") as file:
        file.write(refused.as_json() + "\n")
    played = games_in(tmp_path, NAME)
    assert [game.index for game in played] == [0, 1]
    assert played[1].moments == ()
    # The engine's own words, which name the card it refused...
    assert "nobody" in played[1].problem
    # ...and what the game was played under, which is the thing that explains
    # it. Dropping the game from the list threw this away with it.
    assert played[1].sources == SOURCES


def test_orphaned_decisions_do_not_attach_to_a_later_game(tmp_path: Path) -> None:
    """The shape two runs into one journal leave behind.

    A run killed mid-game leaves its decisions in the *middle* of the file, with
    no recording after them. Append a second run and they sit just before
    somebody else's recording -- so position alone hands one game's advice to
    another game's board, which is the exact thing this format exists to stop.
    The seed is what catches it.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        # The killed run: a decision for a game whose recording never arrived.
        file.write('{"seed": 8, "turn": 1, "step": "upkeep", "player": "you"}\n')
        # A later run, appended to the same journal, that did finish.
        file.write(recording().as_json().replace('"seed": 7', '"seed": 9') + "\n")
    _, later = games_in(tmp_path, NAME)
    assert later.seed == 9
    assert later.moments == ()
