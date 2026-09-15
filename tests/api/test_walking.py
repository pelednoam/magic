# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module, like every
# other test that drives a real client: everything it returns is narrowed by
# ``wire`` before anything is asserted about it.

"""The three routes that make a played game something you can walk.

The third is the one that makes it teaching rather than a log viewer: stepping
into a moment adopts its board as a real game, so the question box, the coach
and the board all work on a position out of last night's game without a single
one of them knowing it came from a replay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import server, talking
from helpers_replay import NAME, SEED, journalled
from mtgcoach.core.steps import Step
from wire import decoded, rows, text

if TYPE_CHECKING:
    from pathlib import Path

HTTP_OK = 200
HTTP_NOT_FOUND = 404

#: How many decisions the fixture journal holds.
DECISIONS = 3

#: Not the server's token.
WRONG = "not-the-token"


def test_a_server_with_no_data_root_has_no_replays() -> None:
    """An honest empty list rather than a 500. Running without one is normal."""
    with talking(server()) as client:
        assert decoded(client.get("/replays").json()) == {"replays": []}


def test_a_server_with_no_data_root_cannot_show_one() -> None:
    with talking(server()) as client:
        assert client.get(f"/replays/{NAME}").status_code == HTTP_NOT_FOUND


def test_the_journals_are_listed(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        assert decoded(client.get("/replays").json()) == {"replays": [NAME]}


def test_a_journal_that_is_not_there_is_a_404(tmp_path: Path) -> None:
    with talking(server(data_root=tmp_path)) as client:
        missing = client.get("/replays/never-ran")
        assert missing.status_code == HTTP_NOT_FOUND
        assert "never-ran" in missing.text


def test_a_game_comes_back_as_moments(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}").json())
        (game,) = rows(body, "games")
        assert game["seed"] == SEED
        assert game["decks"] == ["green", "other"]
        moments = game["moments"]
        assert isinstance(moments, list)
        assert len(moments) == DECISIONS


def test_a_moment_carries_a_board_shaped_like_a_live_one(tmp_path: Path) -> None:
    """So the app renders a replay with the components it already has.

    A position looks the same whether it is happening now or happened last
    night, which is the whole reason the moment goes out through ``views.state``
    rather than through a shape of its own.
    """
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}").json())
        (game,) = rows(body, "games")
        moments = game["moments"]
        assert isinstance(moments, list)
        first = moments[0]
        assert isinstance(first, dict)
        assert first["step"] == str(Step.PRECOMBAT_MAIN)
        assert text(first, "state", "step") == str(Step.PRECOMBAT_MAIN)
        assert first["player"] == "you"
        assert first["trusted"] is True


def test_a_card_in_a_replay_is_named(tmp_path: Path) -> None:
    """A journal carries no catalogue, and the board still has to read.

    The oracle id is shown as the name, which for this project *is* the name --
    the importer uses it as the identifier. A blank card would be worse than an
    unadorned one.
    """
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}").json())
        (game,) = rows(body, "games")
        moments = game["moments"]
        assert isinstance(moments, list)
        first = moments[0]
        assert isinstance(first, dict)
        named = {card["name"] for card in rows(first, "state", "players", "you", "hand")}
        assert "Forest" in named


def test_stepping_into_a_moment_makes_a_game(tmp_path: Path) -> None:
    """The point of the whole screen.

    From here it is an ordinary session, so every route that already exists
    answers about turn seven's board rather than about a board like it.
    """
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        stepped = client.post(f"/replays/{NAME}/{SEED}/at/0")
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
    with talking(server(data_root=tmp_path)) as client:
        assert client.post(f"/replays/{NAME}/999/at/0").status_code == HTTP_NOT_FOUND


def test_stepping_past_the_end_of_a_game(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        assert client.post(f"/replays/{NAME}/{SEED}/at/99").status_code == HTTP_NOT_FOUND


def test_stepping_into_a_journal_that_is_not_there(tmp_path: Path) -> None:
    with talking(server(data_root=tmp_path)) as client:
        assert client.post(f"/replays/never-ran/{SEED}/at/0").status_code == HTTP_NOT_FOUND


def test_stepping_in_needs_a_token(tmp_path: Path) -> None:
    """The replay routes are behind the same door as everything else."""
    journalled(tmp_path)
    with talking(server(data_root=tmp_path), token=WRONG) as client:
        assert client.get("/replays").status_code != HTTP_OK
