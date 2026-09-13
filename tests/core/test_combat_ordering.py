"""Who the attacker chooses to kill, and whose creature is whose.

Both are cases where the engine used to take its answer from the order a caller
happened to build a list in.
"""

from __future__ import annotations

import pytest

from helpers import creature, facts
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import Blocks, Creature
from mtgcoach.core.combat.search import best_defence
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent

STARTING_LIFE = 20


def test_the_attacker_chooses_which_blocker_to_kill() -> None:
    """Three damage among a 3/3 and a 1/1 kills one. It should be the 3/3."""
    attacker = creature("Brute", 3, 3)
    big, small = creature("Ogre", 3, 3), creature("Squire", 1, 1)
    for order in ([big, small], [small, big]):
        outcome = best_defence([attacker], order, 1)
        assert outcome.blocker_names == ("Ogre",)


def test_the_advice_does_not_depend_on_the_order_of_the_blocker_list() -> None:
    """The same board must coach the same way whichever way it is passed in."""
    attackers = [creature("Brute", 3, 3)]
    a, b = creature("Ogre", 3, 3), creature("Squire", 1, 1)
    assert best_defence(attackers, [a, b], 20) == best_defence(attackers, [b, a], 20)


def test_a_single_blocker_has_only_one_order() -> None:
    outcome = best_defence([creature("Brute", 4, 4)], [creature("Squire", 1, 1)], 1)
    assert outcome.blocker_names == ("Squire",)


# --- two copies of a card are two creatures ---------------------------------


def test_two_copies_of_a_card_are_two_separate_creatures() -> None:
    """Deriving identity from the name made damage on one kill both."""
    twins = [creature("Bear", 2, 2), creature("Bear", 2, 2)]
    outcome = best_defence(twins, [creature("Squire", 1, 1)], 20)
    assert outcome.damage_to_defender == 4
    assert len({c.instance_id for c in twins}) == 2


# --- life gained is part of the answer --------------------------------------


def test_the_defender_takes_the_free_point_of_life() -> None:
    """Two blocks that differ only in a lifelinker are not equal.

    Ranking on damage alone tied them exactly, so the defender declined a free
    point whenever the caller listed the other blocker first.
    """
    attacker = creature("Bear", 2, 4)
    cleric = creature("Cleric", 1, 3, "Lifelink")
    guard = creature("Guard", 1, 3)
    for order in ([cleric, guard], [guard, cleric]):
        outcome = best_defence([attacker], order, STARTING_LIFE)
        assert outcome.defender_life_gained == 1
        assert not outcome.blockers_lost


def test_the_attacker_prefers_the_assignment_that_gains_it_life() -> None:
    attacker = creature("Vampire", 3, 3, "Lifelink")
    outcome = best_defence([attacker], [creature("Wall", 0, 5)], STARTING_LIFE)
    assert outcome.attacker_life_gained == 3


def test_best_defence_refuses_a_creature_with_no_fixed_power() -> None:
    """It is public and directly callable, so the guard cannot live in `plans`."""
    star = Creature(
        Permanent(CardInstance(InstanceId("ca"), OracleId("ca"))).settle(),
        facts("Consuming Aberration", creature=True),
    )
    with pytest.raises(ValueError, match="no fixed power"):
        best_defence([star], [], STARTING_LIFE)


def test_best_defence_refuses_an_unknown_blocker_too() -> None:
    star = Creature(
        Permanent(CardInstance(InstanceId("ca"), OracleId("ca"))).settle(),
        facts("Consuming Aberration", creature=True),
    )
    with pytest.raises(ValueError, match="no fixed power"):
        best_defence([creature("Bear", 2, 2)], [star], STARTING_LIFE)


def test_one_permanent_cannot_be_in_a_combat_twice() -> None:
    """Damage is marked by identity, so a repeat fights itself.

    Its damage is doubled and so is what kills it -- the same caller bug the
    mana solver refuses for two sources sharing an identifier.
    """
    bear = creature("Bear", 2, 2)
    with pytest.raises(ValueError, match="cannot be in it twice"):
        best_defence([bear, bear], [], STARTING_LIFE)


def test_resolve_refuses_it_too() -> None:
    """It is public, so it asks -- which it was not doing."""
    bear = creature("Bear", 2, 2)
    with pytest.raises(ValueError, match="cannot be in it twice"):
        resolve([bear, bear], Blocks(), STARTING_LIFE)


def test_resolve_refuses_an_unknown_power() -> None:
    star = Creature(
        Permanent(CardInstance(InstanceId("ca"), OracleId("ca"))).settle(),
        facts("Consuming Aberration", creature=True),
    )
    with pytest.raises(ValueError, match="no fixed power"):
        resolve([star], Blocks(), STARTING_LIFE)


def test_damage_with_nowhere_to_go_still_lands_on_a_blocker() -> None:
    """An attacker without trample assigns all of it among its blockers.

    When every blocker already had lethal marked, nothing was assigned at all
    and the damage vanished -- taking a lifelinker's life gain with it.
    """
    vampire = creature("Vampire", 3, 3, "Lifelink", "Double strike")
    outcome = resolve(
        [vampire],
        Blocks({vampire.instance_id: (creature("Statue", 0, 2, "Indestructible"),)}),
        STARTING_LIFE,
    )
    assert outcome.attacker_life_gained == 6, "three in each step"
    assert outcome.damage_to_defender == 0, "still blocked, and no trample"
