"""Abilities to and from JSON.

Both directions live together because an ability is a thin wrapper: the effects
inside it already have their own codec, and splitting the wrapper across two
modules would only make it easier for the halves to disagree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from mtgcoach.carddata.effectdecode import decode as decode_effect
from mtgcoach.carddata.effectencode import encode as encode_effect
from mtgcoach.carddata.effectparts import decode_target, encode_target
from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    optional_str,
    require_object,
    require_str,
)
from mtgcoach.core.abilities import (
    ActivatedAbility,
    SpellAbility,
    StaticModifier,
    StaticRestriction,
    Trigger,
    TriggeredAbility,
    UnmodeledAbility,
)
from mtgcoach.core.vocabulary import AbilityCost, Restriction, TriggerEvent

if TYPE_CHECKING:
    from mtgcoach.carddata.jsondata import JsonObject
    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.effects import Effect


def _effects(obj: JsonObject, context: str) -> tuple[Effect, ...]:
    return tuple(decode_effect(e, context) for e in as_array(obj.get("effects")) or [])


def _enum[T](factory: type[T], name: str, label: str, context: str) -> T:
    try:
        return factory(name)  # type: ignore[call-arg]
    except ValueError as exc:
        msg = f"{context}: unknown {label} {name!r}"
        raise MalformedJsonError(msg) from exc


def _int(obj: JsonObject, key: str, context: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{context}: {key!r} must be an integer, got {value!r}"
        raise MalformedJsonError(msg)
    return value


def encode(ability: Ability) -> JsonObject:
    """Write one ability as a JSON object."""
    match ability:
        case SpellAbility(effects=effects):
            return {"kind": "spell", "effects": [encode_effect(e) for e in effects]}
        case TriggeredAbility(trigger=trigger, effects=effects):
            return {
                "kind": "triggered",
                "event": trigger.event.value,
                "subject": (
                    encode_target(trigger.subject) if trigger.subject is not None else None
                ),
                "effects": [encode_effect(e) for e in effects],
            }
        case ActivatedAbility(cost=cost, effects=effects):
            return {
                "kind": "activated",
                "cost": {
                    "mana": cost.mana,
                    "tap": cost.tap,
                    "sacrifice_self": cost.sacrifice_self,
                },
                "effects": [encode_effect(e) for e in effects],
            }
        case StaticModifier(power=power, toughness=toughness, affects=affects):
            return {
                "kind": "static_modifier",
                "power": power,
                "toughness": toughness,
                "affects": encode_target(affects),
            }
        case StaticRestriction(restriction=restriction, affects=affects):
            return {
                "kind": "static_restriction",
                "restriction": restriction.value,
                "affects": encode_target(affects),
            }
        case UnmodeledAbility(text=text, reason=reason):
            return {"kind": "unmodeled", "text": text, "reason": reason}
    assert_never(ability)


def decode(value: object, context: str) -> Ability:
    """Read one ability.

    Raises:
        MalformedJsonError: If the object is not a recognised ability.
    """
    obj = require_object(value, context)
    kind = require_str(obj, "kind", context)
    where = f"{context}/{kind}"
    match kind:
        case "spell":
            return SpellAbility(_effects(obj, where))
        case "triggered":
            subject = obj.get("subject")
            return TriggeredAbility(
                Trigger(
                    _enum(TriggerEvent, require_str(obj, "event", where), "event", where),
                    decode_target(subject, where) if subject is not None else None,
                ),
                _effects(obj, where),
            )
        case "activated":
            cost = require_object(obj.get("cost", {}), where)
            return ActivatedAbility(
                AbilityCost(
                    mana=optional_str(cost, "mana"),
                    tap=cost.get("tap") is True,
                    sacrifice_self=cost.get("sacrifice_self") is True,
                ),
                _effects(obj, where),
            )
        case "static_modifier":
            return StaticModifier(
                _int(obj, "power", where),
                _int(obj, "toughness", where),
                decode_target(obj.get("affects"), where),
            )
        case "static_restriction":
            return StaticRestriction(
                _enum(
                    Restriction,
                    require_str(obj, "restriction", where),
                    "restriction",
                    where,
                ),
                decode_target(obj.get("affects"), where),
            )
        case "unmodeled":
            return UnmodeledAbility(
                require_str(obj, "text", where), require_str(obj, "reason", where)
            )
        case _:
            msg = f"{context}: unknown ability kind {kind!r}"
            raise MalformedJsonError(msg)
