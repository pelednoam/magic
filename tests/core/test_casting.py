"""Casting a spell, and the spell resolving.

Two events rather than one, which is the whole point: CR 601.2a puts the card
on the stack and CR 608 takes it off, and between them is the moment a player
may answer it. Collapsing them into a single "put it on the battlefield" is
what left an Opt sitting among the lands for the rest of a game.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helpers import ME, YOU
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep, CastSpell, ResolveSpell
from mtgcoach.core.ids import InstanceId
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.state import GameState


def cast(state: GameState) -> tuple[GameState, CardInstance]:
    """Put the first card in ME's hand on the stack."""
    card = state.player(ME).hand[0]
    return apply(state, CastSpell(ME, card.instance_id)), card


def test_a_cast_spell_goes_to_the_stack(game: GameState) -> None:
    """CR 601.2a. Not to the battlefield, and not nowhere."""
    after, card = cast(game)
    assert after.player(ME).stack == (card,)
    assert card not in after.player(ME).hand


def test_a_permanent_spell_becomes_a_permanent(game: GameState) -> None:
    """CR 608.3."""
    on_stack, card = cast(game)
    after = apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.BATTLEFIELD))
    assert after.player(ME).stack == ()
    assert [p.card for p in after.player(ME).battlefield] == [card]


def test_an_instant_goes_to_its_owners_graveyard(game: GameState) -> None:
    """CR 608.2m, and the bug this whole event pair exists to fix.

    An Opt that has resolved is in the graveyard. It is not on the battlefield,
    where it sat for the rest of the game when casting was a `MoveCard`.
    """
    on_stack, card = cast(game)
    after = apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    assert after.player(ME).graveyard == (card,)
    assert after.player(ME).battlefield == ()
    assert after.player(ME).stack == ()


def test_a_card_not_in_hand_cannot_be_cast(game: GameState) -> None:
    with pytest.raises(IllegalEventError, match="is not in"):
        apply(game, CastSpell(ME, InstanceId("nobody")))


def test_a_card_already_on_the_battlefield_cannot_be_cast(game: GameState) -> None:
    """Casting reads from hand. A permanent is already past that."""
    on_stack, card = cast(game)
    down = apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.BATTLEFIELD))
    with pytest.raises(IllegalEventError, match="is not in"):
        apply(down, CastSpell(ME, card.instance_id))


def test_a_spell_not_on_the_stack_cannot_resolve(game: GameState) -> None:
    card = game.player(ME).hand[0]
    with pytest.raises(IllegalEventError, match="is not on"):
        apply(game, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))


def test_one_players_spell_is_not_on_the_others_stack(game: GameState) -> None:
    """The zone is per-player, so a seat cannot resolve somebody else's spell."""
    on_stack, card = cast(game)
    with pytest.raises(IllegalEventError, match="is not on"):
        apply(on_stack, ResolveSpell(YOU, card.instance_id, ZoneName.GRAVEYARD))


@pytest.mark.parametrize("zone", [ZoneName.HAND, ZoneName.LIBRARY, ZoneName.EXILE, ZoneName.STACK])
def test_a_spell_resolves_to_two_places_and_no_others(game: GameState, zone: ZoneName) -> None:
    """CR 608.2m and 608.3 are the only two outcomes of resolving normally.

    A spell that exiles itself does so as part of its own effect, before 608.2m
    looks for it, and the engine models no card effects yet -- so anything else
    is a caller that is confused, and a confused caller must not be able to put
    a resolved Opt back in its owner's library.
    """
    on_stack, card = cast(game)
    with pytest.raises(IllegalEventError, match="a spell resolves to the"):
        apply(on_stack, ResolveSpell(ME, card.instance_id, zone))


def test_cards_are_conserved_across_a_cast(game: GameState) -> None:
    """The invariant a season checks on every event, asserted here directly."""
    before = sorted(str(card.instance_id) for card in game.player(ME).cards())
    on_stack, card = cast(game)
    assert sorted(str(one.instance_id) for one in on_stack.player(ME).cards()) == before
    after = apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    assert sorted(str(one.instance_id) for one in after.player(ME).cards()) == before


def test_a_spell_waiting_to_resolve_is_still_there_next_step(game: GameState) -> None:
    """Nothing about advancing the turn clears the stack.

    True of the rules -- a spell resolves because somebody let it, not because
    time passed -- and worth pinning, because ``begin_turn`` rebuilds the
    battlefield and could as easily have rebuilt this.
    """
    on_stack, card = cast(game)
    later = on_stack
    while later.step is not Step.END_STEP:
        later = apply(later, AdvanceStep())
    assert later.player(ME).stack == (card,)
