# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module, like every
# other test that drives a real client.

"""Stepping into a moment of a played game, which is what makes it teaching.

Split from ``test_walking`` at the line limit, and the seam is a real one: that
file is about reading a journal over HTTP, this one is about the route that
turns one moment of it into an ordinary session -- after which the question
box, the coach and the board all work on a position out of last night's game
without a single one of them knowing where it came from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import talking
from helpers_journal import journalled, serving
from helpers_replay import NAME
from mtgcoach.core.steps import Step
from wire import decoded, rows, text

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404

#: Not the server's token.
WRONG = "not-the-token"


def test_stepping_into_a_moment_makes_a_game(tmp_path: Path) -> None:
    """The point of the whole screen.

    From here it is an ordinary session, so every route that already exists
    answers about turn seven's board rather than about a board like it.
    """
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        stepped = client.post(f"/replays/{NAME}/0/at/0")
        assert stepped.status_code == HTTP_OK, stepped.text
        body = decoded(stepped.json())
        session_id = body["session_id"]
        assert isinstance(session_id, str)
        assert text(body, "state", "step") == str(Step.PRECOMBAT_MAIN)

        # And the engine advises on it, which is what proves it is a real game
        # rather than a picture of one.
        looked = decoded(client.get(f"/games/{session_id}").json())
        assert text(looked, "state", "step") == str(Step.PRECOMBAT_MAIN)
        assert len(rows(looked, "advice", "you", "hand")) > 0


def test_stepping_into_a_game_that_is_not_there(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        assert client.post(f"/replays/{NAME}/9/at/0").status_code == HTTP_NOT_FOUND


def test_stepping_past_the_end_of_a_game(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        assert client.post(f"/replays/{NAME}/0/at/99").status_code == HTTP_NOT_FOUND


def test_stepping_into_a_journal_that_is_not_there(tmp_path: Path) -> None:
    with talking(serving(tmp_path)) as client:
        assert client.post("/replays/never-ran/0/at/0").status_code == HTTP_NOT_FOUND


def test_stepping_in_needs_a_token(tmp_path: Path) -> None:
    """The replay routes are behind the same door as everything else."""
    journalled(tmp_path)
    with talking(serving(tmp_path), token=WRONG) as client:
        assert client.get("/replays").status_code != HTTP_OK
