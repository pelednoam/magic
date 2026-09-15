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
from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from helpers_journal import journalled
from helpers_replay import NAME, SEED, recording
from mtgcoach.api.replays import UnknownReplayError, games_in
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from pathlib import Path

#: How many decisions the fixture journal holds.
DECISIONS = 3


def test_a_journal_that_is_not_there(tmp_path: Path) -> None:
    with pytest.raises(UnknownReplayError, match="missing"):
        games_in(tmp_path, "missing")


def test_a_journal_that_is_not_json_at_all(tmp_path: Path) -> None:
    """Nothing readable in it is nothing to show, and says so."""
    path = tmp_path / "selfplay" / "broken.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"kind": "game"', encoding="utf-8")
    with pytest.raises(UnknownReplayError, match="no game recorded"):
        games_in(tmp_path, "broken")


def test_a_half_written_last_line_keeps_everything_before_it(tmp_path: Path) -> None:
    """The normal shape of a run that was killed at three in the morning.

    A journal is appended to as a season plays, so the last line is the one
    most likely to be half-written. Refusing the whole file for it was the
    loudest possible response to the quietest possible problem: every finished
    game in the season became unreadable.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write('{"seed": 7, "turn": 2, "step": "upk')
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS


def test_nothing_after_a_damaged_line_is_trusted(tmp_path: Path) -> None:
    """Stopping, not skipping.

    A *recording* that failed to decode would hand its game's decisions to the
    next recording along -- one game's advice beside another game's board,
    which is the exact failure this format exists to prevent. Everything before
    the damage is good; nothing after it can be trusted to mean what it says.
    """
    path = journalled(tmp_path)
    with path.open("a", encoding="utf-8") as file:
        file.write("{not json at all\n")
        file.write(recording().as_json() + "\n")
    assert [game.index for game in games_in(tmp_path, NAME)] == [0]


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


def test_a_killed_run_does_not_lend_its_advice_to_a_later_game(tmp_path: Path) -> None:
    """The case neither position nor seed survives, and the game id does.

    A run killed mid-game leaves decisions with no recording after them. Run
    the same season again into the same journal -- same seeds, by definition --
    and those orphans sit just before the second run's first recording. Position
    hands them to it; the seed agrees, because it is the same seed. Only an id
    made once per game tells them apart.

    What that looks like on screen is one game's coaching explaining another
    game's board, with nothing saying so. On the screen somebody learns the
    rules from.
    """
    path = tmp_path / "selfplay" / "twice.jsonl"
    path.parent.mkdir(parents=True)
    killed = {
        "seed": SEED,
        "game": "the-run-that-died",
        "turn": 1,
        "step": "upkeep",
        "player": "you",
        "trusted": True,
    }
    finished = replace(recording(), game="the-run-that-finished")
    kept = {**killed, "game": "the-run-that-finished", "step": "precombat_main"}
    path.write_text(
        "\n".join([json.dumps(killed), json.dumps(kept), finished.as_json()]) + "\n",
        encoding="utf-8",
    )
    (game,) = games_in(tmp_path, "twice")
    assert [one.step for one in game.moments] == [Step.PRECOMBAT_MAIN]


def test_a_journal_without_game_ids_still_reads(tmp_path: Path) -> None:
    """Every journal written before the id existed, which is all of them.

    Falls back to what was there before -- the stretch of file, and the seed --
    which is good enough for the journals that exist and was never good enough
    to keep as the only answer.
    """
    journalled(tmp_path)
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS


def test_a_blank_line_is_not_damage(tmp_path: Path) -> None:
    """Not every odd line is a killed run.

    A journal is appended to by a process that opens and closes the file each
    time, so a stray blank line is a real shape and not a truncation -- and
    stopping at one would lose the season for a newline.
    """
    path = journalled(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace("\n", "\n\n"), encoding="utf-8")
    (game,) = games_in(tmp_path, NAME)
    assert len(game.moments) == DECISIONS
