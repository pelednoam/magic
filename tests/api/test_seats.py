# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright, and what is read here is read for its shape rather than through
# ``wire``.

"""Which player a token is, and what it may therefore do.

`test_access` covers the door -- whether a request gets in at all. This is who
came through it, which was not a question while there was one token for the
whole server. `test_hidden` is the other consequence: what each device is then
*sent*.

The hole this closes was demonstrable in four lines. One device, holding the
only token, could post `{"type": "change_life", "player": "them", "amount": -5}`
and take five life off the other player. Nothing checked the `player` field
against anything, because there was nothing to check it against -- and the
second device is the one the child holds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from helpers_api import MINE, OTHER_TOKEN, THEIRS, TOKEN, server, talking
from helpers_coach import game
from mtgcoach.api.gatekeeper import SEAT, UnseatedError, seat_of
from mtgcoach.api.seats import seated_in
from mtgcoach.api.sessions import Session
from wire import decoded, text

if TYPE_CHECKING:
    from fastapi import FastAPI

HTTP_OK = 200
HTTP_FORBIDDEN = 403

#: The decks a test game is dealt, keyed by the seat that gets them.
DEAL = {"you": "green", "them": "other"}


def _started(app: FastAPI) -> str:
    """A game, started by the seat `TOKEN` names."""
    with talking(app) as client:
        return text(decoded(client.post("/games", json=DEAL).json()), "session_id")


# --- both tokens are credentials, and the gate says which ---------------------


def test_either_seat_s_token_opens_the_door() -> None:
    """Both are real credentials. The seat is an identity, not a rank."""
    app = server()
    for token in (TOKEN, OTHER_TOKEN):
        with talking(app, token=token) as client:
            assert client.get("/decks").status_code == HTTP_OK


def test_a_handler_outside_the_gate_cannot_be_told_a_seat() -> None:
    """It raises rather than guessing.

    Not something a client can cause -- every route of a `guarded` app is
    behind the middleware. It is what an app assembled without the gate looks
    like, and defaulting to a seat would hand somebody one nobody authenticated
    as.
    """
    with pytest.raises(UnseatedError, match="not authenticated"):
        seat_of({})


def test_the_scope_key_is_where_it_is_thought_to_be() -> None:
    """The gate writes it and `seat_of` reads it; nothing else may.

    A rename on one side only would leave every route reading a key nobody
    writes, which `seat_of` turns into a raise -- but this says so here rather
    than by fifty failures elsewhere.
    """
    assert seat_of({SEAT: "you"}) == "you"


# --- an event may only name the seat that sent it ------------------------------


def test_a_device_cannot_send_an_event_for_the_other_seat() -> None:
    """The hole, as it was: one token, either player's actions."""
    app = server()
    game = _started(app)
    with talking(app) as client:
        refused = client.post(
            f"/games/{game}/events",
            json={"type": "change_life", "player": THEIRS, "amount": -5},
        )
    assert refused.status_code == HTTP_FORBIDDEN
    assert THEIRS in refused.json()["detail"]


def test_the_other_players_life_is_untouched_by_the_attempt() -> None:
    """A refusal that changed the game would be worse than no refusal."""
    app = server()
    game = _started(app)
    with talking(app) as client:
        client.post(
            f"/games/{game}/events",
            json={"type": "change_life", "player": THEIRS, "amount": -5},
        )
        board = client.get(f"/games/{game}").json()
    assert board["state"]["players"][THEIRS]["life"] == 20


def test_each_seat_may_send_its_own_events() -> None:
    """Both tokens are real credentials for the seat they name."""
    app = server()
    game = _started(app)
    for token, seat in ((TOKEN, MINE), (OTHER_TOKEN, THEIRS)):
        with talking(app, token=token) as client:
            sent = client.post(
                f"/games/{game}/events",
                json={"type": "change_life", "player": seat, "amount": -1},
            )
        assert sent.status_code == HTTP_OK, seat


def test_ending_a_step_is_not_anybody_s_action() -> None:
    """`advance_step` names no player and either device may send it.

    A step in which players receive priority ends when every player has passed
    in succession on an empty stack (CR 117.4), so it is a consequence rather
    than a move -- and `core.priority` refuses it until they have. The passes
    it needs are seated events and are checked like any other.
    """
    app = server()
    game = _started(app)
    with talking(app, token=OTHER_TOKEN) as client:
        sent = client.post(f"/games/{game}/events", json={"type": "advance_step"})
    assert sent.status_code == HTTP_OK


# --- the routes that ask a model -------------------------------------------


def test_a_device_cannot_ask_the_coach_about_the_other_seat() -> None:
    """The briefing names every card in the hand it is about.

    So a request that could name the other seat was a way to read their hand
    out of a model's answer, one `{"player": "them"}` away.
    """
    app = server()
    game = _started(app)
    with talking(app) as client:
        refused = client.post(f"/games/{game}/coach", json={"player": THEIRS})
    assert refused.status_code == HTTP_FORBIDDEN


def test_a_device_cannot_ask_a_rules_question_as_the_other_seat() -> None:
    """The same, for the route that quotes the printed text of a hand."""
    app = server()
    game = _started(app)
    with talking(app) as client:
        refused = client.post(
            f"/games/{game}/ask", json={"player": THEIRS, "question": "what is trample?"}
        )
    assert refused.status_code == HTTP_FORBIDDEN


# --- a seat that is not a player in this game ---------------------------------


def test_a_seat_that_is_not_a_player_in_this_game_is_refused() -> None:
    """Which a game adopted from somebody else's journal really can be.

    Every game this server *deals* has both of `SEATS` in it, so nothing in
    ordinary play reaches this. A replay's moment is adopted as a game with
    whatever seats that journal used, and advising a player who is not there
    must not be a 500 -- or, worse, an answer about nobody.
    """
    state = game()
    with pytest.raises(HTTPException) as refused:
        seated_in(Session("x", initial=state, events=(), state=state), THEIRS)
    assert refused.value.status_code == HTTP_FORBIDDEN
    assert "not you" in str(refused.value.detail)
