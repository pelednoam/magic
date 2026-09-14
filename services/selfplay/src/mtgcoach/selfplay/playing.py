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
from mtgcoach.selfplay.records import Game, Kind, Trouble

if TYPE_CHECKING:
    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.coach.report import Playable, TurnReport
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.ids import InstanceId, PlayerId
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
    trouble: list[Trouble] = field(default_factory=list[Trouble])
    unknown: set[str] = field(default_factory=set[str])
    events: int = 0


def play(seats: tuple[Seat, Seat], state: GameState, catalogue: CardLookup, seed: int) -> Game:
    """Play until somebody wins, somebody decks, or the cap is reached."""
    table = {seat.player: seat for seat in seats}
    run = Run(seed=seed, seats=seats)

    while state.turn <= TURN_CAP:
        report = advise(state, state.active_player, catalogue)
        run.unknown.update(report.unknown)
        if state.step in DECISIONS:
            state = _decide(state, table[state.active_player], report, run)
        dead = _dead(state)
        if dead is not None:
            return _over(run, state, dead)
        state, stepped = _stepped(state, run)
        if not stepped:
            return _over(run, state, None, ending="decked")

    run.trouble.append(
        Trouble(Kind.STUCK, f"still going after {TURN_CAP} turns", state.turn, state.step)
    )
    return _over(run, state, None, ending="no end")


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
            state = applying.played(state, seat.player, _offered(report, move.play))
        elif move.attack:
            state = applying.attacked(state, seat.player, _planned(report, move.attack))
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

    A refusal here is how a game ends by decking: the draw step raises when the
    library is empty, which is the rules working rather than anything wrong.
    """
    before = state
    try:
        state = apply(state, AdvanceStep())
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


def _dead(state: GameState) -> PlayerId | None:
    """The player who has lost on life, if there is one."""
    return next((pid for pid, player in state.players.items() if player.life <= 0), None)


def _offered(report: TurnReport, instance: InstanceId) -> Playable:
    """The playable card the agent named.

    Raises:
        LookupError: If the agent named something that is not in hand or not
            playable. Recorded as trouble by the caller, which is the point --
            for Claude it means the coach recommended a card the engine did
            not offer.
    """
    found = next((card for card in report.playable if card.instance_id == instance), None)
    if found is None:
        msg = f"{instance} is not a playable card this turn"
        raise LookupError(msg)
    return found


def _planned(report: TurnReport, attackers: tuple[InstanceId, ...]) -> Plan:
    """The engine's plan for exactly these attackers.

    Raises:
        LookupError: If no plan matches. The harness applies the *engine's*
            outcome, so an attack it never costed has no numbers to apply --
            and an agent inventing one is exactly what ``advice.verify``
            refuses on the player's behalf.
    """
    wanted = set(attackers)
    for plan in report.attacks.plans:
        if {creature.instance_id for creature in plan.attackers} == wanted:
            return plan
    msg = f"no costed attack with exactly {sorted(wanted)}"
    raise LookupError(msg)


def _over(run: Run, state: GameState, dead: PlayerId | None, ending: str = "life") -> Game:
    """Everything that happened, as a record."""
    return Game(
        seed=run.seed,
        decks=(run.seats[0].deck, run.seats[1].deck),
        turns=state.turn,
        winner=state.opponent_of(dead) if dead is not None else None,
        ending=ending,
        trouble=tuple(run.trouble),
        unknown=tuple(sorted(run.unknown)),
        events=run.events,
    )
