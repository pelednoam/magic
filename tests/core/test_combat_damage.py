"""Resolving combat damage.

Every case here is one a beginner gets wrong, and several were wrong in this
code before the test existed.
"""

from __future__ import annotations

from helpers import creature
from mtgcoach.core.combat.damage import Outcome, resolve
from mtgcoach.core.combat.model import Blocks, Creature


def _one(attacker: Creature, *blockers: Creature) -> Outcome:
    """One attacker, blocked by these creatures."""
    return resolve([attacker], Blocks({attacker.instance_id: tuple(blockers)}))


def test_an_unblocked_creature_hits_the_player() -> None:
    bear = creature("Bear", 2, 2)
    outcome = resolve([bear], Blocks())
    assert outcome.damage_to_defender == 2
    assert not outcome.attackers_lost


def test_an_even_trade_kills_both() -> None:
    """Damage in a step is simultaneous: the one that dies still deals its own."""
    attacker, blocker = creature("Bear", 2, 2), creature("Other", 2, 2)
    outcome = _one(attacker, blocker)
    assert outcome.attackers_lost == ("Bear",)
    assert outcome.blockers_lost == ("Other",)


def test_a_wall_stops_damage_without_dying() -> None:
    outcome = _one(creature("Bear", 2, 2), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 0
    assert not outcome.blockers_lost
    assert not outcome.attackers_lost


def test_first_strike_kills_before_taking_damage() -> None:
    """The reason first strike is worth more than its stats suggest."""
    outcome = _one(creature("Knight", 2, 2, "First strike"), creature("Bear", 2, 2))
    assert outcome.blockers_lost == ("Bear",)
    assert not outcome.attackers_lost


def test_first_strike_does_not_save_you_from_a_bigger_creature() -> None:
    outcome = _one(creature("Knight", 2, 2, "First strike"), creature("Giant", 5, 5))
    assert outcome.attackers_lost == ("Knight",)
    assert not outcome.blockers_lost


def test_double_strike_deals_damage_twice() -> None:
    outcome = resolve([creature("Hero", 2, 2, "Double strike")], Blocks())
    assert outcome.damage_to_defender == 4


def test_deathtouch_kills_anything_it_damages() -> None:
    """A 1/1 trades with a 5/5, which is not obvious to a new player."""
    outcome = _one(creature("Giant", 5, 5), creature("Snake", 1, 1, "Deathtouch"))
    assert outcome.attackers_lost == ("Giant",)
    assert outcome.blockers_lost == ("Snake",)


def test_indestructible_survives_lethal_damage() -> None:
    outcome = _one(creature("Giant", 5, 5), creature("Statue", 1, 1, "Indestructible"))
    assert not outcome.blockers_lost


def test_indestructible_survives_deathtouch() -> None:
    outcome = _one(
        creature("Snake", 1, 1, "Deathtouch"), creature("Statue", 0, 4, "Indestructible")
    )
    assert not outcome.blockers_lost


def test_trample_spills_the_excess_through() -> None:
    outcome = _one(creature("Rhino", 5, 5, "Trample"), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 1
    assert outcome.blockers_lost == ("Wall",)


def test_trample_with_deathtouch_only_needs_one() -> None:
    """CR 702.2b plus trample: one point is lethal, the other four get through."""
    outcome = _one(creature("Hydra", 5, 5, "Trample", "Deathtouch"), creature("Wall", 0, 4))
    assert outcome.damage_to_defender == 4


def test_no_trample_means_nothing_gets_through() -> None:
    outcome = _one(creature("Giant", 5, 5), creature("Wall", 0, 1))
    assert outcome.damage_to_defender == 0


def test_lifelink_gains_life_for_damage_dealt() -> None:
    outcome = resolve([creature("Cleric", 3, 3, "Lifelink")], Blocks())
    assert outcome.life_gained == 3


def test_lifelink_counts_damage_to_blockers_too() -> None:
    outcome = _one(creature("Cleric", 3, 3, "Lifelink"), creature("Bear", 2, 2))
    assert outcome.life_gained == 3


def test_two_blockers_can_gang_up() -> None:
    attacker = creature("Giant", 4, 4)
    outcome = resolve(
        [attacker],
        Blocks({attacker.instance_id: (creature("A", 2, 2), creature("B", 2, 2))}),
    )
    assert outcome.attackers_lost == ("Giant",)
    assert outcome.blockers_lost == ("A",), "four damage kills only the first"


def test_several_attackers_at_once() -> None:
    a, b = creature("A", 2, 2), creature("B", 3, 3)
    assert resolve([a, b], Blocks()).damage_to_defender == 5


def test_a_creature_killed_by_first_strike_deals_no_damage() -> None:
    """The surprise that makes first strike worth playing around."""
    outcome = _one(creature("Knight", 3, 3, "First strike"), creature("Bear", 2, 2))
    assert outcome.blockers_lost == ("Bear",)
    assert not outcome.attackers_lost
