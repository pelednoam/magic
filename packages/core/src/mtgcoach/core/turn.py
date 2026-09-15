"""Advancing through the steps of a turn.

Separated from the reducer because turn structure is the one part of the rules
that never varies by card, set or format: it is pure sequencing, and it deserves
to be readable on its own.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from mtgcoach.core import priority
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.results import losses
from mtgcoach.core.steps import Step, has_priority, named, next_step

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

    Whether the step may end at all is ``_may_end`` below: both halves of
    CR 500.2, an empty stack *and* every player having passed in succession.
    The second half was missing for as long as there was no pass to record, so
    a client could advance straight past the other player's only window to
    answer a spell.

    Priority is handed out last, after the new step's turn-based actions, which
    is the order CR 117.3a and CR 117.2c give: those are dealt with before a
    player would receive priority, not after.

    Raises:
        IllegalEventError: If the step cannot end yet.
    """
    finished = losses(state.players)
    if finished is not None:
        return replace(state, over=finished)
    _may_end(state)
    upcoming = next_step(state.step)
    if upcoming is Step.UNTAP:
        state = replace(
            state,
            turn=state.turn + 1,
            active_player=state.opponent_of(state.active_player),
        )
    state = replace(state, step=upcoming)
    return priority.begins(_on_enter(state, upcoming))


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


def _may_end(state: GameState) -> None:
    """Refuse a step that is not over yet.

    Here rather than in ``priority``, though it is priority it reads: when a
    step ends is turn structure, and this is the module that owns the turn.
    ``priority`` answers what a *player* may do; this answers what the *clock*
    may do, and only ``advance`` ever needs it.

    CR 500.3 first: the untap step and the cleanup step end when their actions
    are done, and no player receives priority to hold them open.

    Then CR 500.2, both halves of it. The stack has to be empty -- a game
    cannot walk away from a spell it has not resolved, and without that check
    the harness carried a cast Opt into the next turn and nothing complained.
    And every player has to have passed in succession: simply having the stack
    become empty does not end a step, because each player gets a chance to add
    something to it first. That second half was missing, which is why a client
    could advance past the other player's only window to answer.

    Raises:
        IllegalEventError: If the step cannot end.
    """
    if not has_priority(state.step):
        return
    if state.stack:
        names = ", ".join(str(one.instance_id) for one in state.stack)
        msg = f"the step cannot end while {names} is waiting to resolve"
        raise IllegalEventError(msg)
    if not priority.all_passed(state):
        waiting = ", ".join(str(player) for player in priority.yet_to_pass(state))
        msg = f"the {named(state.step)} does not end until {waiting} passes"
        raise IllegalEventError(msg)
