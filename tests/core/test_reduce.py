"""Applying events."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from helpers import ME, YOU, card_id, deck

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import (
    AdvanceStep,
    ChangeLife,
    DrawCard,
    MoveCard,
    PlayLand,
    SetTapped,
)
from mtgcoach.core.ids import InstanceId
from mtgcoach.core.player import STARTING_LIFE
from mtgcoach.core.reduce import apply, replay
from mtgcoach.core.steps import Step
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState


def test_advance_step(game: GameState) -> None:
    assert apply(game, AdvanceStep()).step is Step.UPKEEP


def test_draw_card(game: GameState) -> None:
    top = game.player(ME).library[0]
    assert apply(game, DrawCard(ME)).player(ME).hand[-1] == top


def test_change_life(game: GameState) -> None:
    assert apply(game, ChangeLife(ME, -3)).player(ME).life == STARTING_LIFE - 3
    assert apply(game, ChangeLife(ME, 2)).player(ME).life == STARTING_LIFE + 2


def test_change_life_touches_only_that_player(game: GameState) -> None:
    state = apply(game, ChangeLife(ME, -3))
    assert state.player(YOU).life == STARTING_LIFE


def test_move_card(game: GameState) -> None:
    state = apply(game, MoveCard(ME, card_id("m", 0), ZoneName.GRAVEYARD))
    assert state.player(ME).graveyard == (deck("m")[0],)


def test_play_land(game: GameState) -> None:
    state = apply(game, PlayLand(ME, card_id("m", 0)))
    assert state.player(ME).battlefield[0].instance_id == card_id("m", 0)
    assert state.player(ME).lands_played_this_turn == 1
    assert len(state.player(ME).hand) == 6


def test_a_land_must_be_in_hand(game: GameState) -> None:
    with pytest.raises(IllegalEventError, match=r"not in .* hand"):
        apply(game, PlayLand(ME, card_id("m", 19)))


def test_only_one_land_per_turn(game: GameState) -> None:
    state = apply(game, PlayLand(ME, card_id("m", 0)))
    with pytest.raises(IllegalEventError, match="already played a land"):
        apply(state, PlayLand(ME, card_id("m", 1)))


def test_set_tapped_affects_only_the_named_permanent(game: GameState) -> None:
    """Precedence bug guard: an earlier version tapped the whole battlefield."""
    state = apply(game, MoveCard(ME, card_id("m", 0), ZoneName.BATTLEFIELD))
    state = apply(state, MoveCard(ME, card_id("m", 1), ZoneName.BATTLEFIELD))
    state = apply(state, SetTapped(ME, card_id("m", 0), tapped=True))
    assert [p.tapped for p in state.player(ME).battlefield] == [True, False]


def test_untapping_affects_only_the_named_permanent(game: GameState) -> None:
    state = apply(game, MoveCard(ME, card_id("m", 0), ZoneName.BATTLEFIELD))
    state = apply(state, MoveCard(ME, card_id("m", 1), ZoneName.BATTLEFIELD))
    state = apply(state, SetTapped(ME, card_id("m", 0), tapped=True))
    state = apply(state, SetTapped(ME, card_id("m", 1), tapped=True))
    state = apply(state, SetTapped(ME, card_id("m", 0), tapped=False))
    assert [p.tapped for p in state.player(ME).battlefield] == [False, True]


def test_set_tapped_needs_a_permanent(game: GameState) -> None:
    with pytest.raises(IllegalEventError, match="no permanent"):
        apply(game, SetTapped(ME, InstanceId("nope"), tapped=True))


def test_replay_of_an_empty_log_is_the_starting_position(game: GameState) -> None:
    assert replay(game, []) == game


def test_replay_matches_step_by_step_application(game: GameState) -> None:
    log: list[Event] = [
        PlayLand(ME, card_id("m", 0)),
        ChangeLife(YOU, -3),
        AdvanceStep(),
        SetTapped(ME, card_id("m", 0), tapped=True),
    ]
    stepwise = game
    for event in log:
        stepwise = apply(stepwise, event)
    assert replay(game, log) == stepwise
