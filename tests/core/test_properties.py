"""Invariants that must hold over arbitrary play.

Example-based tests check the cases I thought of. These check the ones I did
not: Hypothesis drives random legal play and asserts the properties the whole
design rests on -- above all that a game is exactly its starting position plus
its event log, which is what makes undo, replay and end-of-game review exact
rather than approximate.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from helpers import ME, YOU, all_pass, deck
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import (
    AdvanceStep,
    CastSpell,
    ChangeLife,
    DrawCard,
    MoveCard,
    PassPriority,
    PlayLand,
    ResolveSpell,
    SetTapped,
)
from mtgcoach.core.reduce import apply, replay
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import TURN_ORDER
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.events import Event
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState

#: Long enough to cross several turn boundaries and empty a library or two.
PLAY_LENGTH = 40

LIFE_SWING = 5


def _new_game() -> GameState:
    return start_game({ME: deck("m"), YOU: deck("y")}, ME)


def _event_strategy(state: GameState) -> st.SearchStrategy[Event]:
    """Events plausible in ``state``. Illegal ones are welcome and expected.

    The strategy deliberately proposes events that the reducer will refuse --
    a second land drop, a draw from an empty library -- because the refusal path
    has to preserve the invariants too.
    """
    players = st.sampled_from(list(state.players))
    choices: list[st.SearchStrategy[Event]] = [
        st.just(AdvanceStep()),
        # From either seat, on purpose: a pass by the player who does not hold
        # priority has to be refused, and the refusal path has to preserve the
        # invariants like every other.
        st.builds(PassPriority, players),
        st.builds(DrawCard, players),
        st.builds(ChangeLife, players, st.integers(-LIFE_SWING, LIFE_SWING)),
    ]
    for player_id, player in state.players.items():
        owned = [card.instance_id for card in state.cards_of(player_id)]
        if owned:
            choices.append(
                st.builds(
                    MoveCard,
                    st.just(player_id),
                    st.sampled_from(owned),
                    st.sampled_from(list(ZoneName)),
                )
            )
        if player.hand:
            in_hand = st.sampled_from([c.instance_id for c in player.hand])
            choices.append(st.builds(PlayLand, st.just(player_id), in_hand))
            # No payment: the reducer does not know what a spell costs, so a
            # free cast is legal there and `api.guard` is what refuses it.
            # Casting is what puts anything on the stack, so without this the
            # stack invariants above would never see a non-empty one.
            choices.append(st.builds(CastSpell, st.just(player_id), in_hand))
        if state.stack:
            choices.append(
                st.builds(
                    ResolveSpell,
                    st.just(player_id),
                    st.sampled_from([one.instance_id for one in state.stack]),
                    st.sampled_from(list(ZoneName)),
                )
            )
        if player.battlefield:
            choices.append(
                st.builds(
                    SetTapped,
                    st.just(player_id),
                    st.sampled_from([p.instance_id for p in player.battlefield]),
                    st.booleans(),
                )
            )
    return st.one_of(*choices)


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(st.data())
def test_invariants_hold_over_arbitrary_play(data: st.DataObject) -> None:
    initial = _new_game()
    state = initial
    accepted: list[Event] = []
    total_cards = len(list(initial.cards()))

    for _ in range(PLAY_LENGTH):
        event = data.draw(_event_strategy(state))
        before = copy.deepcopy(state)

        try:
            nxt = apply(state, event)
        except IllegalEventError:
            assert state == before, "a refused event must leave the state untouched"
            continue

        assert state == before, "apply must not mutate its input"
        assert len(list(nxt.cards())) == total_cards, "cards were created or destroyed"
        for one in nxt.stack:
            assert one.card in list(nxt.cards_of(one.controller)), (
                "a spell on the stack must still count among its controller's cards"
            )
        assert nxt.turn >= state.turn, "the turn counter must not run backwards"
        if nxt.turn != state.turn:
            assert nxt.active_player != state.active_player, (
                "a new turn must belong to the other player"
            )
        assert nxt.step in TURN_ORDER

        accepted.append(event)
        state = nxt

    assert replay(initial, accepted) == state, (
        "replaying the log must reproduce the state it produced"
    )


@settings(max_examples=25, deadline=None)
@given(st.integers(min_value=0, max_value=len(TURN_ORDER) - 1))
def test_a_full_cycle_from_any_step_advances_exactly_one_turn(offset: int) -> None:
    """Whichever step you start from, twelve advances is one turn, not two."""
    state = _new_game()
    for _ in range(offset):
        state = _ended(state)

    start_turn, start_player = state.turn, state.active_player
    for _ in range(len(TURN_ORDER)):
        state = _ended(state)

    assert state.turn == start_turn + 1
    assert state.active_player != start_player


def _ended(state: GameState) -> GameState:
    """End the current step the way CR 500.2 ends it: all pass, then advance.

    A bare ``AdvanceStep`` is refused now, and a property test that reached for
    one was leaning on the very gap this engine has closed.
    """
    return apply(all_pass(state), AdvanceStep())


@settings(max_examples=25, deadline=None)
@given(st.lists(st.sampled_from([ME, YOU]), max_size=10))
def test_life_changes_commute(players: list[PlayerId]) -> None:
    """Life is a running total; the order of independent changes cannot matter."""
    forwards = replay(_new_game(), [ChangeLife(p, -1) for p in players])
    backwards = replay(_new_game(), [ChangeLife(p, -1) for p in reversed(players)])
    assert forwards == backwards
