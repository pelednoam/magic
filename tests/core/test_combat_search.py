"""Choosing an attack, assuming the opponent blocks well."""

from __future__ import annotations

from dataclasses import replace

import pytest

from helpers import creature, facts
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.combat.budget import (
    MAX_ATTACKERS,
    MAX_BLOCKERS,
    TooManyCombinationsError,
)
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.defending import best_defence
from mtgcoach.core.combat.model import Blocks, Creature, can_block
from mtgcoach.core.combat.search import plans
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent

STARTING_LIFE = 20


def test_attacking_with_a_flyer_they_cannot_block() -> None:
    """The commonest good attack in the box, and it should come out first."""
    flyer = creature("Skyhunter", 2, 2, "Flying")
    ground = creature("Bear", 2, 2)
    best = plans([flyer, ground], [creature("Ogre", 3, 3)], STARTING_LIFE)[0]
    assert best.names == ("Skyhunter",)
    assert best.outcome.damage_to_defender == 2
    assert not best.outcome.attacker_names


def test_lethal_is_ranked_first() -> None:
    attackers = [creature("A", 3, 3), creature("B", 3, 3)]
    best = plans(attackers, [], 5)[0]
    assert best.is_lethal
    assert best.defender_life_after <= 0


def test_not_attacking_is_always_an_option() -> None:
    """A coach that cannot say 'hold back' is not giving advice."""
    suicidal = creature("Squire", 1, 1)
    all_plans = plans([suicidal], [creature("Giant", 5, 5)], STARTING_LIFE)
    assert any(p.names == () for p in all_plans)
    assert all_plans[0].names == (), "attacking into a bigger creature is not best"


def test_a_good_defender_chump_blocks_to_survive() -> None:
    """At one life, the defender must block even at a loss."""
    attacker = creature("Bear", 2, 2)
    outcome = best_defence([attacker], [creature("Squire", 1, 1)], 1)
    assert outcome.damage_to_defender == 0
    assert outcome.blocker_names == ("Squire",)


def test_a_defender_at_high_life_takes_the_hit_rather_than_chump_block() -> None:
    """Ordering damage above creatures would make every attack look bad."""
    attacker = creature("Bear", 2, 2)
    outcome = best_defence([attacker], [creature("Squire", 1, 1)], STARTING_LIFE)
    assert outcome.damage_to_defender == 2
    assert not outcome.blocker_names


def test_a_defender_takes_a_free_trade() -> None:
    attacker = creature("Bear", 2, 2)
    outcome = best_defence([attacker], [creature("Wall", 0, 4)], STARTING_LIFE)
    assert outcome.damage_to_defender == 0
    assert not outcome.blocker_names


def test_a_defender_blocks_to_kill_when_it_costs_nothing() -> None:
    attacker = creature("Squire", 1, 1)
    outcome = best_defence([attacker], [creature("Giant", 5, 5)], STARTING_LIFE)
    assert outcome.attacker_names == ("Squire",)
    assert not outcome.blocker_names


def test_flying_cannot_be_blocked_by_a_ground_creature() -> None:
    assert not can_block(creature("Bear", 2, 2), creature("Flyer", 2, 2, "Flying"))


def test_reach_blocks_flying() -> None:
    assert can_block(creature("Spider", 1, 3, "Reach"), creature("Flyer", 2, 2, "Flying"))


def test_flying_blocks_flying() -> None:
    assert can_block(creature("Bird", 1, 1, "Flying"), creature("Flyer", 2, 2, "Flying"))


def test_a_ground_creature_blocks_a_ground_creature() -> None:
    assert can_block(creature("Bear", 2, 2), creature("Ogre", 3, 3))


def test_a_tapped_creature_cannot_block() -> None:
    bear = creature("Bear", 2, 2)
    tapped = replace(bear, permanent=bear.permanent.tap())
    assert not can_block(tapped, creature("Other", 2, 2))


def test_summoning_sickness_does_not_stop_a_block() -> None:
    """CR 302.6 restricts attacking and {T} costs, not blocking."""
    sick = Creature(
        Permanent(CardInstance(InstanceId("new"), OracleId("new"))),
        facts("Newcomer", "", power=2, toughness=2, creature=True),
    )
    assert sick.permanent.summoning_sick
    assert can_block(sick, creature("Other", 2, 2))


def test_menace_needs_two_blockers() -> None:
    """CR 702.111b -- one blocker is not a legal block at all."""
    attacker = creature("Brute", 3, 3, "Menace")
    one = best_defence([attacker], [creature("Bear", 2, 2)], STARTING_LIFE)
    assert one.damage_to_defender == 3, "a single blocker cannot block it"

    two = best_defence([attacker], [creature("A", 2, 2), creature("B", 2, 2)], 3)
    assert two.damage_to_defender == 0


def test_a_creature_with_no_fixed_power_stops_the_evaluation() -> None:
    """Consuming Aberration is */*; guessing zero would make it look harmless."""
    star = Creature(
        Permanent(CardInstance(InstanceId("ca"), OracleId("ca"))).settle(),
        facts("Consuming Aberration", creature=True),
    )
    with pytest.raises(ValueError, match="no fixed power"):
        plans([star], [], STARTING_LIFE)


def test_an_unknown_blocker_stops_the_evaluation_too() -> None:
    blocker = Creature(
        Permanent(CardInstance(InstanceId("ca"), OracleId("ca"))).settle(),
        facts("Consuming Aberration", creature=True),
    )
    with pytest.raises(ValueError, match="no fixed power"):
        plans([creature("Bear", 2, 2)], [blocker], STARTING_LIFE)


def test_too_many_attackers_is_refused_rather_than_approximated() -> None:
    army = [creature(f"C{i}", 1, 1) for i in range(MAX_ATTACKERS + 1)]
    with pytest.raises(TooManyCombinationsError, match="cannot evaluate 9 attackers"):
        plans(army, [], STARTING_LIFE)


def test_too_many_blockers_is_refused_too() -> None:
    """The blockers are the exponent; capping only attackers guarded nothing."""
    wall = [creature(f"B{i}", 1, 1) for i in range(MAX_BLOCKERS + 1)]
    with pytest.raises(TooManyCombinationsError, match="blockers"):
        plans([creature("Bear", 2, 2)], wall, STARTING_LIFE)


def test_best_defence_refuses_an_oversized_board_as_well() -> None:
    """It is reachable directly, so the guard cannot live only in `plans`."""
    wall = [creature(f"B{i}", 1, 1) for i in range(MAX_BLOCKERS + 1)]
    with pytest.raises(TooManyCombinationsError):
        best_defence([creature("Bear", 2, 2)], wall, STARTING_LIFE)


def test_the_attacker_limit_itself_is_allowed() -> None:
    army = [creature(f"C{i}", 1, 1) for i in range(MAX_ATTACKERS)]
    assert len(plans(army, [], STARTING_LIFE)) == 2**MAX_ATTACKERS


def test_the_blocker_limit_itself_is_allowed() -> None:
    wall = [creature(f"B{i}", 1, 1) for i in range(MAX_BLOCKERS)]
    assert plans([creature("Bear", 2, 2)], wall, STARTING_LIFE)


def test_every_subset_is_considered() -> None:
    attackers = [creature("A", 1, 1), creature("B", 1, 1), creature("C", 1, 1)]
    assert len(plans(attackers, [], STARTING_LIFE)) == 2 ** len(attackers)


def test_an_empty_board_has_one_plan() -> None:
    assert plans([], [], STARTING_LIFE)[0].names == ()


def test_blocking_nothing_is_a_legal_assignment() -> None:
    attacker = creature("Bear", 2, 2)
    assert best_defence([attacker], [], STARTING_LIFE).damage_to_defender == 2


def test_resolve_handles_an_attacker_with_no_blocks_entry() -> None:
    bear = creature("Bear", 2, 2)
    assert resolve([bear], Blocks(), STARTING_LIFE).damage_to_defender == 2


def test_value_counts_trades_and_losses() -> None:
    """Two damage through beats two damage through that cost a creature."""
    through = plans([creature("Flyer", 2, 2, "Flying")], [creature("Bear", 2, 2)], STARTING_LIFE)
    assert through[0].value == 2
