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

from helpers_journal import ANSWER, journalled
from helpers_replay import NAME, SEED, board_at, recording
from mtgcoach.api.replays import games_in, journals
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


def test_decisions_belong_to_the_game_they_were_written_during(tmp_path: Path) -> None:
    """A journal holds a whole season, cut into games at each recording line.

    Position, not seed. The harness appends a decision as it happens and the
    recording when the game ends, so the lines between two recordings are one
    game's -- which is the only join that survives two runs into the same
    journal repeating a seed.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write('{"seed": 7, "turn": 1, "step": "upkeep", "player": "you", "trusted": true}\n')
        file.write(recording().as_json() + "\n")
    first, second = games_in(tmp_path, NAME)
    assert (first.index, second.index) == (0, 1)
    assert len(first.moments) == DECISIONS
    assert [one.step for one in second.moments] == [Step.UPKEEP]


def test_two_games_with_the_same_seed_are_told_apart(tmp_path: Path) -> None:
    """Which a season re-run into an existing journal produces immediately.

    Keyed by seed, the second game's advice appeared beside the first game's
    board -- one game's coaching explaining another game's position, with
    nothing on screen saying so.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write('{"seed": 7, "turn": 1, "step": "upkeep", "player": "you"}\n')
        file.write(recording().as_json() + "\n")
    first, second = games_in(tmp_path, NAME)
    assert first.seed == second.seed == SEED
    assert len(first.moments) != len(second.moments)


def test_a_decision_at_a_step_that_is_not_one_is_ignored(tmp_path: Path) -> None:
    """A line from a newer engine, or a corrupted one. Either way, not a step."""
    journalled(
        tmp_path,
        extra=[
            '{"seed": 7, "turn": 1, "step": "second_main", "player": "you"}',
            '{"seed": 7, "turn": "one", "step": "upkeep", "player": "you"}',
        ],
    )
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS


def test_a_malformed_answer_still_makes_an_explanation(tmp_path: Path) -> None:
    """Every field is read defensively, because a journal is a file on a disk."""
    journalled(
        tmp_path,
        extra=[
            (
                '{"seed": 7, "turn": 1, "step": "end_step", "player": "you", '
                '"answer": {"attack": "all of them"}, "problems": "none"}'
            )
        ],
    )
    (game,) = games_in(tmp_path, NAME)
    late = game.moments[-1]
    assert late.said is not None
    assert late.said.attack == ()
    assert late.problems == ()


def test_the_word_false_is_not_a_verdict(tmp_path: Path) -> None:
    """A JSON string is truthy, and "checked" is not a claim to make on that.

    Nothing the harness writes puts a string here. This is a file on a disk,
    and labelling unchecked advice "checked" on a screen somebody learns the
    rules from is the exact failure this project exists to avoid.
    """
    journalled(
        tmp_path,
        extra=[
            (
                '{"seed": 7, "turn": 1, "step": "end_step", "player": "you", '
                '"answer": {"in_short": "x"}, "trusted": "false"}'
            )
        ],
    )
    (game,) = games_in(tmp_path, NAME)
    assert not game.moments[-1].trusted
