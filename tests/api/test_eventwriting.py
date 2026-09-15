"""An event written down and read back, which is what a recorded game rests on.

Split from ``test_eventspec`` at the line limit: that file is about refusing a
client's bad JSON, this one is about the round trip.

A journal keeps the event log; a replay parses it back and folds it over the
opening board. If those two halves disagreed about a single field, the board a
child is shown stepping through a game would not be the board that was played
-- silently, because both halves would still be valid JSON.
"""

from __future__ import annotations

from typing import get_args

import pytest

from mtgcoach.api.eventfields import BadEventError
from mtgcoach.api.eventspec import parse, written
from mtgcoach.core.events import (
    AdvanceStep,
    CastSpell,
    ChangeLife,
    DrawCard,
    Event,
    MoveCard,
    PlayLand,
    ResolveSpell,
    SetTapped,
)
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.zones import ZoneName

#: One of every event, for the round trip. Built with real values rather than
#: defaults so a field dropped on the way out is visible on the way back.
EVERY_EVENT: tuple[Event, ...] = (
    AdvanceStep(),
    DrawCard(PlayerId("you")),
    PlayLand(PlayerId("you"), InstanceId("card-1")),
    CastSpell(PlayerId("you"), InstanceId("card-4")),
    ResolveSpell(PlayerId("you"), InstanceId("card-5"), ZoneName.GRAVEYARD),
    SetTapped(PlayerId("them"), InstanceId("card-2"), tapped=True),
    MoveCard(PlayerId("you"), InstanceId("card-3"), ZoneName.GRAVEYARD),
    ChangeLife(PlayerId("them"), -3),
)


@pytest.mark.parametrize("event", EVERY_EVENT)
def test_an_event_survives_being_written_down_and_read_back(event: Event) -> None:
    """The property a recorded game depends on.

    A journal keeps the event log; a replay parses it back and folds it over
    the opening board. If those two disagree about a single field, the board a
    child is shown is not the board that was played -- silently, because both
    halves would still be valid JSON.
    """
    assert parse(written(event)) == event


def test_every_event_can_be_written_down() -> None:
    """Guard on the guard: a new event with no round trip above."""
    assert {type(event) for event in EVERY_EVENT} == set(get_args(Event.__value__))


def test_casting_and_resolving_are_two_events() -> None:
    """Because they are two things, with a gap between them.

    The gap is where a player may answer a spell. Nothing can yet -- that needs
    priority (CR 117) -- but modelling the gap away is what put an Opt on the
    battlefield for the rest of a game.
    """
    cast = parse({"type": "cast_spell", "player": "you", "instance_id": "you-3"})
    assert cast == CastSpell(PlayerId("you"), InstanceId("you-3"))
    body = {"type": "resolve_spell", "player": "you", "instance_id": "you-3", "to": "graveyard"}
    assert parse(body) == ResolveSpell(PlayerId("you"), InstanceId("you-3"), ZoneName.GRAVEYARD)


def test_resolving_needs_somewhere_to_go() -> None:
    """The destination is the client's to supply: `core` cannot read a type line."""
    with pytest.raises(BadEventError, match="'to'"):
        parse({"type": "resolve_spell", "player": "you", "instance_id": "you-3"})


def test_a_payment_must_be_a_list() -> None:
    """A client that sent a single id rather than a list of them."""
    body = {"type": "cast_spell", "player": "you", "instance_id": "x", "payment": "land-1"}
    with pytest.raises(BadEventError, match="'payment' must be a list"):
        parse(body)


@pytest.mark.parametrize("bad", [["land-1", 7], ["land-1", ""], [None]])
def test_a_payment_must_be_non_empty_strings(bad: list[object]) -> None:
    """Refused whole rather than trimmed.

    A payment with one element quietly dropped is a different payment, and it
    is a *cheaper* one -- so trimming would turn a malformed request into a
    spell cast for less than it costs.
    """
    body = {"type": "cast_spell", "player": "you", "instance_id": "x", "payment": bad}
    with pytest.raises(BadEventError, match="non-empty strings"):
        parse(body)


def test_a_cast_with_no_payment_is_a_free_one() -> None:
    """Absent is empty: a spell that costs nothing, or an older recording."""
    assert parse({"type": "cast_spell", "player": "you", "instance_id": "x"}) == CastSpell(
        PlayerId("you"), InstanceId("x")
    )
