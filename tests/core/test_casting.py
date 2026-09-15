"""Casting a spell, and the spell resolving.

Two events rather than one, which is the whole point: CR 601.2a puts the card
on the stack and CR 608 takes it off, and between them is the moment a player
may answer it. Collapsing them into a single "put it on the battlefield" is
what left an Opt sitting among the lands for the rest of a game.

That moment is now something the engine has: a resolution waits until every
player has passed in succession (CR 117.4), so ``resolve`` here goes through
``all_pass`` rather than straight after the cast. A test that resolved without
passing would be pinning the shape the app used to have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helpers import ME, YOU, all_pass
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import CastSpell, ResolveSpell
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.reduce import apply
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.state import GameState


def cast(state: GameState, player: PlayerId = ME) -> tuple[GameState, CardInstance]:
    """Put the first card in a player's hand on the stack."""
    card = state.player(player).hand[0]
    return apply(state, CastSpell(player, card.instance_id)), card


def resolve(state: GameState, card: CardInstance, to: ZoneName, player: PlayerId = ME) -> GameState:
    """Let the top of the stack resolve, the way it actually resolves.

    Both players pass first (CR 117.4). Not decoration: the reducer refuses a
    resolution nobody has passed to, which is the hole the app fell into.
    """
    return apply(all_pass(state), ResolveSpell(player, card.instance_id, to))


def test_a_cast_spell_goes_to_the_stack(main: GameState) -> None:
    """CR 601.2a. Not to the battlefield, and not nowhere."""
    after, card = cast(main)
    assert [one.card for one in after.stack] == [card]
    assert after.stack[0].controller == ME
    assert card not in after.player(ME).hand


def test_a_permanent_spell_becomes_a_permanent(main: GameState) -> None:
    """CR 608.3."""
    on_stack, card = cast(main)
    after = resolve(on_stack, card, ZoneName.BATTLEFIELD)
    assert after.stack == ()
    assert [p.card for p in after.player(ME).battlefield] == [card]


def test_an_instant_goes_to_its_owners_graveyard(main: GameState) -> None:
    """CR 608.2m, and the bug this whole event pair exists to fix.

    An Opt that has resolved is in the graveyard. It is not on the battlefield,
    where it sat for the rest of the game when casting was a `MoveCard`.
    """
    on_stack, card = cast(main)
    after = resolve(on_stack, card, ZoneName.GRAVEYARD)
    assert after.player(ME).graveyard == (card,)
    assert after.player(ME).battlefield == ()
    assert after.stack == ()


def test_a_card_not_in_hand_cannot_be_cast(main: GameState) -> None:
    with pytest.raises(IllegalEventError, match="is not in"):
        apply(main, CastSpell(ME, InstanceId("nobody")))


def test_a_card_already_on_the_battlefield_cannot_be_cast(main: GameState) -> None:
    """Casting reads from hand. A permanent is already past that."""
    on_stack, card = cast(main)
    down = resolve(on_stack, card, ZoneName.BATTLEFIELD)
    with pytest.raises(IllegalEventError, match="is not in"):
        apply(down, CastSpell(ME, card.instance_id))


def test_a_spell_not_on_the_stack_cannot_resolve(main: GameState) -> None:
    card = main.player(ME).hand[0]
    with pytest.raises(IllegalEventError, match="is not on the stack"):
        apply(all_pass(main), ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))


def test_one_player_cannot_resolve_the_others_spell(main: GameState) -> None:
    """The stack is shared, so being able to *see* it is not being able to take it.

    This used to read "one player's spell is not on the other's stack", which
    was true of the old per-player zone and is not a rule: the stack is one
    public zone (CR 405.1) and both players can see every spell on it. What
    stops a seat resolving somebody else's spell is that they do not control it
    (CR 405.4), which is a different sentence and the right one.
    """
    on_stack, card = cast(main)
    passed = all_pass(on_stack)
    with pytest.raises(IllegalEventError, match="not 'you''s to resolve"):
        apply(passed, ResolveSpell(YOU, card.instance_id, ZoneName.GRAVEYARD))


@pytest.mark.parametrize("zone", [ZoneName.HAND, ZoneName.LIBRARY, ZoneName.EXILE])
def test_a_spell_resolves_to_two_places_and_no_others(main: GameState, zone: ZoneName) -> None:
    """CR 608.2m and 608.3 are the only two outcomes of resolving normally.

    A spell that exiles itself does so as part of its own effect, before 608.2m
    looks for it, and the engine models no card effects yet -- so anything else
    is a caller that is confused, and a confused caller must not be able to put
    a resolved Opt back in its owner's library.

    The stack used to be in this list, back when it was one of a player's own
    zones. It is not one any more, so ``move_card`` cannot name it and neither
    can the wire: putting a card on the stack is casting it.
    """
    on_stack, card = cast(main)
    with pytest.raises(IllegalEventError, match="a spell resolves to the"):
        apply(all_pass(on_stack), ResolveSpell(ME, card.instance_id, zone))


def test_cards_are_conserved_across_a_cast(main: GameState) -> None:
    """The invariant a season checks on every event, asserted here directly.

    Asked of ``cards_of`` rather than ``PlayerState.cards``: a spell on the
    stack is in a zone the two players share, and the count that matters is
    still the count *per player*.
    """
    before = sorted(str(card.instance_id) for card in main.cards_of(ME))
    on_stack, card = cast(main)
    assert sorted(str(one.instance_id) for one in on_stack.cards_of(ME)) == before
    after = resolve(on_stack, card, ZoneName.GRAVEYARD)
    assert sorted(str(one.instance_id) for one in after.cards_of(ME)) == before
