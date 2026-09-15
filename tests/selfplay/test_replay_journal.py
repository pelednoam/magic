"""What a replay writes down, so a re-run can be walked through.

Split from ``test_replaying`` at the line limit, and the seam is a real one:
that file is about a replay producing the same *game*, this one is about it
producing the same *journal* -- which is what turns a coached season from
before the harness recorded games into one the step-through screen can show.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_selfplay import BOOK, YOU, main_phase

from mtgcoach.coach.advice import Explanation
from mtgcoach.coach.report import advise
from mtgcoach.selfplay.answers import Answers, read
from mtgcoach.selfplay.journal import Decision, Journal, fields
from mtgcoach.selfplay.replaying import Replayed

if TYPE_CHECKING:
    from pathlib import Path


def journalled_replay(tmp_path: Path, found: Decision) -> Path:
    """Replay one moment with a journal attached, and say where it went."""
    where = tmp_path / "again.jsonl"
    state = main_phase()
    agent = Replayed(
        answers=Answers(said={(1, state.turn, str(state.step), str(YOU)): found}),
        seed=1,
        journal=Journal(where),
    )
    agent.act(state, advise(state, YOU, BOOK), YOU)
    return where


def written(tmp_path: Path, found: Decision) -> Decision:
    """The single decision a journalled replay wrote."""
    ((made,),) = (tuple(read(journalled_replay(tmp_path, found)).said.values()),)
    return made


def test_a_replay_writes_a_journal_of_its_own(tmp_path: Path) -> None:
    """Which is what makes a re-run walkable.

    A coached season from before the harness recorded games has advice and no
    boards. Replaying it writes both -- in seconds, without asking the model
    anything -- and the result is a journal the step-through screen can show.
    """
    state = main_phase()
    said = Explanation(play="", because="Nothing to do.", in_short="Pass.")
    made = written(
        tmp_path,
        Decision(
            seed=1,
            turn=state.turn,
            step=str(state.step),
            player=str(YOU),
            briefing="the board, as the model was shown it",
            answer=fields(said),
            trusted=True,
        ),
    )
    assert made.briefing == "the board, as the model was shown it"
    assert made.answer == fields(said)
    assert made.trusted


def test_the_journal_a_replay_writes_carries_todays_verdict(tmp_path: Path) -> None:
    """Not the one the old journal had.

    The new journal describes the run that just happened. An answer the engine
    accepted last week and refuses today is written down as refused, because
    that is what happened in this game -- and it is what somebody stepping
    through it needs to read. The comparison with the old verdict lives in the
    tally, which is where a person looking for regressions looks.
    """
    state = main_phase()
    made = written(
        tmp_path,
        Decision(
            seed=1,
            turn=state.turn,
            step=str(state.step),
            player=str(YOU),
            briefing="",
            answer=fields(Explanation(play="no-such-card", because="x", in_short="x")),
            trusted=True,
        ),
    )
    assert not made.trusted
    assert made.problems != ()


def test_a_replay_with_no_journal_writes_nothing(tmp_path: Path) -> None:
    """The default, which is what every test and every throwaway run wants."""
    state = main_phase()
    agent = Replayed(
        answers=Answers(
            said={
                (1, state.turn, str(state.step), str(YOU)): Decision(
                    seed=1,
                    turn=state.turn,
                    step=str(state.step),
                    player=str(YOU),
                    briefing="",
                    error="timed out",
                )
            }
        ),
        seed=1,
    )
    agent.act(state, advise(state, YOU, BOOK), YOU)
    assert list(tmp_path.iterdir()) == []


def test_a_refusal_is_journalled_too(tmp_path: Path) -> None:
    """A moment with no advice is a real moment, and the game carried on."""
    state = main_phase()
    made = written(
        tmp_path,
        Decision(
            seed=1,
            turn=state.turn,
            step=str(state.step),
            player=str(YOU),
            briefing="",
            error="timed out",
        ),
    )
    assert made.answer is None
    assert made.error == "timed out"
    assert not made.trusted
