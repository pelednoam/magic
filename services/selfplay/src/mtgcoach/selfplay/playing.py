"""One whole game, watched at every event.

The loop is deliberately dull. It walks the steps the engine defines, asks the
seat whose turn it is what to do at the two steps where a decision exists, and
applies it. Everything interesting is in what surrounds each transition: the
state before and after go to ``watching.broken``, and anything that raises
becomes a record rather than a traceback, because a season of a thousand games
must not stop at the first one.

Nothing here decides anything about Magic. Where a rule is needed the engine is
asked; where the engine has no answer the game simply does not do that thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.coach.report import advise
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step
from mtgcoach.selfplay import applying, watching
from mtgcoach.selfplay.ending import finished, over_with
from mtgcoach.selfplay.offers import offered, planned
from mtgcoach.selfplay.records import Game, Kind, Reached, Trouble

if TYPE_CHECKING:
    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState
    from mtgcoach.selfplay.moves import Seat

#: Past this, the game is not going to end on its own. Two Beginner Box decks
#: deck out around turn 50; this is well clear of that, and a game that reaches
#: it is a finding rather than a long game.
TURN_CAP = 120

#: The steps a player is asked at. The engine offers a land drop and a cast in
#: either main phase and an attack in exactly one step, so these are every
#: moment a decision exists.
DECISIONS = (Step.PRECOMBAT_MAIN, Step.DECLARE_ATTACKERS, Step.POSTCOMBAT_MAIN)


@dataclass(slots=True)
class Run:
    """What one game accumulates while it is being played.

    A record rather than four locals threaded through every helper: they are
    always passed together, and the helpers that add to it should not be able
    to take one and forget another.
    """

    seed: int
    seats: tuple[Seat, Seat]
    #: The card data, so applying an action can go through the server's own
    #: guard rather than straight to the reducer. Without it the harness
    #: exercised every check in ``core`` and none of the card-aware ones, and
    #: a defect could pass a three-hundred-game season while failing the first
    #: tap in the app.
    catalogue: CardLookup | None = None
    trouble: list[Trouble] = field(default_factory=list[Trouble])
    unknown: set[str] = field(default_factory=set[str])
    events: int = 0
    reached: Reached = field(default_factory=Reached)
    #: Every event this game applied, in order. The record that makes a game
    #: replayable by anything holding `core`: the journal stores it, and the
    #: API rebuilds any moment of it with `reduce.replay` alone.
    log: list[Event] = field(default_factory=list["Event"])

    def also(self, **more: int) -> None:
        """Add to what this game reached."""
        self.reached = self.reached.and_also(Reached(**more))


def play(seats: tuple[Seat, Seat], state: GameState, catalogue: CardLookup, seed: int) -> Game:
    """Play until somebody wins, somebody decks, or the cap is reached."""
    table = {seat.player: seat for seat in seats}
    run = Run(seed=seed, seats=seats, catalogue=catalogue)

    while state.turn <= TURN_CAP:
        report = advise(state, state.active_player, catalogue)
        run.unknown.update(report.unknown)
        run.also(
            triggers=1 if report.reminders else 0,
            biggest_board=max(len(player.battlefield) for player in state.players.values()),
        )
        if state.step in DECISIONS:
            state = _decide(state, table[state.active_player], report, run)
        state, stepped = _stepped(state, run)
        # The engine's own answer, not a second one. This loop used to check
        # life totals itself, outside the game -- so the harness knew a game
        # had ended while the live API path carried on advancing steps. One
        # question must not have two answers, and the engine's is the one a
        # player sees.
        if state.over is not None:
            return finished(run, state, state.over)
        if not stepped:
            return over_with(run, state, None, ending="stuck")

    run.trouble.append(
        Trouble(Kind.STUCK, f"still going after {TURN_CAP} turns", state.turn, state.step)
    )
    return over_with(run, state, None, ending="no end")


def _decide(state: GameState, seat: Seat, report: TurnReport, run: Run) -> GameState:
    """Ask the seat what to do, and do it if the engine allows.

    An agent naming something the engine did not offer is recorded and ignored
    rather than applied: a bad agent must not be able to produce an illegal
    state, or every later finding is its fault rather than the engine's.
    """
    before = state
    try:
        # The agent's own call is inside the guard, not before it. It was
        # outside, and a test of "an agent that raises does not stop the game"
        # found that it did -- the one thing this function promises.
        move = seat.agent.act(state, report, seat.player)
        if move.play is not None:
            card = offered(report, move.play)
            done = applying.played(state, seat.player, card, run.catalogue)
            state = _logged(run, done)
            if card.is_land:
                run.also(lands=1)
            else:
                run.also(spells=1)
        elif move.attack:
            done = applying.attacked(
                state, seat.player, planned(report, move.attack), run.catalogue
            )
            state = _logged(run, done)
            run.also(attacks=1)
    except (IllegalEventError, LookupError) as refused:
        run.trouble.append(Trouble(Kind.REFUSED, str(refused), state.turn, state.step, seat.player))
        return before
    except Exception as crashed:  # noqa: BLE001 - a season must not stop at one game
        run.trouble.append(
            Trouble(
                Kind.CRASH,
                f"{type(crashed).__name__}: {crashed}",
                state.turn,
                state.step,
                seat.player,
            )
        )
        return before
    run.trouble.extend(
        Trouble(Kind.BROKEN, wrong, state.turn, state.step, seat.player)
        for wrong in watching.broken(before, state)
    )
    run.events += 1
    return state


def _stepped(state: GameState, run: Run) -> tuple[GameState, bool]:
    """Advance one step, watching what that did.

    A refusal here used to be how a game ended by decking: the draw step raised
    when the library was empty. It does not any more -- CR 121.3 makes that a
    *loss*, which `advance` records in the state -- so decking now arrives as a
    result rather than as an exception, and the caller reads `state.over`.
    """
    before = state
    try:
        state = apply(state, AdvanceStep())
        run.log.append(AdvanceStep())
    except IllegalEventError:
        return before, False
    except Exception as crashed:  # noqa: BLE001 - see `_decide`
        run.trouble.append(
            Trouble(Kind.CRASH, f"{type(crashed).__name__}: {crashed}", state.turn, state.step)
        )
        return before, False
    run.trouble.extend(
        Trouble(Kind.BROKEN, wrong, state.turn, state.step)
        for wrong in watching.broken(before, state)
    )
    run.events += 1
    return state, True


def _logged(run: Run, done: applying.Applied) -> GameState:
    """Keep what was applied, and hand back where it got to."""
    run.log.extend(done.events)
    return done.state
