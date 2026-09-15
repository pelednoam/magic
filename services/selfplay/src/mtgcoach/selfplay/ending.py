"""Turning a finished game into the record a season keeps.

Split from ``playing`` at the line limit. The seam is between playing a game
and writing down what happened in it, which are different jobs -- and this half
is where the engine's own verdict is read rather than a second one invented.

That mattered: this loop used to check life totals itself, outside the game, so
the harness knew a game had ended while the live API path carried on advancing
steps. One question must not have two answers, and the engine's is the one a
player sees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.results import Loss
from mtgcoach.selfplay.records import Game

if TYPE_CHECKING:
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.results import Over
    from mtgcoach.core.state import GameState
    from mtgcoach.selfplay.playing import Run


def finished(run: Run, state: GameState, over: Over) -> Game:
    """A game the engine has declared over, as a record.

    ``ending`` comes from the engine's reason rather than being inferred, so
    "decked" means CR 704.5b fired and not "the harness guessed".
    """
    reasons = {one.why for one in over.lost}
    ending = "decked" if Loss.EMPTY_LIBRARY in reasons else "life"
    if over.drawn:
        ending = "draw"
    return over_with(run, state, None, ending=ending, winner=over.winner(state.players))


def over_with(
    run: Run,
    state: GameState,
    dead: PlayerId | None,
    ending: str = "life",
    winner: PlayerId | None = None,
) -> Game:
    """Everything that happened, as a record."""
    return Game(
        seed=run.seed,
        decks=(run.seats[0].deck, run.seats[1].deck),
        turns=state.turn,
        winner=winner if dead is None else state.opponent_of(dead),
        ending=ending,
        trouble=tuple(run.trouble),
        unknown=tuple(sorted(run.unknown)),
        events=run.events,
        log=tuple(run.log),
        reached=run.reached,
    )
