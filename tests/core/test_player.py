"""One player's zones."""

from __future__ import annotations

from dataclasses import replace

import pytest

from helpers import card_id, deck
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.player import PlayerState
from mtgcoach.core.zones import ZoneName


def _populated() -> PlayerState:
    cards = deck("p", 5)
    return PlayerState(
        library=(cards[0],),
        hand=(cards[1],),
        battlefield=(Permanent(cards[2]),),
        graveyard=(cards[3],),
        exile=(cards[4],),
    )


def test_defaults() -> None:
    player = PlayerState(library=(), hand=(), battlefield=(), graveyard=(), exile=())
    assert player.life == 20
    assert player.lands_played_this_turn == 0


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
def test_every_zone_is_reachable(zone: ZoneName, index: int) -> None:
    """A zone missing from the match would be unreachable and untestable."""
    assert _populated().zone(zone) == (deck("p", 5)[index],)


def test_cards_yields_every_zone() -> None:
    assert len(list(_populated().cards())) == 5


def test_find_locates_a_card() -> None:
    found = _populated().find(ZoneName.HAND, card_id("p", 1))
    assert found == CardInstance(card_id("p", 1), OracleId("forest"))


def test_find_returns_none_when_absent() -> None:
    assert _populated().find(ZoneName.HAND, InstanceId("nope")) is None


def test_find_does_not_search_other_zones() -> None:
    assert _populated().find(ZoneName.HAND, card_id("p", 0)) is None


def test_begin_turn_untaps_and_settles() -> None:
    cards = deck("p", 2)
    player = PlayerState(
        library=(),
        hand=(),
        battlefield=(Permanent(cards[0]).tap(), Permanent(cards[1])),
        graveyard=(),
        exile=(),
    )
    untapped = player.begin_turn()
    assert [p.tapped for p in untapped.battlefield] == [False, False]
    assert [p.summoning_sick for p in untapped.battlefield] == [False, False]


def test_begin_turn_resets_the_land_drop() -> None:
    player = replace(_populated(), lands_played_this_turn=1)
    assert player.begin_turn().lands_played_this_turn == 0
