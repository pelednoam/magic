"""Properties of combat, over boards Hypothesis chooses.

Every bug M4's combat engine shipped with belongs to a class that reads as a
property, and every one was found by an example test that happened to be
written. These are the same statements made generally: order-independence,
conservation, and that blocking can never be worse for the defender than
standing still.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from helpers import creature
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import Blocks, Creature
from mtgcoach.core.combat.search import best_defence, plans

KEYWORDS = [
    "Flying",
    "Reach",
    "First strike",
    "Double strike",
    "Deathtouch",
    "Trample",
    "Lifelink",
    "Menace",
    "Indestructible",
]

STARTING_LIFE = 20


def _build(name: str, power: int, toughness: int, keywords: list[str]) -> Creature:
    """A generated creature, named so a shrunk counterexample stays readable."""
    return creature(name, power, toughness, *keywords)


creatures = st.builds(
    _build,
    st.text(alphabet="ABCDEFG", min_size=1, max_size=2),
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=1, max_value=6),
    st.lists(st.sampled_from(KEYWORDS), max_size=3, unique=True),
)
boards = st.tuples(
    st.lists(creatures, max_size=3),
    st.lists(creatures, max_size=3),
)


@settings(max_examples=120, deadline=None)
@given(boards, st.integers(min_value=1, max_value=20))
def test_the_advice_does_not_depend_on_the_order_of_the_lists(
    board: tuple[list[Creature], list[Creature]], life: int
) -> None:
    """Two callers with the same board must be coached the same way."""
    attackers, blockers = board
    forward = best_defence(attackers, blockers, life)
    backward = best_defence(attackers[::-1], blockers[::-1], life)
    assert forward.damage_to_defender == backward.damage_to_defender
    assert sorted(forward.attacker_names) == sorted(backward.attacker_names)
    assert sorted(forward.blocker_names) == sorted(backward.blocker_names)


@settings(max_examples=120, deadline=None)
@given(boards, st.integers(min_value=1, max_value=20))
def test_blocking_is_never_worse_for_the_defender_than_not_blocking(
    board: tuple[list[Creature], list[Creature]], life: int
) -> None:
    """Not blocking is always available, so the best defence is at least it."""
    attackers, blockers = board
    best = best_defence(attackers, blockers, life)
    idle = resolve(attackers, Blocks())
    assert best.damage_to_defender <= idle.damage_to_defender or not best.blockers_lost


@settings(max_examples=120, deadline=None)
@given(boards)
def test_unblocked_damage_is_exactly_the_power_that_swung(
    board: tuple[list[Creature], list[Creature]],
) -> None:
    """Damage is conserved: nothing is created or lost between the two steps."""
    attackers, _ = board
    outcome = resolve(attackers, Blocks())
    expected = sum(c.power * (2 if c.has("Double strike") else 1) for c in attackers)
    assert outcome.damage_to_defender == expected


@settings(max_examples=80, deadline=None)
@given(boards, st.integers(min_value=1, max_value=20))
def test_a_blocked_attacker_never_reaches_the_player_without_trample(
    board: tuple[list[Creature], list[Creature]], life: int
) -> None:
    """CR 509.1h, stated generally: blocked is blocked, however the blockers die."""
    attackers, blockers = board
    if not attackers or not blockers:
        return
    blocked = Blocks({attackers[0].instance_id: (blockers[0],)})
    outcome = resolve([attackers[0]], blocked)
    assert outcome.damage_to_defender == 0 or attackers[0].has("Trample")
    assert life > 0


@settings(max_examples=60, deadline=None)
@given(boards, st.integers(min_value=1, max_value=20))
def test_every_plan_is_a_distinct_subset_and_not_attacking_is_one(
    board: tuple[list[Creature], list[Creature]], life: int
) -> None:
    attackers, blockers = board
    found = plans(attackers, blockers, life)
    chosen = [tuple(sorted(c.instance_id for c in p.attackers)) for p in found]
    assert len(chosen) == len(set(chosen)) == 2 ** len(attackers)
    assert () in chosen


@settings(max_examples=60, deadline=None)
@given(boards, st.integers(min_value=1, max_value=20))
def test_a_plan_is_lethal_exactly_when_it_empties_the_life_total(
    board: tuple[list[Creature], list[Creature]], life: int
) -> None:
    attackers, blockers = board
    for plan in plans(attackers, blockers, life):
        assert plan.is_lethal == (plan.defender_life_after <= 0)
