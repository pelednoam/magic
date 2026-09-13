"""Game construction and whole-state accessors."""

from __future__ import annotations

import pytest

from helpers import ME, YOU, deck
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import PlayerId
from mtgcoach.core.player import OPENING_HAND_SIZE, PlayerState
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step


def test_a_new_game_starts_at_untap_on_turn_one(game: GameState) -> None:
    assert game.turn == 1
    assert game.step is Step.UNTAP
    assert game.active_player == ME


def test_both_players_draw_an_opening_hand(game: GameState) -> None:
    for player_id in (ME, YOU):
        player = game.player(player_id)
        assert len(player.hand) == OPENING_HAND_SIZE
        assert len(player.library) == len(deck("m")) - OPENING_HAND_SIZE


def test_the_opening_hand_comes_off_the_top(game: GameState) -> None:
    """The caller shuffles; the engine deals off the top deterministically."""
    assert game.player(ME).hand == deck("m")[:OPENING_HAND_SIZE]
    assert game.player(ME).library == deck("m")[OPENING_HAND_SIZE:]


def test_player_rejects_an_unknown_id(game: GameState) -> None:
    with pytest.raises(IllegalEventError, match="no such player"):
        game.player(PlayerId("nobody"))


def test_with_player_replaces_only_that_player(game: GameState) -> None:
    empty = PlayerState(library=(), hand=(), battlefield=(), graveyard=(), exile=())
    updated = game.with_player(ME, empty)
    assert updated.player(ME) == empty
    assert updated.player(YOU) == game.player(YOU)
    assert game.player(ME) != empty, "the original must be unchanged"


def test_opponent_of(game: GameState) -> None:
    assert game.opponent_of(ME) == YOU
    assert game.opponent_of(YOU) == ME


def test_opponent_of_rejects_an_unknown_id(game: GameState) -> None:
    with pytest.raises(IllegalEventError, match="no such player"):
        game.opponent_of(PlayerId("nobody"))


def test_cards_spans_both_players(game: GameState) -> None:
    assert len(list(game.cards())) == 2 * len(deck("m"))


def test_a_game_needs_exactly_two_players() -> None:
    with pytest.raises(ValueError, match="exactly 2 players"):
        start_game({ME: deck("m")}, ME)


def test_the_first_player_must_be_in_the_game() -> None:
    with pytest.raises(ValueError, match="not in the game"):
        start_game({ME: deck("m"), YOU: deck("y")}, PlayerId("nobody"))


def test_a_library_must_cover_the_opening_hand() -> None:
    with pytest.raises(ValueError, match="at least 7 cards"):
        start_game({ME: deck("m", 6), YOU: deck("y")}, ME)
