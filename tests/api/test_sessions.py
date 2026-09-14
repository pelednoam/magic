"""The authoritative game, and the log it is derived from."""

from __future__ import annotations

import pytest

from helpers import ME, YOU, deck
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.core.events import AdvanceStep, ChangeLife
from mtgcoach.core.steps import Step


def _store() -> tuple[SessionStore, str]:
    store = SessionStore()
    session = store.create({ME: deck("m"), YOU: deck("y")}, ME)
    return store, session.session_id


def test_a_new_game_starts_at_the_beginning() -> None:
    store, session_id = _store()
    session = store.get(session_id)
    assert session.state.turn == 1
    assert session.events == ()
    assert session.consistent


def test_each_game_gets_its_own_name() -> None:
    store = SessionStore()
    first = store.create({ME: deck("m"), YOU: deck("y")}, ME)
    second = store.create({ME: deck("m"), YOU: deck("y")}, ME)
    assert first.session_id != second.session_id


def test_an_event_advances_the_game_and_is_kept() -> None:
    store, session_id = _store()
    session = store.record(store.get(session_id).with_event(AdvanceStep()))
    assert session.events == (AdvanceStep(),)
    assert session.state.step is not Step.UNTAP
    assert session.consistent


def test_the_log_is_the_game() -> None:
    """The cached state is a cache; replaying the log has to give the same."""
    store, session_id = _store()
    session = store.get(session_id)
    for _ in range(6):
        session = session.with_event(AdvanceStep())
    session = session.with_event(ChangeLife(ME, -3))
    assert session.consistent
    assert session.state.player(ME).life == 17


def test_undo_takes_back_the_last_event() -> None:
    store, session_id = _store()
    session = store.get(session_id).with_event(ChangeLife(ME, -5))
    assert session.state.player(ME).life == 15
    back = session.undone()
    assert back.state.player(ME).life == 20
    assert back.events == ()
    assert back.consistent


def test_undo_on_a_fresh_game_is_a_no_op() -> None:
    """Not an error: a player pressing undo twice is ordinary."""
    store, session_id = _store()
    session = store.get(session_id)
    assert session.undone() == session


def test_undo_replays_rather_than_inverting() -> None:
    """Two events in, one back: the state has to match a fresh replay of one."""
    store, session_id = _store()
    session = store.get(session_id)
    session = session.with_event(ChangeLife(ME, -5)).with_event(ChangeLife(ME, -2))
    once = session.undone()
    assert once.state.player(ME).life == 15
    assert once.consistent


def test_a_game_that_was_never_started() -> None:
    store = SessionStore()
    with pytest.raises(UnknownSessionError):
        store.get("nope")


def test_recording_replaces_what_was_there() -> None:
    store, session_id = _store()
    store.record(store.get(session_id).with_event(AdvanceStep()))
    assert len(store.get(session_id).events) == 1
