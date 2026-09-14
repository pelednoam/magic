"""A whole game, and what the loop does when something goes wrong in one.

The loop itself is dull on purpose. These cover the parts that are not: that a
game ends the ways a game can end, that an agent naming something the engine
never offered is recorded rather than applied, and that nothing an agent does
can stop a season.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helpers_selfplay import BOOK, THEM, YOU, game

from helpers_coach import Book
from mtgcoach.core.ids import InstanceId
from mtgcoach.core.reduce import apply
from mtgcoach.selfplay.moves import Idle, Move, Seat
from mtgcoach.selfplay.playing import TURN_CAP, play
from mtgcoach.selfplay.policy import Greedy
from mtgcoach.selfplay.records import Kind

if TYPE_CHECKING:
    import pytest

    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.events import Event
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class Fixed:
    """An agent that always says the same thing."""

    move: Move
    name: str = "fixed"

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """The same move, whatever the board."""
        del state, report, player
        return self.move


def seats(first: object, second: object) -> tuple[Seat, Seat]:
    """Two seats with these agents."""
    return (Seat(YOU, "forests", first), Seat(THEM, "forests", second))  # type: ignore[arg-type]


def test_two_idle_agents_still_play_a_whole_game() -> None:
    """The cheapest real test of the step walker there is.

    Nobody does anything, so the game can only end by somebody drawing from an
    empty library -- and getting there means every step of every turn ran.
    """
    played = play(seats(Idle(), Idle()), game(), BOOK, seed=1)
    assert played.clean, played.trouble
    assert played.ending == "decked"
    assert played.turns > 10
    assert played.events > 100


def test_a_greedy_game_ends_and_stays_clean() -> None:
    played = play(seats(Greedy(seed=2), Greedy(seed=3)), game(), BOOK, seed=2)
    assert played.clean, played.trouble
    assert played.ending in {"decked", "life"}


def test_an_agent_naming_a_card_it_does_not_have_is_recorded_not_applied() -> None:
    """A bad agent must not be able to produce an illegal state.

    Otherwise every later finding in the season is the agent's fault rather
    than the engine's, and the harness stops being evidence.
    """
    invented = Fixed(Move(play=InstanceId("no-such-card")))
    played = play(seats(invented, Idle()), game(), BOOK, seed=4)
    assert played.trouble
    assert all(problem.kind is Kind.REFUSED for problem in played.trouble)
    assert all("not a playable card" in problem.detail for problem in played.trouble)


def test_an_agent_inventing_an_attack_is_recorded_not_applied() -> None:
    """An attack the engine never costed has no numbers to apply.

    The harness applies the *engine's* outcome, so there is nothing to use.
    """
    invented = Fixed(Move(attack=(InstanceId("no-such-creature"),)))
    played = play(seats(invented, Idle()), game(), BOOK, seed=5)
    assert played.trouble
    assert all("no costed attack" in problem.detail for problem in played.trouble)


def test_an_agent_that_raises_does_not_stop_the_game() -> None:
    """A season of a thousand games must not stop at the first one."""

    @dataclass(frozen=True, slots=True)
    class Exploding:
        """An agent with a bug in it."""

        name: str = "exploding"

        def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
            """Fail."""
            del state, report, player
            msg = "something nobody predicted"
            raise RuntimeError(msg)

    played = play(seats(Exploding(), Idle()), game(), BOOK, seed=6)
    assert played.trouble
    assert played.trouble[0].kind is Kind.CRASH
    assert "RuntimeError" in played.trouble[0].detail
    assert played.ending == "decked", "the game still finished"


def test_a_game_that_will_not_end_is_a_finding() -> None:
    """Not a hang.

    The cap is well past where two real decks deck out, so reaching it means
    something is wrong rather than slow.
    """
    huge = game(forests=400, bears=400)
    played = play(seats(Idle(), Idle()), huge, BOOK, seed=7)
    assert played.ending == "no end"
    assert played.turns > TURN_CAP
    assert any(problem.kind is Kind.STUCK for problem in played.trouble)


def test_the_loser_is_the_one_who_ran_out_of_life() -> None:
    played = play(seats(Greedy(seed=8), Idle()), game(), BOOK, seed=8)
    if played.ending == "life":
        assert played.winner == YOU


def test_a_game_records_what_it_could_not_speak_for() -> None:
    """The single most useful number for deciding what to work on next."""
    played = play(seats(Idle(), Idle()), game(), Book(), seed=9)
    assert "Forest" in played.unknown
    assert "Grizzly Bears" in played.unknown


def test_a_step_that_crashes_is_recorded_and_the_game_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The step walker raising is not something an agent can cause.

    It is the one path in the loop nothing else reaches, and a season must
    survive it the way it survives an agent's bug.
    """
    real = apply
    seen = {"n": 0}

    def fails(state: GameState, event: Event) -> GameState:
        """Work twice, then break."""
        seen["n"] += 1
        if seen["n"] > 2:
            msg = "the step walker fell over"
            raise RuntimeError(msg)
        return real(state, event)

    monkeypatch.setattr("mtgcoach.selfplay.playing.apply", fails)
    played = play(seats(Idle(), Idle()), game(), BOOK, seed=10)
    assert any(problem.kind is Kind.CRASH for problem in played.trouble)
    assert "RuntimeError" in played.trouble[-1].detail
