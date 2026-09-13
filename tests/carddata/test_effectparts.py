"""Reading the pieces effects are built from, and refusing the ones we cannot."""

from __future__ import annotations

import pytest

from mtgcoach.carddata.effectparts import (
    decode_amount,
    decode_target,
    decode_token,
    encode_amount,
    encode_target,
    encode_token,
)
from mtgcoach.carddata.jsondata import JsonValue, MalformedJsonError
from mtgcoach.core.amounts import Dynamic, Quantity
from mtgcoach.core.effects import TokenSpec
from mtgcoach.core.targets import ANY_CREATURE, Condition, Controller, TargetKind, TargetSpec

GOBLIN = TokenSpec(
    name="Goblin",
    type_line="Token Creature — Goblin",
    power=1,
    toughness=1,
    colors=frozenset({"R"}),
)


def test_amounts_round_trip() -> None:
    for amount in (0, 3, Dynamic(Quantity.X)):
        assert decode_amount(encode_amount(amount), "test") == amount


def test_a_boolean_is_not_an_amount() -> None:
    truthy: JsonValue = True
    with pytest.raises(MalformedJsonError, match="cannot be a boolean"):
        decode_amount(truthy, "test")


def test_an_unknown_quantity_is_rejected() -> None:
    with pytest.raises(MalformedJsonError, match="unknown quantity"):
        decode_amount({"quantity": "vibes"}, "test")


def test_targets_round_trip() -> None:
    spec = TargetSpec(
        kinds=frozenset({TargetKind.PERMANENT}),
        controller=Controller.OPPONENT,
        conditions=frozenset({Condition.NONLAND}),
        minimum=0,
        maximum=1,
    )
    assert decode_target(encode_target(spec), "test") == spec


def test_an_unknown_target_kind_is_rejected() -> None:
    body = encode_target(ANY_CREATURE)
    body["kinds"] = ["wizard"]
    with pytest.raises(MalformedJsonError, match="unknown kind"):
        decode_target(body, "test")


def test_an_unknown_controller_is_rejected() -> None:
    body = encode_target(ANY_CREATURE)
    body["controller"] = "everyone"
    with pytest.raises(MalformedJsonError, match="unknown controller"):
        decode_target(body, "test")


def test_an_unknown_condition_is_rejected() -> None:
    body = encode_target(ANY_CREATURE)
    body["conditions"] = ["sideways"]
    with pytest.raises(MalformedJsonError, match="unknown condition"):
        decode_target(body, "test")


@pytest.mark.parametrize("bad", [-1, "one", True])
def test_a_bad_target_count_is_rejected(bad: object) -> None:
    body = encode_target(ANY_CREATURE)
    body["minimum"] = bad  # type: ignore[assignment]
    with pytest.raises(MalformedJsonError, match="non-negative integer"):
        decode_target(body, "test")


def test_missing_counts_default_to_one() -> None:
    body = encode_target(ANY_CREATURE)
    del body["minimum"]
    del body["maximum"]
    spec = decode_target(body, "test")
    assert (spec.minimum, spec.maximum) == (1, 1)


def test_tokens_round_trip() -> None:
    assert decode_token(encode_token(GOBLIN), "test") == GOBLIN


def test_a_token_without_stats_round_trips() -> None:
    treasure = TokenSpec(name="Treasure", type_line="Token Artifact — Treasure")
    assert decode_token(encode_token(treasure), "test") == treasure


def test_a_bad_token_stat_is_rejected() -> None:
    body = encode_token(GOBLIN)
    body["power"] = "one"
    with pytest.raises(MalformedJsonError, match="integer or null"):
        decode_token(body, "test")
