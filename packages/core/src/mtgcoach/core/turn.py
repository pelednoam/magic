"""Advancing through the steps of a turn.

Separated from the reducer because turn structure is the one part of the rules
that never varies by card, set or format: it is pure sequencing, and it deserves
to be readable on its own.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.results import losses
from mtgcoach.core.steps import Step, next_step

if TYPE_CHECKING:
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState

#: The turn on which the starting player skips their draw step (CR 103.7a).
FIRST_TURN = 1


def advance(state: GameState) -> GameState:
    """Move to the next step, applying that step's turn-based actions.

    Wrapping past cleanup begins the next player's turn. Turn-based actions
    happen automatically and receive no priority, which is exactly why they
    belong here and not in a player-issued event.

    **This is the priority boundary**, so it is where state-based actions are
    checked (CR 704.3). A player at 0 life or who has tried to draw from an
    empty library loses *here* rather than at the moment it happened, which is
    the difference between ending a game correctly and ending it in the middle
    of a combat damage step: damage, deaths and lifelink are one event in the
    rules (CR 510.2), and a check wedged between them would end the game before
    the deaths it caused were applied. When a loss fires, the step does not
    advance -- there is nothing to advance to.

    Raises:
        IllegalEventError: If anything is waiting to resolve. CR 500.2: a step
            ends when the stack is empty and all players pass in succession, so
            a game cannot walk away from a spell it has not resolved. Without
            this the harness would happily carry a cast Opt into the next turn
            and the board would be wrong in a way nothing complained about --
            which is how it stayed wrong for so long the first time.
    """
    finished = losses(state.players)
    if finished is not None:
        return replace(state, over=finished)
    waiting = [card for player in state.players.values() for card in player.stack]
    if waiting:
        names = ", ".join(str(card.instance_id) for card in waiting)
        msg = f"the step cannot end while {names} is waiting to resolve"
        raise IllegalEventError(msg)
    upcoming = next_step(state.step)
    if upcoming is Step.UNTAP:
        state = replace(
            state,
            turn=state.turn + 1,
            active_player=state.opponent_of(state.active_player),
        )
    state = replace(state, step=upcoming)
    return _on_enter(state, upcoming)


def _on_enter(state: GameState, step: Step) -> GameState:
    if step is Step.UNTAP:
        return _untap_step(state)
    if step is Step.DRAW and state.turn != FIRST_TURN:
        return draw_card(state, state.active_player)
    return state


def _untap_step(state: GameState) -> GameState:
    active = state.player(state.active_player)
    return state.with_player(state.active_player, active.begin_turn())


def draw_card(state: GameState, player_id: PlayerId) -> GameState:
    """Move the top card of a library into its owner's hand.

    An empty library is not an error. CR 121.3: a player who attempts to draw
    from one loses the game the next time a player would receive priority --
    they do not fail to draw. This used to raise, with a docstring saying
    losing "arrives with the rules engine in M4"; it has arrived, and the
    difference is not academic. Refusing made decking *unreachable* rather than
    lost, so a game that should have ended with a winner ended with a 400 and
    a tracker still showing a live board.
    """
    player = state.player(player_id)
    if not player.library:
        return state.with_player(player_id, replace(player, drew_from_empty=True))
    top, rest = player.library[0], player.library[1:]
    drawn = replace(player, library=rest, hand=(*player.hand, top))
    return state.with_player(player_id, drawn)
