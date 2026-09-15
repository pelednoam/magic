"""Turning a client's JSON into an event, or saying why not.

The boundary where untrusted input becomes a typed ``Event``. Every test here
is a message a client could actually send by mistake.
"""

from __future__ import annotations

from typing import get_args

import pytest

from mtgcoach.api.eventfields import BadEventError
from mtgcoach.api.eventspec import BUILDERS, parse
from mtgcoach.core.events import (
    AdvanceStep,
    ChangeLife,
    DrawCard,
    Event,
    MoveCard,
    PlayLand,
    SetTapped,
)
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.zones import ZoneName

#: Every event a client can send, as it spells it on the wire. Written out
#: rather than read from ``BUILDERS``: a test that derived the list from the
#: thing it is checking would agree with anything.
WIRE_FORMS = frozenset(
    {
        "advance_step",
        "pass_priority",
        "draw_card",
        "play_land",
        "cast_spell",
        "resolve_spell",
        "set_tapped",
        "move_card",
        "change_life",
    }
)


def test_advance_step_needs_nothing_else() -> None:
    assert parse({"type": "advance_step"}) == AdvanceStep()


def test_draw_card() -> None:
    assert parse({"type": "draw_card", "player": "you"}) == DrawCard(PlayerId("you"))


def test_play_land() -> None:
    event = parse({"type": "play_land", "player": "you", "instance_id": "you-3"})
    assert event == PlayLand(PlayerId("you"), InstanceId("you-3"))


def test_set_tapped() -> None:
    body = {"type": "set_tapped", "player": "you", "instance_id": "you-3", "tapped": True}
    assert parse(body) == SetTapped(PlayerId("you"), InstanceId("you-3"), tapped=True)


def test_move_card() -> None:
    body = {"type": "move_card", "player": "you", "instance_id": "you-3", "to": "graveyard"}
    assert parse(body) == MoveCard(PlayerId("you"), InstanceId("you-3"), ZoneName.GRAVEYARD)


def test_change_life() -> None:
    assert parse({"type": "change_life", "player": "you", "amount": -3}) == ChangeLife(
        PlayerId("you"), -3
    )


def test_an_unknown_type_says_which_one() -> None:
    """The sentence goes back over the wire, so it has to be a bug report."""
    with pytest.raises(BadEventError, match="unknown event type 'atack'"):
        parse({"type": "atack"})


def test_a_missing_type() -> None:
    with pytest.raises(BadEventError, match="'type' must be a non-empty string"):
        parse({})


def test_an_empty_string_field_is_not_a_value() -> None:
    with pytest.raises(BadEventError, match="'player'"):
        parse({"type": "draw_card", "player": ""})


def test_a_number_where_a_string_belongs() -> None:
    with pytest.raises(BadEventError, match="'player'"):
        parse({"type": "draw_card", "player": 7})


def test_a_missing_instance_id() -> None:
    with pytest.raises(BadEventError, match="'instance_id'"):
        parse({"type": "play_land", "player": "you"})


def test_tapped_must_be_a_boolean_not_a_truthy_value() -> None:
    """JSON's 0 is a client that got the field wrong, not "untapped"."""
    body = {"type": "set_tapped", "player": "you", "instance_id": "x", "tapped": 0}
    with pytest.raises(BadEventError, match="'tapped' must be true or false"):
        parse(body)


def test_life_must_be_a_number() -> None:
    with pytest.raises(BadEventError, match="'amount' must be a whole number"):
        parse({"type": "change_life", "player": "you", "amount": "three"})


def test_true_is_not_a_life_total() -> None:
    """`bool` is an `int` in Python and in no other sense."""
    with pytest.raises(BadEventError, match="'amount' must be a whole number"):
        parse({"type": "change_life", "player": "you", "amount": True})


def test_an_unknown_zone_lists_the_real_ones() -> None:
    # The command zone, which is real in the rules and does not exist here:
    # it arrives with commanders, which this project does not play. "stack"
    # used to be the example, and is a zone now.
    body = {"type": "move_card", "player": "you", "instance_id": "x", "to": "command"}
    with pytest.raises(BadEventError, match="expected one of battlefield, exile"):
        parse(body)


def test_every_event_type_the_engine_has_can_be_sent() -> None:
    """A new Event member with no wire form would be unreachable from a client.

    The union is closed and ``reduce`` is exhaustive over it, so the engine
    would keep type-checking while the app quietly lost the ability to ask for
    it. This is the one place that notices.
    """
    members = {member.__name__ for member in get_args(Event.__value__)}
    assert {_wire_name(name) for name in members} == WIRE_FORMS
    # And the table the parser actually dispatches on says the same, so a name
    # spelled one way in the union and another in `BUILDERS` is caught here
    # rather than by a client getting "unknown event type".
    assert set(BUILDERS) == WIRE_FORMS


def _wire_name(class_name: str) -> str:
    """``PlayLand`` as a client would spell it."""
    return "".join("_" + c.lower() if c.isupper() else c for c in class_name).lstrip("_")
