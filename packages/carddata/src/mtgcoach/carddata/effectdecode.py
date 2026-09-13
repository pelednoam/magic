"""JSON to effects.

The gate every proposed effect passes through. A model's output is untrusted
text like any other document: an unknown kind, a misspelled condition or a
missing field is rejected here rather than being stored and surfacing later as
a coach confidently doing the wrong thing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata.effectparts import (
    decode_amount,
    decode_target,
    decode_token,
)
from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    require_object,
    require_str,
    string_set,
)
from mtgcoach.core.effects import (
    ChangeLife,
    CounterSpell,
    CreateTokens,
    DealDamage,
    Destroy,
    Discard,
    Draw,
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
from mtgcoach.core.targets import Controller, TargetSpec
from mtgcoach.core.vocabulary import CounterKind, Duration
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.carddata.jsondata import JsonObject
    from mtgcoach.core.effects import Effect


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


def _who(obj: JsonObject, context: str) -> Controller:
    return _enum(Controller, require_str(obj, "who", context), "controller", context)


def _target(obj: JsonObject, context: str) -> TargetSpec:
    if "target" not in obj:
        msg = f"{context}: 'target' is required"
        raise MalformedJsonError(msg)
    return decode_target(obj["target"], context)


def decode(value: object, context: str) -> Effect:
    """Read one effect.

    Raises:
        MalformedJsonError: If the object is not a recognised effect.
    """
    obj = require_object(value, context)
    kind = require_str(obj, "kind", context)
    where = f"{context}/{kind}"
    match kind:
        case "deal_damage":
            raw_source = obj.get("source")
            return DealDamage(
                decode_amount(obj.get("amount", 0), where),
                _target(obj, where),
                decode_target(raw_source, where) if raw_source is not None else None,
            )
        case "destroy":
            return Destroy(_target(obj, where))
        case "exile":
            return ExileTarget(_target(obj, where))
        case "move_to":
            zone = _enum(ZoneName, require_str(obj, "to_zone", where), "zone", where)
            return MoveTo(_target(obj, where), zone)
        case "counter_spell":
            return CounterSpell(_target(obj, where))
        case "draw":
            return Draw(_int(obj, "count", where), _who(obj, where))
        case "discard":
            return Discard(_int(obj, "count", where), _who(obj, where))
        case "change_life":
            return ChangeLife(_int(obj, "amount", where), _who(obj, where))
        case "scry":
            return Scry(_int(obj, "count", where))
        case "modify_stats":
            return ModifyStats(
                _int(obj, "power", where),
                _int(obj, "toughness", where),
                _target(obj, where),
                _enum(Duration, require_str(obj, "duration", where), "duration", where),
            )
        case "grant_keywords":
            return GrantKeywords(
                string_set(obj, "keywords", where),
                _target(obj, where),
                _enum(Duration, require_str(obj, "duration", where), "duration", where),
            )
        case "put_counters":
            return PutCounters(
                _enum(CounterKind, require_str(obj, "counter", where), "counter", where),
                decode_amount(obj.get("count", 1), where),
                _target(obj, where),
            )
        case "set_tapped":
            return SetTappedEffect(
                tapped=obj.get("tapped") is True,
                target=_target(obj, where),
            )
        case "create_tokens":
            if "token" not in obj:
                msg = f"{where}: 'token' is required"
                raise MalformedJsonError(msg)
            return CreateTokens(_int(obj, "count", where), decode_token(obj["token"], where))
        case "produce_mana":
            return ProduceMana(
                require_str(obj, "mana", where),
                decode_amount(obj.get("amount", 1), where),
            )
        case "unmodeled":
            return Unmodeled(require_str(obj, "text", where), require_str(obj, "reason", where))
        case _:
            msg = f"{context}: unknown effect kind {kind!r}"
            raise MalformedJsonError(msg)
