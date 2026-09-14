"""Getting from two deck names to a game that can be played.

The engine never generates randomness, which is what makes a game a pure
function of its libraries and its events. So the shuffle happens here, from a
seed -- and these are mostly about that: the same seed must give the same
game, or a season that finds something cannot be run again to see it.
"""

from __future__ import annotations

import pytest

from mtgcoach.core.ids import OracleId
from mtgcoach.selfplay.dealing import THEM, YOU, dealt, libraries

DECKS = {
    "forests": tuple(OracleId("Forest") for _ in range(40)),
    "bears": tuple(OracleId("Grizzly Bears") for _ in range(40)),
}


def test_the_same_seed_deals_the_same_game() -> None:
    """The whole point of seeding it here rather than in the engine."""
    assert libraries(DECKS, ("forests", "bears"), 5) == libraries(DECKS, ("forests", "bears"), 5)


def test_a_different_seed_deals_a_different_game() -> None:
    one = libraries(DECKS, ("forests", "bears"), 1)[YOU]
    two = libraries(DECKS, ("forests", "bears"), 2)[YOU]
    assert one != two, "40 cards shuffled two ways"


def test_every_card_gets_its_own_identity() -> None:
    """Two copies share an oracle id and never an instance id.

    That is what lets the state tell "the Forest you tapped" from the other.
    """
    made = libraries(DECKS, ("forests", "bears"), 0)
    ids = [card.instance_id for card in made[YOU]]
    assert len(set(ids)) == len(ids)


def test_the_two_seats_do_not_share_identities() -> None:
    made = libraries(DECKS, ("forests", "bears"), 0)
    assert not {card.instance_id for card in made[YOU]} & {card.instance_id for card in made[THEM]}


def test_a_deck_nobody_has_is_refused() -> None:
    with pytest.raises(KeyError):
        libraries(DECKS, ("forests", "dragons"), 0)


def test_who_goes_first_alternates_with_the_seed() -> None:
    """Going first is a real asymmetry: they skip a draw.

    A season where one seat always went first would test half of it.
    """
    assert dealt(DECKS, ("forests", "bears"), 0).active_player == YOU
    assert dealt(DECKS, ("forests", "bears"), 1).active_player == THEM


def test_a_dealt_game_has_two_opening_hands() -> None:
    state = dealt(DECKS, ("forests", "bears"), 0)
    assert len(state.player(YOU).hand) == 7
    assert len(state.player(THEM).hand) == 7
    assert state.turn == 1
