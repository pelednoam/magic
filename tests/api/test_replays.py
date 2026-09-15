"""A journal, turned into something a screen can page through.

The tests that matter here are the ones about *exactness*: that the board at a
moment is the board the recorded events produced, and that a journal which
cannot produce one says so rather than showing an empty screen. This is the
code a child learns the rules from, and a plausible-looking wrong board is the
worst thing it could do.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from helpers_replay import ANSWER, NAME, SEED, board_at, journalled, recording
from mtgcoach.api.replays import UnknownReplayError, games_in, journals
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from pathlib import Path

#: How many decisions the fixture journal holds.
DECISIONS = 3


def test_a_journal_is_listed(tmp_path: Path) -> None:
    journalled(tmp_path)
    assert journals(tmp_path) == (NAME,)


def test_a_data_root_with_no_journals_lists_none(tmp_path: Path) -> None:
    """Not an error: a server that has never run a season is a normal server."""
    assert journals(tmp_path) == ()


def test_journals_come_back_newest_first(tmp_path: Path) -> None:
    """Because the interesting one is almost always the last run."""
    older = journalled(tmp_path, "zebra")
    newer = journalled(tmp_path, "aardvark")
    # Set explicitly. Two files written in the same millisecond have the same
    # mtime, and the tie would be broken alphabetically -- which would make
    # this pass or fail on the names rather than on the order.
    os.utime(older, (0, 1000))
    os.utime(newer, (0, 2000))
    assert journals(tmp_path) == ("aardvark", "zebra")


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


def test_a_game_comes_back_with_its_decisions(tmp_path: Path) -> None:
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    assert game.seed == SEED
    assert game.decks == ("green", "other")
    assert len(game.moments) == DECISIONS


def test_the_moments_walk_forwards(tmp_path: Path) -> None:
    """In turn order, not in the order the lines happen to be written.

    A journal is appended to as a game happens, so the file order is usually
    right -- and "usually" is not what somebody stepping through a game to
    learn the rules needs from the back button.
    """
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    assert [one.step for one in game.moments] == [
        Step.PRECOMBAT_MAIN,
        Step.DECLARE_ATTACKERS,
        Step.POSTCOMBAT_MAIN,
    ]


def test_a_moment_carries_the_board_the_events_produced(tmp_path: Path) -> None:
    """The exactness claim, stated as a test.

    Not a board like the one that was played -- the one that was played. The
    state on entering the step is what the coach was shown, so it is what the
    child is shown asking about the same decision.
    """
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    assert game.moments[0].state == board_at(Step.PRECOMBAT_MAIN)
    assert game.moments[1].state == board_at(Step.DECLARE_ATTACKERS)


def test_an_answer_comes_back_as_the_thing_the_coach_returns(tmp_path: Path) -> None:
    """So a replayed moment goes out through the same view as a live one."""
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    said = game.moments[0].said
    assert said is not None
    assert said.in_short == ANSWER["in_short"]
    assert said.attack == ("you-4",)
    assert game.moments[0].trusted


def test_an_answer_the_engine_refused_keeps_its_objections(tmp_path: Path) -> None:
    """Shown, not hidden: it is the rule being stated out loud."""
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    doubted = game.moments[1]
    assert not doubted.trusted
    assert doubted.problems == ("Grizzly Bears cannot attack: it entered this turn.",)


def test_a_moment_with_no_answer_keeps_why(tmp_path: Path) -> None:
    """A real moment. The game carried on without advice, and that shows."""
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    refused = game.moments[2]
    assert refused.said is None
    assert refused.error == "no answer: the coach was not available"


def test_decisions_from_another_game_are_not_borrowed(tmp_path: Path) -> None:
    """A journal holds a whole season. Moments belong to one game in it."""
    path = journalled(tmp_path)
    other = recording()
    with path.open("a", encoding="utf-8") as file:
        file.write('{"seed": 99, "turn": 1, "step": "upkeep", "player": "you", "trusted": true}\n')
        file.write(other.as_json().replace(f'"seed": {SEED}', '"seed": 99') + "\n")
    played = {game.seed: game for game in games_in(tmp_path, NAME)}
    assert len(played[SEED].moments) == DECISIONS
    assert [one.step for one in played[99].moments] == [Step.UPKEEP]


def test_a_decision_at_a_step_that_is_not_one_is_ignored(tmp_path: Path) -> None:
    """A line from a newer engine, or a corrupted one. Either way, not a step."""
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write('{"seed": 7, "turn": 1, "step": "second_main", "player": "you"}\n')
        file.write('{"seed": 7, "turn": "one", "step": "upkeep", "player": "you"}\n')
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS


def test_a_malformed_answer_still_makes_an_explanation(tmp_path: Path) -> None:
    """Every field is read defensively, because a journal is a file on a disk."""
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write(
            '{"seed": 7, "turn": 1, "step": "end_step", "player": "you", '
            '"answer": {"attack": "all of them"}, "problems": "none"}\n'
        )
    (game,) = games_in(tmp_path, NAME)
    late = game.moments[-1]
    assert late.said is not None
    assert late.said.attack == ()
    assert late.problems == ()


def test_a_line_that_is_not_an_object_is_walked_past(tmp_path: Path) -> None:
    """Valid JSON, and not a line this format has ever written.

    Skipped rather than fatal: a journal is appended to by a process that can
    be killed, and refusing a whole season over one strange line would lose
    every game in it.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write("42\n")
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS
