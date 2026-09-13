"""JSON for the pieces effects are built from.

Shared by the encoder and the decoder so the two cannot drift: a field written
one way and read another is the kind of asymmetry that survives every test that
only round-trips through both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    optional_str,
    require_object,
    require_str,
    string_set,
)
from mtgcoach.core.amounts import Amount, Dynamic, Quantity
from mtgcoach.core.targets import Condition, Controller, TargetKind, TargetSpec
from mtgcoach.core.vocabulary import TokenSpec

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtgcoach.carddata.jsondata import JsonObject, JsonValue


def strings(values: Iterable[str]) -> list[JsonValue]:
    """Sort a set of strings into a JSON array, so output is stable."""
    out: list[JsonValue] = []
    out.extend(sorted(values))
    return out


def encode_amount(amount: Amount) -> JsonValue:
    """Write an amount as a number, or as a named quantity."""
    if isinstance(amount, Dynamic):
        return {"quantity": amount.quantity.value}
    return amount


def decode_amount(value: JsonValue, context: str) -> Amount:
    """Read an amount.

    Raises:
        MalformedJsonError: If it is neither an integer nor a known quantity.
    """
    if isinstance(value, bool):
        msg = f"{context}: an amount cannot be a boolean"
        raise MalformedJsonError(msg)
    if isinstance(value, int):
        return value
    obj = require_object(value, context)
    name = require_str(obj, "quantity", context)
    try:
        return Dynamic(Quantity(name))
    except ValueError as exc:
        msg = f"{context}: unknown quantity {name!r}"
        raise MalformedJsonError(msg) from exc


def encode_target(target: TargetSpec) -> JsonObject:
    """Write a target spec."""
    return {
        "kinds": strings(k.value for k in target.kinds),
        "controller": target.controller.value,
        "conditions": strings(c.value for c in target.conditions),
        "minimum": target.minimum,
        "maximum": target.maximum,
    }


def _enum_set[T](obj: JsonObject, key: str, factory: type[T], context: str) -> frozenset[T]:
    out: list[T] = []
    for name in sorted(string_set(obj, key, context)):
        try:
            out.append(factory(name))  # type: ignore[call-arg]
        except ValueError as exc:
            msg = f"{context}: unknown {key[:-1]} {name!r}"
            raise MalformedJsonError(msg) from exc
    return frozenset(out)


def decode_target(value: JsonValue, context: str) -> TargetSpec:
    """Read a target spec."""
    obj = require_object(value, context)
    # Absent or null means "any", which is what TargetSpec already defaults to.
    # Demanding it rejected sixteen otherwise-valid cards on the first run: a
    # field with a sensible default has no business being mandatory.
    controller = optional_str(obj, "controller", Controller.ANY.value, context)
    try:
        who = Controller(controller)
    except ValueError as exc:
        msg = f"{context}: unknown controller {controller!r}"
        raise MalformedJsonError(msg) from exc
    return TargetSpec(
        kinds=_enum_set(obj, "kinds", TargetKind, context),
        controller=who,
        conditions=_enum_set(obj, "conditions", Condition, context),
        minimum=_count(obj, "minimum", context, default=1),
        maximum=_count(obj, "maximum", context, default=1),
    )


def _count(obj: JsonObject, key: str, context: str, default: int) -> int:
    value = obj.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{context}: {key!r} must be a non-negative integer, got {value!r}"
        raise MalformedJsonError(msg)
    return value


def encode_token(token: TokenSpec) -> JsonObject:
    """Write a token spec."""
    return {
        "name": token.name,
        "type_line": token.type_line,
        "power": token.power,
        "toughness": token.toughness,
        "colors": strings(token.colors),
        "keywords": strings(token.keywords),
    }


def decode_token(value: JsonValue, context: str) -> TokenSpec:
    """Read a token spec."""
    obj = require_object(value, context)
    return TokenSpec(
        name=require_str(obj, "name", context),
        type_line=require_str(obj, "type_line", context),
        power=_optional_count(obj, "power", context),
        toughness=_optional_count(obj, "toughness", context),
        colors=string_set(obj, "colors", context),
        keywords=string_set(obj, "keywords", context),
    )


def _optional_count(obj: JsonObject, key: str, context: str) -> int | None:
    value = obj.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{context}: {key!r} must be an integer or null, got {value!r}"
        raise MalformedJsonError(msg)
    return value
