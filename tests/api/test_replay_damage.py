"""Every way a journal can be damaged, and what the screen does about it.

Split from ``test_replays`` at the line limit, and the seam is the real one:
that file is about finding the games in a good journal, this one is about a
journal written by a process that was killed at three in the morning.

The rule throughout: a damaged game is *skipped*, never repaired. A board
rebuilt from a deal with one card missing is a board that never existed, and
nothing on screen would say so -- which on the one screen somebody learns the
rules from is much worse than a game that cannot be shown.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from helpers_replay import NAME, SEED, journalled, recording
from mtgcoach.api.recording import KIND
from mtgcoach.api.replays import UnknownReplayError, games_in
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from pathlib import Path

#: How many decisions the fixture journal holds.
DECISIONS = 3


def test_a_journal_that_is_not_there(tmp_path: Path) -> None:
    with pytest.raises(UnknownReplayError, match="missing"):
        games_in(tmp_path, "missing")


def test_a_journal_that_is_not_json(tmp_path: Path) -> None:
    """A half-written line is a shape a killed run leaves behind."""
    path = tmp_path / "selfplay" / "broken.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"kind": "game"', encoding="utf-8")
    with pytest.raises(UnknownReplayError, match="JSONDecodeError"):
        games_in(tmp_path, "broken")


def test_a_journal_of_decisions_with_no_game_says_so(tmp_path: Path) -> None:
    """The shape the first overnight run left: advice, and no board for it.

    Saying which is better than an empty screen. It can still be replayed
    *inside* the harness, and it cannot be shown, and those are different
    things a person needs to be able to tell apart.
    """
    path = tmp_path / "selfplay" / "decisions.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"seed": 7, "turn": 1, "step": "upkeep", "player": "you"}\n', encoding="utf-8")
    with pytest.raises(UnknownReplayError, match="interrupted run"):
        games_in(tmp_path, "decisions")


def test_a_line_that_is_not_an_object_is_walked_past(tmp_path: Path) -> None:
    """Valid JSON, and not a line this format has ever written.

    Skipped rather than fatal: a journal is appended to by a process that can
    be killed, and refusing a whole season over one strange line would lose
    every game in it.
    """
    journalled(tmp_path, extra=["42"])
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS


def test_a_game_that_will_not_rebuild_is_skipped_not_fatal(tmp_path: Path) -> None:
    """One damaged game must not take a season with it.

    A library too short for an opening hand raises out of ``start_game``. It
    used to raise all the way out of the route, so a journal with one bad game
    in it answered 500 and every good game in it became unreadable.
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
    assert [game.seed for game in played] == [SEED, SEED]


def test_a_journal_of_only_damaged_games_says_so(tmp_path: Path) -> None:
    """Rather than an empty screen, or a 500."""
    path = tmp_path / "selfplay" / "wrecked.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "kind": KIND,
                "seed": 8,
                "decks": [],
                "first": "you",
                "libraries": {"you": [["a", "Forest"]]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(UnknownReplayError, match="can be rebuilt"):
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
