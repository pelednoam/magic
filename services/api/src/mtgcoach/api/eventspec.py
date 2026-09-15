"""Turning a client's JSON into an engine event, and back again.

The boundary where untrusted input becomes a typed ``Event``. Everything past
here is checked by the type system; nothing before it is, so this is where the
checking has to be explicit and complete. ``eventfields`` does the checking of
each field; this module says which fields each event has.

It is also where one hole in ``core`` gets closed. ``PlayLand``'s own docstring
says the reducer cannot tell whether the card is a land -- ``core`` holds no
card data by design, so "until then a caller can play any card in hand as its
land for the turn". This layer *has* card data. So the check lives here, which
is the first point that can make it.

The two directions are a round trip, and ``test_eventspec`` asserts it over one
of every event. That property is what a recorded game rests on: a journal keeps
the event log, and the replay route rebuilds any moment from it with nothing
but ``core.reduce.replay``. If the two halves disagreed about a single field,
the board a child is shown stepping through a game would not be the board that
was played -- silently, because both halves would still be valid JSON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from mtgcoach.api.eventfields import (
    BadEventError,
    flag,
    instance,
    instances,
    player,
    text,
    whole,
    zone,
)
from mtgcoach.core.events import (
    AdvanceStep,
    CastSpell,
    ChangeLife,
    DrawCard,
    MoveCard,
    PlayLand,
    ResolveSpell,
    SetTapped,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from mtgcoach.api.views import Json
    from mtgcoach.core.events import Event
    from mtgcoach.core.reduce import Moving

#: Every event a client may send, by the name it sends it under.
#:
#: A table rather than a chain of ``if``s, so the set of names the wire accepts
#: is one object that can be read at a glance -- and asserted against, which is
#: what stops a new event reaching the engine without the app ever hearing of it.
BUILDERS: Mapping[str, Callable[[Mapping[str, object]], Event]] = {
    "advance_step": lambda _: AdvanceStep(),
    "draw_card": lambda payload: DrawCard(player(payload)),
    "play_land": lambda payload: PlayLand(player(payload), instance(payload)),
    "cast_spell": lambda payload: CastSpell(
        player(payload), instance(payload), instances(payload, "payment")
    ),
    "resolve_spell": lambda payload: ResolveSpell(
        player(payload), instance(payload), zone(payload)
    ),
    "set_tapped": lambda payload: SetTapped(
        player(payload), instance(payload), tapped=flag(payload, "tapped")
    ),
    "move_card": lambda payload: MoveCard(player(payload), instance(payload), zone(payload)),
    "change_life": lambda payload: ChangeLife(player(payload), whole(payload, "amount")),
}


def parse(payload: Mapping[str, object]) -> Event:
    """Build an event from a client's JSON object.

    Raises:
        BadEventError: If the type is unknown or a field is missing or ill-typed.
    """
    kind = text(payload, "type")
    build = BUILDERS.get(kind)
    if build is None:
        known = ", ".join(sorted(BUILDERS))
        msg = f"unknown event type {kind!r}; expected one of {known}"
        raise BadEventError(msg)
    return build(payload)


def written(event: Event) -> dict[str, Json]:
    """One event as the JSON object ``parse`` would read back.

    Closed with ``assert_never``, so a new member of ``Event`` is a type error
    here until it is written down -- which is what makes a forgotten event a
    failing build rather than a game that replays wrong.
    """
    match event:
        case AdvanceStep():
            return {"type": "advance_step"}
        case DrawCard(seat):
            return {"type": "draw_card", "player": str(seat)}
        case PlayLand() | CastSpell() | ResolveSpell() | MoveCard():
            return _moved(event)
        case SetTapped(seat, instance_id, tapped):
            return {
                "type": "set_tapped",
                "player": str(seat),
                "instance_id": str(instance_id),
                "tapped": tapped,
            }
        case ChangeLife(seat, amount):
            return {"type": "change_life", "player": str(seat), "amount": amount}
    assert_never(event)


def _moved(event: Moving) -> dict[str, Json]:
    """The four events that take a card from one zone to another.

    Split the same way ``reduce`` splits them, and for the same reason: one
    match may not branch this many times. Both halves stay ``assert_never``-
    closed over their own part of ``Event``.
    """
    match event:
        case PlayLand(seat, instance_id):
            return _card("play_land", seat, instance_id)
        case CastSpell(seat, instance_id, payment):
            return {
                **_card("cast_spell", seat, instance_id),
                "payment": [str(one) for one in payment],
            }
        case ResolveSpell(seat, instance_id, to):
            return {**_card("resolve_spell", seat, instance_id), "to": str(to)}
        case MoveCard(seat, instance_id, to):
            return {**_card("move_card", seat, instance_id), "to": str(to)}
    assert_never(event)


def _card(kind: str, seat: object, instance_id: object) -> dict[str, Json]:
    """The three fields every card movement carries."""
    return {"type": kind, "player": str(seat), "instance_id": str(instance_id)}
