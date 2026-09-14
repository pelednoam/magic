"""Playing a coached game again, from what the coach said the first time.

The engine is deterministic, so a seed reproduces a deal and a policy exactly.
The coach is not. These are about the two questions a journal answers: the
identical game in a second, and what a changed engine makes of a game the
coach already played.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from helpers_selfplay import BOOK, THEM, YOU, game, main_phase

from mtgcoach.coach.advice import Explanation
from mtgcoach.coach.report import advise
from mtgcoach.selfplay.coached import Coached
from mtgcoach.selfplay.journal import Answers, Decision, Journal, fields, read
from mtgcoach.selfplay.moves import Move, Seat
from mtgcoach.selfplay.playing import play
from mtgcoach.selfplay.replaying import DivergedError, Replayed

if TYPE_CHECKING:
    from pathlib import Path


class Deciding:
    """An explainer that plays the first thing it is offered."""

    def explain(self, report: object, briefing: str) -> Explanation:
        """Whatever is playable, or nothing."""
        del briefing
        playable = getattr(report, "playable", ())
        card = str(playable[0].instance_id) if playable else ""
        return Explanation(play=card, because="the first thing", in_short="the first thing")


def test_a_journalled_game_replays_identically(tmp_path: Path) -> None:
    """The whole point.

    Twenty minutes of Claude, kept, and then run again in a second -- which is
    what turns a bad decision into something to study rather than something
    that happened once.
    """
    where = tmp_path / "run.jsonl"
    seats = (
        Seat(YOU, "x", Coached(explainer=Deciding(), seed=1, journal=Journal(where))),
        Seat(THEM, "y", Coached(explainer=Deciding(), seed=1, journal=Journal(where))),
    )
    first = play(seats, game(), BOOK, seed=1)

    answers = read(where)
    again = play(
        (
            Seat(YOU, "x", Replayed(answers=answers, seed=1)),
            Seat(THEM, "y", Replayed(answers=answers, seed=1)),
        ),
        game(),
        BOOK,
        seed=1,
    )
    assert (again.turns, again.events, again.winner, again.ending) == (
        first.turns,
        first.events,
        first.winner,
        first.ending,
    )
    assert again.clean


def test_a_moment_the_journal_does_not_have_is_refused() -> None:
    """Not guessed.

    A replay whose gaps are filled with "do nothing" is not a replay, and the
    divergence it hides is the most interesting thing that could happen.
    """
    state = main_phase()
    agent = Replayed(answers=Answers(), seed=1)
    with pytest.raises(DivergedError, match="no decision for"):
        agent.act(state, advise(state, YOU, BOOK), YOU)


def test_a_divergence_becomes_trouble_rather_than_a_traceback() -> None:
    """The loop catches it, so a season survives one bad journal."""
    seats = (
        Seat(YOU, "x", Replayed(answers=Answers(), seed=1)),
        Seat(THEM, "y", Replayed(answers=Answers(), seed=1)),
    )
    played = play(seats, game(), BOOK, seed=1)
    assert played.trouble
    assert "no decision for" in played.trouble[0].detail


def test_a_journalled_refusal_replays_as_one() -> None:
    state = main_phase()
    moment = (1, state.turn, str(state.step), str(YOU))
    answers = Answers(
        said={
            moment: Decision(
                seed=1,
                turn=state.turn,
                step=str(state.step),
                player=str(YOU),
                briefing="",
                error="timed out",
            )
        }
    )
    agent = Replayed(answers=answers, seed=1)
    assert agent.act(state, advise(state, YOU, BOOK), YOU) == Move()
    assert agent.tally.refused == 1


def test_an_answer_that_no_longer_passes_is_reported_with_what_it_was() -> None:
    """The regression worth knowing about.

    An answer that was trusted last week and fails today is what replaying
    against a changed engine is for, so the journal's own verdict is carried
    into the complaint.
    """
    state = main_phase()
    moment = (1, state.turn, str(state.step), str(YOU))
    answers = Answers(
        said={
            moment: Decision(
                seed=1,
                turn=state.turn,
                step=str(state.step),
                player=str(YOU),
                briefing="",
                answer=fields(Explanation(play="no-such-card", because="x", in_short="x")),
                trusted=True,
            )
        }
    )
    agent = Replayed(answers=answers, seed=1)
    assert agent.act(state, advise(state, YOU, BOOK), YOU) == Move()
    assert agent.tally.untrusted == 1
    assert "journal said trusted=True" in agent.tally.disagreements[0]
