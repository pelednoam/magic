# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""The server's JSON and the app's types, checked against each other.

Both are written by hand, which is the right call -- the wire is a contract two
sides agreed on, not a dump of either's internals -- and it means the two can
drift apart silently. The failure that causes is a blank space in the UI, found
at the kitchen table rather than in CI.

So this builds a real snapshot from the real views and reads
``apps/mobile/src/wire/``, in both directions: a field the server sends that
the app has never heard of, and a field the app declares that the server no
longer sends. Either is a bug; neither raises anything at runtime.
"""

from __future__ import annotations

import pytest

from wirecorners import finished, replayed
from wirefields import DYNAMIC_KEYS, declared, wire_files
from wireturn import a_whole_turn


@pytest.fixture(scope="module")
def sent(tmp_path_factory: pytest.TempPathFactory) -> frozenset[str]:
    """Every field the server sends anywhere, across every shape it can send.

    One payload cannot carry the whole shape: attack plans exist only in the
    declare-attackers step, reminders only at an upkeep, the stack's own fields
    only while a spell is waiting, and a permanent is only `tapped` once
    something has tapped it. So the three walks in ``wirecorners`` union what
    they see -- which is also the honest question, since the contract is "what
    does this server ever send", not "what is in one response".
    """
    return frozenset(a_whole_turn() | replayed(tmp_path_factory.mktemp("data")) | finished())


def test_the_app_knows_every_field_the_server_sends(sent: frozenset[str]) -> None:
    """A field the app has never heard of is a blank space in the UI."""
    assert (sent - DYNAMIC_KEYS) - declared() == set()


def test_the_server_sends_every_field_the_app_declares(sent: frozenset[str]) -> None:
    """A field the app expects and no longer gets is the same bug, mirrored."""
    assert declared() - sent == set()


def test_the_wire_folder_is_where_it_is_thought_to_be() -> None:
    """A moved or renamed module would make both checks vacuously pass."""
    assert wire_files() == [
        "board.ts",
        "claude.ts",
        "game.ts",
        "index.ts",
        "replay.ts",
        "shapes.ts",
    ]


def test_the_turn_actually_covers_the_payload(sent: frozenset[str]) -> None:
    """Guard on the guard: a turn that reached nothing would check nothing."""
    corners = {
        "tapped",
        "they_lose",
        "tap",
        "keep",
        "event",
        "payment",
        "unknown",
        "check_yourself",
        "citations",
        "reference",
        # The replay routes, whose shape is only reached through a journal.
        "replays",
        "games",
        "moments",
        "problems",
        "error",
        "trusted",
        "decisions",
        "index",
        # A game that ended, which only a game played to a conclusion reaches.
        "over",
        "lost",
        "why",
        "winner",
        "drawn",
    }
    assert corners <= sent
