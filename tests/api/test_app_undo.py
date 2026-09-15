# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Everything read here is narrowed by
# ``wire``.

"""Taking an event back, and the number that says which board is newer.

Split from `test_app` at the length limit, and the seam is a real one: these
four are about *time* -- undo is a replay of the log minus its tail, and
`version` is the only ordering a client has, because an HTTP reply and a socket
broadcast arrive in whatever order the network chooses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import server, talking
from wire import decoded, number

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_NOT_FOUND = 404


def _new_game(client: TestClient) -> str:
    response = client.post("/games", json={"you": "green", "them": "other"})
    assert response.status_code == HTTP_OK
    session_id: str = response.json()["session_id"]
    return session_id


def test_undo_takes_the_last_event_back() -> None:
    with talking(server()) as client:
        session_id = _new_game(client)
        client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -3},
        )
        body = client.post(f"/games/{session_id}/undo").json()
        assert number(body, "state", "players", "you", "life") == 20


def test_undo_on_a_game_that_does_not_exist() -> None:
    with talking(server()) as client:
        assert client.post("/games/nope/undo").status_code == HTTP_NOT_FOUND


def test_the_version_only_ever_goes_up() -> None:
    """It is the client's only ordering, and undo is a change like any other.

    Counting *events* made it go backwards on undo -- and the client keeps a
    snapshot unless the new one is at least as new, so it discarded every undo
    and undo silently did nothing. This test used to pin that: it asserted the
    undo snapshot came back as 0.
    """
    with talking(server()) as client:
        session_id = _new_game(client)
        seen = [number(decoded(client.get(f"/games/{session_id}").json()), "version")]
        seen.append(
            number(
                decoded(
                    client.post(
                        f"/games/{session_id}/events",
                        json={"type": "change_life", "player": "you", "amount": -1},
                    ).json()
                ),
                "version",
            )
        )
        seen.append(number(decoded(client.post(f"/games/{session_id}/undo").json()), "version"))
        assert seen == sorted(seen), f"versions went backwards: {seen}"
        assert len(set(seen)) == len(seen), f"two states shared a version: {seen}"


def test_an_undo_is_newer_than_the_event_it_undid() -> None:
    """Otherwise the client cannot tell the undo from the thing being undone."""
    with talking(server()) as client:
        session_id = _new_game(client)
        after = decoded(
            client.post(
                f"/games/{session_id}/events",
                json={"type": "change_life", "player": "you", "amount": -1},
            ).json()
        )
        undone = decoded(client.post(f"/games/{session_id}/undo").json())
        assert number(undone, "version") > number(after, "version")
        assert number(undone, "state", "players", "you", "life") == 20
