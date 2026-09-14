"""Turning a client's JSON into an engine event, or saying why not.

The boundary where untrusted input becomes a typed ``Event``. Everything past
here is checked by the type system; nothing before it is, so this is where the
checking has to be explicit and complete.

It is also where one hole in ``core`` gets closed. ``PlayLand``'s own docstring
says the reducer cannot tell whether the card is a land -- ``core`` holds no
card data by design, so "until then a caller can play any card in hand as its
land for the turn". This layer *has* card data. So the check lives here, which
is the first point that can make it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.events import (
    AdvanceStep,
    ChangeLife,
    DrawCard,
    MoveCard,
    PlayLand,
    SetTapped,
)
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.core.events import Event


class BadEventError(ValueError):
    """The client sent something that is not an event this engine accepts.

    A ``ValueError`` with a sentence in it, because the sentence goes back over
    the wire. "unknown event type 'atack'" is a bug report; a 422 with a schema
    dump is a puzzle.
    """


def parse(payload: Mapping[str, object]) -> Event:
    """Build an event from a client's JSON object.

    Raises:
        BadEventError: If the type is unknown or a field is missing or ill-typed.
    """
    kind = _text(payload, "type")
    if kind == "advance_step":
        return AdvanceStep()
    if kind == "draw_card":
        return DrawCard(PlayerId(_text(payload, "player")))
    if kind == "play_land":
        return PlayLand(PlayerId(_text(payload, "player")), _instance(payload))
    if kind == "set_tapped":
        return SetTapped(
            PlayerId(_text(payload, "player")),
            _instance(payload),
            tapped=_flag(payload, "tapped"),
        )
    if kind == "move_card":
        return MoveCard(PlayerId(_text(payload, "player")), _instance(payload), _zone(payload))
    if kind == "change_life":
        return ChangeLife(PlayerId(_text(payload, "player")), _whole(payload, "amount"))
    msg = f"unknown event type {kind!r}"
    raise BadEventError(msg)


def _instance(payload: Mapping[str, object]) -> InstanceId:
    """The card this event is about."""
    return InstanceId(_text(payload, "instance_id"))


def _text(payload: Mapping[str, object], field: str) -> str:
    """A required string field."""
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        msg = f"{field!r} must be a non-empty string"
        raise BadEventError(msg)
    return value


def _flag(payload: Mapping[str, object], field: str) -> bool:
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


def _whole(payload: Mapping[str, object], field: str) -> int:
    """A required integer field.

    ``bool`` is excluded because it is an ``int`` in Python and not one in any
    other sense: ``{"amount": true}`` would otherwise gain a player one life.
    """
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{field!r} must be a whole number"
        raise BadEventError(msg)
    return value


def _zone(payload: Mapping[str, object]) -> ZoneName:
    """The zone a card is moving to."""
    name = _text(payload, "to")
    try:
        return ZoneName(name)
    except ValueError as exc:
        allowed = ", ".join(sorted(zone.value for zone in ZoneName))
        msg = f"unknown zone {name!r}; expected one of {allowed}"
        raise BadEventError(msg) from exc
