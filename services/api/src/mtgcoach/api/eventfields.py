"""Reading one field out of a client's JSON, or refusing it.

Split from ``eventspec`` so that module is the shape of the wire -- which type
means which event -- and this one is the paranoia. Every reader here answers
the same question about untrusted input: is this the type it must be, exactly,
with no coercion. ``0`` is not ``false``; ``true`` is not ``1``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Mapping


class BadEventError(ValueError):
    """The client sent something that is not an event this engine accepts.

    A ``ValueError`` with a sentence in it, because the sentence goes back over
    the wire. "unknown event type 'atack'" is a bug report; a 422 with a schema
    dump is a puzzle.
    """


def instance(payload: Mapping[str, object]) -> InstanceId:
    """The card this event is about."""
    return InstanceId(text(payload, "instance_id"))


def text(payload: Mapping[str, object], field: str) -> str:
    """A required string field."""
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        msg = f"{field!r} must be a non-empty string"
        raise BadEventError(msg)
    return value


def flag(payload: Mapping[str, object], field: str) -> bool:
    """A required boolean field.

    Checked for ``bool`` specifically, not truthiness: JSON's ``0`` and ``""``
    are not "untapped", they are a client that got the field wrong, and silently
    reading them as false would tap the wrong permanent.
    """
    value = payload.get(field)
    if not isinstance(value, bool):
        msg = f"{field!r} must be true or false"
        raise BadEventError(msg)
    return value


def whole(payload: Mapping[str, object], field: str) -> int:
    """A required integer field.

    ``bool`` is excluded because it is an ``int`` in Python and not one in any
    other sense: ``{"amount": true}`` would otherwise gain a player one life.
    """
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field!r} must be a whole number"
        raise BadEventError(msg)
    return value


def zone(payload: Mapping[str, object]) -> ZoneName:
    """The zone a card is moving to."""
    name = text(payload, "to")
    try:
        return ZoneName(name)
    except ValueError as exc:
        allowed = ", ".join(sorted(zone.value for zone in ZoneName))
        msg = f"unknown zone {name!r}; expected one of {allowed}"
        raise BadEventError(msg) from exc


def player(payload: Mapping[str, object]) -> PlayerId:
    """The seat this event is about."""
    return PlayerId(text(payload, "player"))


def instances(payload: Mapping[str, object], field: str) -> tuple[InstanceId, ...]:
    """An optional list of card identifiers.

    Absent is empty, which is a spell that costs nothing and a recording made
    before casting took a payment. Present and not a list of non-empty strings
    is a client that got it wrong, and is refused rather than trimmed: a
    payment with one element quietly dropped is a different payment, and it
    would be a *cheaper* one.
    """
    value = payload.get(field)
    if value is None:
        return ()
    if not isinstance(value, list):
        msg = f"{field!r} must be a list of card identifiers"
        raise BadEventError(msg)
    found: list[InstanceId] = []
    for one in cast("list[object]", value):
        if not isinstance(one, str) or not one:
            msg = f"{field!r} must be a list of non-empty strings, got {one!r}"
            raise BadEventError(msg)
        found.append(InstanceId(one))
    return tuple(found)
