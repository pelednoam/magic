"""Step advancement and turn-based actions."""

from __future__ import annotations

from dataclasses import replace

from helpers import ME, YOU, deck
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


def test_drawing_from_an_empty_library_loses_rather_than_failing() -> None:
    """CR 121.3, and the old test had this backwards.

    It asserted a refusal, on a docstring saying losing "arrives with the rules
    engine in M4". The difference is not academic: refusing made decking
    *unreachable* rather than lost, so a game that should have ended with a
    winner ended with a 400 and a tracker still showing a live board.

    The loss itself comes at the next priority, which is ``advance``. Here the
    attempt is simply remembered.
    """
    state = start_game({ME: deck("m", 7), YOU: deck("y")}, ME)
    tried = draw_card(state, ME)
    assert tried.player(ME).drew_from_empty
    assert tried.over is None, "the loss is a state-based action, not immediate"


def test_the_attempted_draw_loses_the_game_at_the_next_priority() -> None:
    """CR 704.5b. One step later, not one event later."""
    state = start_game({ME: deck("m", 7), YOU: deck("y")}, ME)
    finished = advance(draw_card(state, ME))
    assert finished.over is not None
    assert [one.player for one in finished.over.lost] == [ME]
    assert finished.over.winner(finished.players) == YOU


def test_a_player_at_zero_life_loses_at_the_next_priority() -> None:
    """CR 704.5a. The tracker used to carry on advancing steps instead."""
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    state = state.with_player(ME, replace(state.player(ME), life=0))
    finished = advance(state)
    assert finished.over is not None
    assert [one.player for one in finished.over.lost] == [ME]
    assert finished.step is state.step, "a finished game does not advance"


def test_both_players_out_at_once_is_a_draw() -> None:
    """CR 104.4b, rather than a win for whoever is listed first."""
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    for seat in (ME, YOU):
        state = state.with_player(seat, replace(state.player(seat), life=-1))
    finished = advance(state)
    assert finished.over is not None
    assert finished.over.drawn
    assert finished.over.winner(finished.players) is None
