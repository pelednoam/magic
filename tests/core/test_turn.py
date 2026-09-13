"""Step advancement and turn-based actions."""

from __future__ import annotations

from dataclasses import replace

import pytest
from helpers import ME, YOU, deck

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.movement import add_card
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import TURN_ORDER, Step
from mtgcoach.core.turn import advance, draw_card
from mtgcoach.core.zones import ZoneName


def _advance_to(state: GameState, step: Step) -> GameState:
    for _ in range(len(TURN_ORDER) * 2):
        state = advance(state)
        if state.step is step:
            return state
    msg = f"never reached {step}"
    raise AssertionError(msg)


def test_advance_moves_one_step(game: GameState) -> None:
    assert advance(game).step is Step.UPKEEP


def test_a_full_turn_passes_to_the_other_player(game: GameState) -> None:
    state = game
    for _ in range(len(TURN_ORDER)):
        state = advance(state)
    assert state.step is Step.UNTAP
    assert state.turn == 2
    assert state.active_player == YOU


def test_the_starting_player_skips_their_first_draw(game: GameState) -> None:
    """CR 103.7a. Beginners get this wrong in both directions."""
    before = len(game.player(ME).hand)
    state = _advance_to(game, Step.DRAW)
    assert len(state.player(ME).hand) == before


def test_the_second_player_does_draw_on_turn_two(game: GameState) -> None:
    state = game
    for _ in range(len(TURN_ORDER)):
        state = advance(state)
    before = len(state.player(YOU).hand)
    state = _advance_to(state, Step.DRAW)
    assert len(state.player(YOU).hand) == before + 1


def test_the_untap_step_untaps_only_the_active_player(game: GameState) -> None:
    cards = deck("m")
    state = game
    for player_id in (ME, YOU):
        player = add_card(state.player(player_id), cards[0], ZoneName.BATTLEFIELD)
        state = state.with_player(
            player_id, replace(player, battlefield=(player.battlefield[0].tap(),))
        )

    for _ in range(len(TURN_ORDER)):
        state = advance(state)

    assert state.active_player == YOU
    assert not state.player(YOU).battlefield[0].tapped
    assert state.player(ME).battlefield[0].tapped, "the inactive player stays tapped"


def test_the_untap_step_clears_summoning_sickness(game: GameState) -> None:
    state = game.with_player(YOU, add_card(game.player(YOU), deck("y")[0], ZoneName.BATTLEFIELD))
    assert state.player(YOU).battlefield[0].summoning_sick
    for _ in range(len(TURN_ORDER)):
        state = advance(state)
    assert not state.player(YOU).battlefield[0].summoning_sick


def test_the_untap_step_resets_the_land_drop(game: GameState) -> None:
    state = game.with_player(YOU, replace(game.player(YOU), lands_played_this_turn=1))
    for _ in range(len(TURN_ORDER)):
        state = advance(state)
    assert state.player(YOU).lands_played_this_turn == 0


def test_draw_moves_the_top_card(game: GameState) -> None:
    top = game.player(ME).library[0]
    state = draw_card(game, ME)
    assert state.player(ME).hand[-1] == top
    assert state.player(ME).library[0] != top


def test_drawing_from_an_empty_library_is_refused() -> None:
    state = start_game({ME: deck("m", 7), YOU: deck("y")}, ME)
    with pytest.raises(IllegalEventError, match="empty library"):
        draw_card(state, ME)
