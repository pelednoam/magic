"""Who the attacker chooses to kill, and whose creature is whose.

Both are cases where the engine used to take its answer from the order a caller
happened to build a list in.
"""

from __future__ import annotations

from helpers import creature
from mtgcoach.core.combat.search import best_defence

STARTING_LIFE = 20


def test_the_attacker_chooses_which_blocker_to_kill() -> None:
    """Three damage among a 3/3 and a 1/1 kills one. It should be the 3/3."""
    attacker = creature("Brute", 3, 3)
    big, small = creature("Ogre", 3, 3), creature("Squire", 1, 1)
    for order in ([big, small], [small, big]):
        outcome = best_defence([attacker], order, 1)
        assert outcome.blockers_lost == ("Ogre",)


def test_the_advice_does_not_depend_on_the_order_of_the_blocker_list() -> None:
    """The same board must coach the same way whichever way it is passed in."""
    attackers = [creature("Brute", 3, 3)]
    a, b = creature("Ogre", 3, 3), creature("Squire", 1, 1)
    assert best_defence(attackers, [a, b], 20) == best_defence(attackers, [b, a], 20)


def test_a_single_blocker_has_only_one_order() -> None:
    outcome = best_defence([creature("Brute", 4, 4)], [creature("Squire", 1, 1)], 1)
    assert outcome.blockers_lost == ("Squire",)


# --- two copies of a card are two creatures ---------------------------------


def test_two_copies_of_a_card_are_two_separate_creatures() -> None:
    """Deriving identity from the name made damage on one kill both."""
    twins = [creature("Bear", 2, 2), creature("Bear", 2, 2)]
    outcome = best_defence(twins, [creature("Squire", 1, 1)], 20)
    assert outcome.damage_to_defender == 4
    assert len({c.instance_id for c in twins}) == 2
