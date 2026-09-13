"""Abilities to JSON and back.

The cards named here are real ones from the Beginner Box, several of them the
exact cards the first extraction run could not express at all.
"""

from __future__ import annotations

import pytest

from mtgcoach.carddata.abilitycodec import decode, encode
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.abilities import (
    Ability,
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
from mtgcoach.core.vocabulary import AbilityCost, CounterKind, Restriction, TriggerEvent

#: One of every kind, so a new ability without a codec case fails here.
EVERY_KIND: list[Ability] = [
    SpellAbility((ChangeLife(2, Controller.YOU),)),
    TriggeredAbility(
        Trigger(TriggerEvent.YOU_GAIN_LIFE),
        (PutCounters(CounterKind.PLUS_ONE_PLUS_ONE, 1, SELF),),
    ),
    ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),)),
    StaticModifier(1, 0, ANY_CREATURE),
    StaticRestriction(Restriction.CANT_ATTACK, SELF),
    UnmodeledAbility("Choose one", "modal"),
]


@pytest.mark.parametrize("ability", EVERY_KIND, ids=lambda a: type(a).__name__)
def test_every_ability_kind_round_trips(ability: Ability) -> None:
    assert decode(encode(ability), "test") == ability


def test_the_codec_covers_the_whole_union() -> None:
    kinds = {str(encode(a)["kind"]) for a in EVERY_KIND}
    assert len(kinds) == len(EVERY_KIND)


def test_druid_of_the_cowl() -> None:
    """The `{T}: Add {G}` shape, unmodellable before the ability layer."""
    body = encode(ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),)))
    assert body["kind"] == "activated"
    assert body["cost"] == {"mana": "", "tap": True, "sacrifice_self": False}
    assert body["effects"] == [{"kind": "produce_mana", "mana": "{G}", "amount": 1}]


def test_a_trigger_with_a_subject_round_trips() -> None:
    ability = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS, ANY_CREATURE), ())
    assert decode(encode(ability), "test") == ability


def test_a_trigger_without_a_subject_encodes_null() -> None:
    assert encode(TriggeredAbility(Trigger(TriggerEvent.DIES), ()))["subject"] is None


def test_an_unknown_ability_kind_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="unknown ability kind"):
        decode({"kind": "telepathy"}, "test")


def test_an_unknown_trigger_event_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="unknown event"):
        decode({"kind": "triggered", "event": "when_it_rains", "effects": []}, "test")


def test_an_unknown_restriction_is_rejected() -> None:
    body = encode(StaticRestriction(Restriction.CANT_BLOCK, SELF))
    body["restriction"] = "cant_dance"
    with pytest.raises(MalformedJsonError, match="unknown restriction"):
        decode(body, "test")


def test_a_missing_cost_defaults_to_free() -> None:
    """An ability with no cost object is free, not malformed."""
    ability = decode({"kind": "activated", "effects": []}, "test")
    assert isinstance(ability, ActivatedAbility)
    assert ability.cost.is_free


def test_a_non_integer_static_modifier_is_rejected() -> None:
    body = encode(StaticModifier(1, 0, ANY_CREATURE))
    body["power"] = "one"
    with pytest.raises(MalformedJsonError, match="must be an integer"):
        decode(body, "test")


def test_effects_inside_an_ability_are_validated() -> None:
    """A bad effect must not ride in on a well-formed ability."""
    with pytest.raises(MalformedJsonError, match="unknown effect kind"):
        decode({"kind": "spell", "effects": [{"kind": "teleport"}]}, "test")


def test_an_ability_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="should be an object"):
        decode("spell", "test")
