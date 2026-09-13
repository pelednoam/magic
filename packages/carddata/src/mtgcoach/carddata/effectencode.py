"""Effects to JSON.

An exhaustive ``match`` rather than a lookup table, so that adding a member to
``Effect`` fails the type check here until it can be written down. A table would
have compiled happily and silently dropped the new kind out of every sealed
fixture -- which is precisely the drift the signed manifest exists to catch, and
much better caught before it is written.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from mtgcoach.carddata.effectparts import (
    encode_amount,
    encode_target,
    encode_token,
    strings,
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

if TYPE_CHECKING:
    from mtgcoach.carddata.jsondata import JsonObject
    from mtgcoach.core.effects import Effect


def encode(effect: Effect) -> JsonObject:
    """Write one effect as a JSON object."""
    match effect:
        case DealDamage(amount=amount, target=target, source=source):
            return {
                "kind": "deal_damage",
                "amount": encode_amount(amount),
                "target": encode_target(target),
                "source": encode_target(source) if source is not None else None,
            }
        case Destroy(target=target):
            return {"kind": "destroy", "target": encode_target(target)}
        case ExileTarget(target=target):
            return {"kind": "exile", "target": encode_target(target)}
        case MoveTo(target=target, to_zone=zone):
            return {
                "kind": "move_to",
                "target": encode_target(target),
                "to_zone": zone.value,
            }
        case CounterSpell(target=target):
            return {"kind": "counter_spell", "target": encode_target(target)}
        case Draw(count=count, who=who):
            return {"kind": "draw", "count": count, "who": who.value}
        case Discard(count=count, who=who):
            return {"kind": "discard", "count": count, "who": who.value}
        case ChangeLife(amount=life, who=who):
            return {"kind": "change_life", "amount": life, "who": who.value}
        case Scry(count=count):
            return {"kind": "scry", "count": count}
        case ModifyStats(power=power, toughness=toughness, target=t, duration=d):
            return {
                "kind": "modify_stats",
                "power": power,
                "toughness": toughness,
                "target": encode_target(t),
                "duration": d.value,
            }
        case GrantKeywords(keywords=keywords, target=target, duration=duration):
            return {
                "kind": "grant_keywords",
                "keywords": strings(keywords),
                "target": encode_target(target),
                "duration": duration.value,
            }
        case PutCounters(kind=counter, count=count, target=target):
            return {
                "kind": "put_counters",
                "counter": counter.value,
                "count": encode_amount(count),
                "target": encode_target(target),
            }
        case SetTappedEffect(tapped=tapped, target=target):
            return {
                "kind": "set_tapped",
                "tapped": tapped,
                "target": encode_target(target),
            }
        case CreateTokens(count=count, token=token):
            return {
                "kind": "create_tokens",
                "count": count,
                "token": encode_token(token),
            }
        case ProduceMana(mana=mana, amount=amount):
            return {
                "kind": "produce_mana",
                "mana": mana,
                "amount": encode_amount(amount),
            }
        case Unmodeled(text=text, reason=reason):
            return {"kind": "unmodeled", "text": text, "reason": reason}
    assert_never(effect)
