"""Resolving combat damage.

Every case here is one a beginner gets wrong, and several were wrong in this
code before the test existed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers import creature
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import Blocks, Creature

if TYPE_CHECKING:
    from mtgcoach.core.combat.board import Outcome


def _one(attacker: Creature, *blockers: Creature) -> Outcome:
    """One attacker, blocked by these creatures."""
    return resolve([attacker], Blocks({attacker.instance_id: tuple(blockers)}))


def test_an_unblocked_creature_hits_the_player() -> None:
    bear = creature("Bear", 2, 2)
    outcome = resolve([bear], Blocks())
    assert outcome.damage_to_defender == 2
    assert not outcome.attacker_names


def test_an_even_trade_kills_both() -> None:
    """Damage in a step is simultaneous: the one that dies still deals its own."""
    attacker, blocker = creature("Bear", 2, 2), creature("Other", 2, 2)
    outcome = _one(attacker, blocker)
    assert outcome.attacker_names == ("Bear",)
    assert outcome.blocker_names == ("Other",)


def test_a_wall_stops_damage_without_dying() -> None:
    outcome = _one(creature("Bear", 2, 2), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 0
    assert not outcome.blocker_names
    assert not outcome.attacker_names


def test_first_strike_kills_before_taking_damage() -> None:
    """The reason first strike is worth more than its stats suggest."""
    outcome = _one(creature("Knight", 2, 2, "First strike"), creature("Bear", 2, 2))
    assert outcome.blocker_names == ("Bear",)
    assert not outcome.attacker_names


def test_first_strike_does_not_save_you_from_a_bigger_creature() -> None:
    outcome = _one(creature("Knight", 2, 2, "First strike"), creature("Giant", 5, 5))
    assert outcome.attacker_names == ("Knight",)
    assert not outcome.blocker_names


def test_double_strike_deals_damage_twice() -> None:
    outcome = resolve([creature("Hero", 2, 2, "Double strike")], Blocks())
    assert outcome.damage_to_defender == 4


def test_deathtouch_kills_anything_it_damages() -> None:
    """A 1/1 trades with a 5/5, which is not obvious to a new player."""
    outcome = _one(creature("Giant", 5, 5), creature("Snake", 1, 1, "Deathtouch"))
    assert outcome.attacker_names == ("Giant",)
    assert outcome.blocker_names == ("Snake",)


def test_indestructible_survives_lethal_damage() -> None:
    outcome = _one(creature("Giant", 5, 5), creature("Statue", 1, 1, "Indestructible"))
    assert not outcome.blocker_names


def test_indestructible_survives_deathtouch() -> None:
    outcome = _one(
        creature("Snake", 1, 1, "Deathtouch"), creature("Statue", 0, 4, "Indestructible")
    )
    assert not outcome.blocker_names


def test_trample_spills_the_excess_through() -> None:
    outcome = _one(creature("Rhino", 5, 5, "Trample"), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 1
    assert outcome.blocker_names == ("Wall",)


def test_trample_with_deathtouch_only_needs_one() -> None:
    """CR 702.2b plus trample: one point is lethal, the other four get through."""
    outcome = _one(creature("Hydra", 5, 5, "Trample", "Deathtouch"), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 4


def test_no_trample_means_nothing_gets_through() -> None:
    outcome = _one(creature("Giant", 5, 5), creature("Wall", 0, 1))
    assert outcome.damage_to_defender == 0


def test_lifelink_gains_life_for_damage_dealt() -> None:
    outcome = resolve([creature("Cleric", 3, 3, "Lifelink")], Blocks())
    assert outcome.attacker_life_gained == 3


def test_an_attacker_short_of_lethal_for_two_kills_only_the_first() -> None:
    attacker = creature("Giant", 3, 3)
    outcome = resolve(
        [attacker],
        Blocks({attacker.instance_id: (creature("A", 2, 2), creature("B", 2, 2))}),
    )
    assert outcome.blocker_names == ("A",)


def test_lifelink_counts_damage_to_blockers_too() -> None:
    outcome = _one(creature("Cleric", 3, 3, "Lifelink"), creature("Bear", 2, 2))
    assert outcome.attacker_life_gained == 3


def test_two_blockers_can_gang_up() -> None:
    attacker = creature("Giant", 4, 4)
    outcome = resolve(
        [attacker],
        Blocks({attacker.instance_id: (creature("A", 2, 2), creature("B", 2, 2))}),
    )
    assert outcome.attacker_names == ("Giant",)
    assert outcome.blocker_names == ("A", "B"), "lethal to each in turn (CR 510.1a)"


def test_several_attackers_at_once() -> None:
    a, b = creature("A", 2, 2), creature("B", 3, 3)
    assert resolve([a, b], Blocks()).damage_to_defender == 5


def test_a_creature_killed_by_first_strike_deals_no_damage() -> None:
    """The surprise that makes first strike worth playing around."""
    outcome = _one(creature("Knight", 3, 3, "First strike"), creature("Bear", 2, 2))
    assert outcome.blocker_names == ("Bear",)
    assert not outcome.attacker_names


def test_a_blocker_with_lifelink_gains_the_defender_life() -> None:
    """Lifelink is not the attacker's privilege, and the claim said so flatly."""
    outcome = _one(creature("Bear", 2, 2), creature("Cleric", 3, 3, "Lifelink"))
    assert outcome.defender_life_gained == 3
    assert outcome.attacker_life_gained == 0


def test_a_lifelink_block_can_make_a_lethal_attack_survivable() -> None:
    outcome = _one(creature("Bear", 2, 2), creature("Cleric", 1, 1, "Lifelink"))
    assert outcome.defender_life_after(1) == 2, "one life, plus the one gained"


def test_a_blocked_double_striker_does_not_reach_the_player() -> None:
    """CR 509.1h: it stays blocked even when every blocker is dead."""
    outcome = _one(creature("Duellist", 3, 3, "Double strike"), creature("Squire", 1, 1))
    assert outcome.blocker_names == ("Squire",)
    assert outcome.damage_to_defender == 0


def test_a_blocked_first_striker_does_not_reach_the_player_either() -> None:
    attacker = creature("Knight", 3, 3, "First strike")
    outcome = _one(attacker, creature("Squire", 1, 1))
    assert outcome.damage_to_defender == 0


def test_trample_still_spills_over_a_dead_blocker() -> None:
    """Trample is the one thing that *does* put damage through a block."""
    attacker = creature("Brute", 5, 5, "Trample", "Double strike")
    outcome = _one(attacker, creature("Squire", 1, 1))
    assert outcome.damage_to_defender == 9, "4 spills in the first step, 5 in the second"
