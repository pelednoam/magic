"""Encoding effects, and reading the pieces back.

The cards named in these tests are real ones from the Beginner Box; the schema
was designed by reading them, so they are the right thing to check it against.
"""

from __future__ import annotations

import json

import pytest

from mtgcoach.carddata.effectdecode import decode
from mtgcoach.carddata.effectencode import encode
from mtgcoach.carddata.effectparts import encode_target
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.amounts import Dynamic, Quantity
from mtgcoach.core.effects import (
    ChangeLife,
    CounterSpell,
    CreateTokens,
    DealDamage,
    Destroy,
    Discard,
    Draw,
    Effect,
    ExileTarget,
    GrantKeywords,
    ModifyStats,
    MoveTo,
    ProduceMana,
    PutCounters,
    Scry,
    SetTappedEffect,
    Unmodeled,
)
from mtgcoach.core.targets import (
    ANY_CREATURE,
    Condition,
    Controller,
    TargetKind,
    TargetSpec,
)
from mtgcoach.core.vocabulary import CounterKind, Duration, TokenSpec
from mtgcoach.core.zones import ZoneName

GOBLIN = TokenSpec(
    name="Goblin",
    type_line="Token Creature — Goblin",
    power=1,
    toughness=1,
    colors=frozenset({"R"}),
)

#: One of every member, so a new effect kind without an encoder fails here.
EVERY_KIND: list[Effect] = [
    DealDamage(3, ANY_CREATURE),
    Destroy(ANY_CREATURE),
    ExileTarget(ANY_CREATURE),
    MoveTo(ANY_CREATURE, ZoneName.HAND),
    CounterSpell(TargetSpec(kinds=frozenset({TargetKind.SPELL}))),
    Draw(2, Controller.YOU),
    Discard(1, Controller.YOU),
    ChangeLife(2, Controller.YOU),
    Scry(1),
    ModifyStats(3, 3, ANY_CREATURE, Duration.UNTIL_END_OF_TURN),
    GrantKeywords(frozenset({"Flying"}), ANY_CREATURE, Duration.UNTIL_END_OF_TURN),
    PutCounters(CounterKind.PLUS_ONE_PLUS_ONE, 1, ANY_CREATURE),
    SetTappedEffect(tapped=True, target=ANY_CREATURE),
    CreateTokens(2, GOBLIN),
    Unmodeled("Choose one —", "modal spells are not modelled yet"),
]


@pytest.mark.parametrize("effect", EVERY_KIND, ids=lambda e: type(e).__name__)
def test_every_effect_kind_encodes(effect: Effect) -> None:
    body = encode(effect)
    assert isinstance(body["kind"], str)
    assert json.dumps(body), "must be JSON-serialisable"


def test_the_encoder_covers_the_whole_union() -> None:
    """A member added without a case here would encode as nothing."""
    kinds = {str(encode(e)["kind"]) for e in EVERY_KIND}
    assert len(kinds) == len(EVERY_KIND), "each kind must have a distinct tag"


def test_deadly_riposte() -> None:
    """'deals 3 damage to target tapped creature and you gain 2 life'."""
    tapped = TargetSpec(
        kinds=frozenset({TargetKind.CREATURE}),
        conditions=frozenset({Condition.TAPPED}),
    )
    damage = encode(DealDamage(3, tapped))
    assert damage == {
        "kind": "deal_damage",
        "amount": 3,
        "target": {
            "kinds": ["creature"],
            "controller": "any",
            "conditions": ["tapped"],
            "minimum": 1,
            "maximum": 1,
        },
        "source": None,
    }, "the card itself deals the damage, so there is no separate source"
    assert encode(ChangeLife(2, Controller.YOU)) == {
        "kind": "change_life",
        "amount": 2,
        "who": "you",
    }


def test_bite_down_carries_a_dynamic_amount() -> None:
    """'deals damage equal to its power'."""
    body = encode(DealDamage(Dynamic(Quantity.SOURCE_POWER), ANY_CREATURE))
    assert body["amount"] == {"quantity": "source_power"}


def test_sets_are_sorted_so_output_is_stable() -> None:
    """A fixture whose bytes move for no reason cannot be checksummed."""
    spec = TargetSpec(
        kinds=frozenset({TargetKind.ENCHANTMENT, TargetKind.ARTIFACT}),
        conditions=frozenset({Condition.HAS_FLYING, Condition.NONLAND}),
    )
    body = encode_target(spec)
    assert body["kinds"] == ["artifact", "enchantment"]
    assert body["conditions"] == ["has_flying", "nonland"]


def test_bite_down_names_the_creature_dealing_the_damage() -> None:
    """Bite Down: "target creature you control deals damage equal to its power".

    The extractor found this gap: without a source, source_power was ambiguous
    about whose power it meant.
    """
    mine = TargetSpec(kinds=frozenset({TargetKind.CREATURE}), controller=Controller.YOU)
    body = encode(DealDamage(Dynamic(Quantity.SOURCE_POWER), ANY_CREATURE, mine))
    assert body["amount"] == {"quantity": "source_power"}
    assert body["source"] == encode_target(mine)


def test_produce_mana_round_trips() -> None:
    """`{T}: Add {G}` -- the effect the mana solver reads."""
    for effect in (ProduceMana("{G}"), ProduceMana("{C}", Dynamic(Quantity.X))):
        assert decode(encode(effect), "test") == effect


def test_a_missing_target_is_rejected() -> None:
    """Every targeted effect needs one; a default would invent a legal target."""
    with pytest.raises(MalformedJsonError, match="'target' is required"):
        decode({"kind": "destroy"}, "test")


def test_a_missing_token_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="'token' is required"):
        decode({"kind": "create_tokens", "count": 1}, "test")


@pytest.mark.parametrize("kind", ["draw", "discard"])
def test_an_unknown_controller_in_an_effect_is_rejected(kind: str) -> None:
    with pytest.raises(MalformedJsonError, match="unknown controller"):
        decode({"kind": kind, "count": 1, "who": "everyone"}, "test")


def test_an_unknown_zone_is_rejected() -> None:
    body = encode(MoveTo(ANY_CREATURE, ZoneName.HAND))
    body["to_zone"] = "the_bin"
    with pytest.raises(MalformedJsonError, match="unknown zone"):
        decode(body, "test")


def test_an_unknown_duration_is_rejected() -> None:
    body = encode(ModifyStats(1, 1, ANY_CREATURE, Duration.UNTIL_END_OF_TURN))
    body["duration"] = "forever_and_ever"
    with pytest.raises(MalformedJsonError, match="unknown duration"):
        decode(body, "test")


def test_an_unknown_counter_kind_is_rejected() -> None:
    body = encode(PutCounters(CounterKind.PLUS_ONE_PLUS_ONE, 1, ANY_CREATURE))
    body["counter"] = "+5/+5"
    with pytest.raises(MalformedJsonError, match="unknown counter"):
        decode(body, "test")


@pytest.mark.parametrize("kind", ["draw", "scry"])
def test_a_non_integer_count_is_rejected(kind: str) -> None:
    with pytest.raises(MalformedJsonError, match="must be an integer"):
        decode({"kind": kind, "count": "two", "who": "you"}, "test")


def test_an_unknown_effect_kind_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="unknown effect kind"):
        decode({"kind": "telekinesis"}, "test")
