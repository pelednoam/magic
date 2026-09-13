"""The layer that says *when*."""

from __future__ import annotations

from mtgcoach.core.abilities import (
    ActivatedAbility,
    SpellAbility,
    StaticModifier,
    StaticRestriction,
    Trigger,
    TriggeredAbility,
    UnmodeledAbility,
)
from mtgcoach.core.effects import ChangeLife, ProduceMana, PutCounters
from mtgcoach.core.targets import ANY_CREATURE, SELF, Controller
from mtgcoach.core.vocabulary import (
    AbilityCost,
    CounterKind,
    Restriction,
    TriggerEvent,
)


def test_a_tap_for_mana_ability_is_a_mana_ability() -> None:
    """The `{T}: Add {G}` shape.

    CR 605.1a: a mana ability never uses the stack, which is why the solver has
    to be able to recognise one.
    """
    forest = ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),))
    assert forest.is_mana_ability
    assert not forest.cost.is_free


def test_an_ability_that_does_more_than_make_mana_is_not_a_mana_ability() -> None:
    mixed = ActivatedAbility(
        AbilityCost(tap=True), (ProduceMana("{R}"), ChangeLife(-1, Controller.YOU))
    )
    assert not mixed.is_mana_ability


def test_an_ability_with_no_effects_is_not_a_mana_ability() -> None:
    assert not ActivatedAbility(AbilityCost(tap=True), ()).is_mana_ability


def test_a_free_cost() -> None:
    assert AbilityCost().is_free
    assert not AbilityCost(mana="{2}").is_free
    assert not AbilityCost(sacrifice_self=True).is_free


def test_a_trigger_may_need_no_subject() -> None:
    """Whenever you gain life -- the event names no permanent."""
    pridemate = TriggeredAbility(
        Trigger(TriggerEvent.YOU_GAIN_LIFE),
        (PutCounters(CounterKind.PLUS_ONE_PLUS_ONE, 1, SELF),),
    )
    assert pridemate.trigger.subject is None
    counter = pridemate.effects[0]
    assert isinstance(counter, PutCounters)
    assert counter.target is SELF


def test_a_trigger_may_narrow_its_subject() -> None:
    """Whenever another creature you control enters."""
    trigger = Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS, ANY_CREATURE)
    assert trigger.subject == ANY_CREATURE


def test_a_spell_ability_holds_its_effects() -> None:
    spell = SpellAbility((ChangeLife(2, Controller.YOU),))
    assert len(spell.effects) == 1


def test_static_abilities() -> None:
    """`Pacifism` restricts its host; an anthem modifies a set of permanents."""
    assert StaticRestriction(Restriction.CANT_ATTACK, SELF).affects is SELF
    assert StaticModifier(1, 0, ANY_CREATURE).power == 1


def test_an_unmodeled_ability_keeps_the_text_and_says_why() -> None:
    ability = UnmodeledAbility("Choose one —", "modal spells are not modelled")
    assert ability.text
    assert ability.reason
