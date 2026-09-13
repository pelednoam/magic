"""Encoding effects, and reading the pieces back.

The cards named in these tests are real ones from the Beginner Box; the schema
was designed by reading them, so they are the right thing to check it against.
"""

from __future__ import annotations

import json

import pytest

from mtgcoach.carddata.effectencode import encode
from mtgcoach.carddata.effectparts import (
    encode_target,
)
from mtgcoach.core.amounts import Dynamic, Quantity
from mtgcoach.core.effects import (
    ChangeLife,
    CounterKind,
    CounterSpell,
    CreateTokens,
    DealDamage,
    Destroy,
    Discard,
    Draw,
    Duration,
    Effect,
    ExileTarget,
    GrantKeywords,
    ModifyStats,
    MoveTo,
    PutCounters,
    Scry,
    SetTappedEffect,
    TokenSpec,
    Unmodeled,
)
from mtgcoach.core.targets import (
    ANY_CREATURE,
    Condition,
    Controller,
    TargetKind,
    TargetSpec,
)
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
    }
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
