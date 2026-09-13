"""Moving cards between zones."""

from __future__ import annotations

from dataclasses import replace

import pytest
from helpers import card_id, deck

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import InstanceId
from mtgcoach.core.movement import add_card, move_card, remove_card
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.player import PlayerState
from mtgcoach.core.zones import ZoneName

CARDS = deck("p", 5)


def _populated() -> PlayerState:
    return PlayerState(
        library=(CARDS[0],),
        hand=(CARDS[1],),
        battlefield=(Permanent(CARDS[2]),),
        graveyard=(CARDS[3],),
        exile=(CARDS[4],),
    )


@pytest.mark.parametrize(
    ("zone", "index"),
    [
        (ZoneName.LIBRARY, 0),
        (ZoneName.HAND, 1),
        (ZoneName.BATTLEFIELD, 2),
        (ZoneName.GRAVEYARD, 3),
        (ZoneName.EXILE, 4),
    ],
)
def test_remove_finds_a_card_in_any_zone(zone: ZoneName, index: int) -> None:
    player, card = remove_card(_populated(), card_id("p", index))
    assert card == CARDS[index]
    assert player.zone(zone) == ()
    assert len(list(player.cards())) == 4


def test_remove_rejects_an_unknown_card() -> None:
    with pytest.raises(IllegalEventError, match="no card"):
        remove_card(_populated(), InstanceId("nope"))


@pytest.mark.parametrize("zone", list(ZoneName))
def test_add_puts_a_card_in_any_zone(zone: ZoneName) -> None:
    empty = PlayerState(library=(), hand=(), battlefield=(), graveyard=(), exile=())
    player = add_card(empty, CARDS[0], zone)
    assert player.zone(zone) == (CARDS[0],)


def test_a_card_entering_the_battlefield_is_summoning_sick() -> None:
    empty = PlayerState(library=(), hand=(), battlefield=(), graveyard=(), exile=())
    player = add_card(empty, CARDS[0], ZoneName.BATTLEFIELD)
    assert player.battlefield[0].summoning_sick
    assert not player.battlefield[0].tapped


def test_move_preserves_the_card_count() -> None:
    player = move_card(_populated(), card_id("p", 1), ZoneName.GRAVEYARD)
    assert len(list(player.cards())) == 5
    assert player.hand == ()
    assert len(player.graveyard) == 2


def test_removing_from_the_battlefield_drops_permanent_state() -> None:
    """A card that leaves the battlefield is a new object when it returns."""
    tapped = replace(_populated(), battlefield=(Permanent(CARDS[2]).tap().settle(),))
    player = move_card(tapped, card_id("p", 2), ZoneName.HAND)
    back = add_card(player, CARDS[2], ZoneName.BATTLEFIELD)
    assert back.battlefield[0].summoning_sick
    assert not back.battlefield[0].tapped
