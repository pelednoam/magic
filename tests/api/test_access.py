# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright. Nothing read here is narrowed by ``wire`` because nothing read here
# is a payload -- these are status codes and headers.

"""Who this server will talk to.

§4 puts it on one LAN with two devices, and PLAN.md carried "the API is
unauthenticated" as a known gap from M5 until now. The thing it actually
closes is not a guest's phone -- it is a web page the household visits, which
could make cross-origin requests to the laptop and did not previously need to
know anything to drive the game or spend the operator's subscription.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from helpers_api import CATALOGUE, DECKS, TOKEN, NoAnswers, NoCoach, server, talking
from mtgcoach.api.access import (
    MissingTokenError,
)
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from mtgcoach.api.gatekeeper import REFUSAL

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
WS_POLICY_VIOLATION = 1008


def _unguarded() -> TestClient:
    """A client with no token at all, as a stranger would have."""
    return TestClient(server())


# --- the door -----------------------------------------------------------------


def test_a_request_with_no_token_is_refused() -> None:
    response = _unguarded().get("/decks")
    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.json()["detail"] == REFUSAL


def test_a_request_with_the_wrong_token_is_refused() -> None:
    with talking(server(), token="not-it") as client:  # noqa: S106 - the point of the test
        assert client.get("/decks").status_code == HTTP_UNAUTHORIZED


def test_a_request_with_the_token_is_let_through() -> None:
    with talking(server()) as client:
        assert client.get("/decks").status_code == HTTP_OK


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/decks"),
        ("post", "/games"),
        ("get", "/games/nope"),
        ("post", "/games/nope/events"),
        ("post", "/games/nope/undo"),
        ("post", "/games/nope/coach"),
        ("post", "/games/nope/ask"),
    ],
)
def test_every_route_is_behind_the_door(method: str, path: str) -> None:
    """True by construction, not by remembering.

    Middleware rather than a per-route dependency, so it holds for a route
    added next month too.
    """
    client = _unguarded()
    response = client.request(method.upper(), path, json={})
    assert response.status_code == HTTP_UNAUTHORIZED, path


def test_the_refusal_says_nothing_about_the_token() -> None:
    """Not its length, and not how close the attempt was."""
    with talking(server(), token="x") as client:  # noqa: S106 - the point of the test
        said = client.get("/decks").json()["detail"]
    assert TOKEN not in said
    assert str(len(TOKEN)) not in said


def test_a_refusal_still_carries_cors_headers() -> None:
    """Or the browser reports an opaque cross-origin error instead.

    The app would then never see the 401 it needs in order to ask for a token.
    """
    response = _unguarded().get("/decks", headers={"Origin": "http://localhost:8081"})
    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers.get("access-control-allow-origin") == "*"


def test_a_preflight_is_answered_without_a_token() -> None:
    """A preflight cannot be carrying the header it is asking permission for.

    Refusing it would refuse the request that follows.
    """
    response = _unguarded().options(
        "/games",
        headers={"Origin": "http://localhost:8081", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == HTTP_OK


# --- the socket, which a browser cannot put a header on -----------------------


def test_the_socket_accepts_the_token_in_the_query_string() -> None:
    """A page cannot set headers on a WebSocket handshake.

    So the URL carries it, which is a real if small cost: a query string
    reaches logs and browser history in a way a header does not.
    """
    # One app, so the game the socket asks for is the game that was started.
    app = server()
    with talking(app) as client:
        started = client.post("/games", json={"you": "green", "them": "other"}).json()
    stranger = TestClient(app)
    with stranger.websocket_connect(
        f"/games/{started['session_id']}/watch?token={TOKEN}"
    ) as socket:
        assert "state" in socket.receive_json()


def test_the_socket_is_closed_when_no_token_is_given() -> None:

    stranger = _unguarded()
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        stranger.websocket_connect("/games/nope/watch"),
    ):
        pass
    assert closed.value.code == WS_POLICY_VIOLATION


def test_the_socket_is_closed_when_the_token_is_wrong() -> None:

    stranger = _unguarded()
    with (
        pytest.raises(WebSocketDisconnect),
        stranger.websocket_connect("/games/nope/watch?token=not-it"),
    ):
        pass


# --- there is no open mode ----------------------------------------------------


def test_a_server_cannot_be_built_without_a_token() -> None:
    """There is no open mode.

    An argument that can be left out is an argument that gets left out, and
    this one is the whole of the server's access control.
    """
    with pytest.raises(MissingTokenError, match="no open mode"):
        create_app(CATALOGUE, DECKS, "", Claude(NoCoach(), NoAnswers()))
