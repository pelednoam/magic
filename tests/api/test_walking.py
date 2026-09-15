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

from dataclasses import replace
from typing import TYPE_CHECKING

from helpers_api import server, talking
from helpers_replay import BEAR, FOREST, NAME, SEED, journalled, recording, serving
from mtgcoach.core.events import PlayLand
from mtgcoach.core.ids import InstanceId, PlayerId
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
    with talking(serving(tmp_path)) as client:
        assert decoded(client.get("/replays").json()) == {"replays": [NAME]}


def test_a_journal_that_is_not_there_is_a_404(tmp_path: Path) -> None:
    with talking(serving(tmp_path)) as client:
        missing = client.get("/replays/never-ran")
        assert missing.status_code == HTTP_NOT_FOUND
        assert "never-ran" in missing.text


def test_a_journal_lists_its_games_without_their_boards(tmp_path: Path) -> None:
    """The list route answers "which game?", which needs no board.

    A twelve-game coached season is several megabytes once every position is
    serialised, and this route is read to choose between three lines of text.
    """
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}").json())
        (game,) = rows(body, "games")
        assert game == {"index": 0, "seed": SEED, "decks": ["green", "other"], "decisions": 3}


def test_a_game_comes_back_as_moments(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}/0").json())
        assert body["seed"] == SEED
        assert body["decks"] == ["green", "other"]
        moments = body["moments"]
        assert isinstance(moments, list)
        assert len(moments) == DECISIONS


def test_a_game_that_is_not_there_is_a_404(tmp_path: Path) -> None:
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        assert client.get(f"/replays/{NAME}/9").status_code == HTTP_NOT_FOUND


def test_a_moment_carries_a_board_shaped_like_a_live_one(tmp_path: Path) -> None:
    """So the app renders a replay with the components it already has.

    A position looks the same whether it is happening now or happened last
    night, which is the whole reason the moment goes out through ``views.state``
    rather than through a shape of its own.
    """
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}/0").json())
        moments = body["moments"]
        assert isinstance(moments, list)
        first = moments[0]
        assert isinstance(first, dict)
        assert first["step"] == str(Step.PRECOMBAT_MAIN)
        assert text(first, "state", "step") == str(Step.PRECOMBAT_MAIN)
        assert first["player"] == "you"
        assert first["trusted"] is True


def test_a_card_in_a_replay_is_named_from_the_catalogue(tmp_path: Path) -> None:
    """A journal holds oracle ids -- Scryfall's UUIDs -- and a board has to read.

    Without the catalogue every card on the walk screen reads
    ``b2c6aa39-...``, and the *same* position one tap later, under "ask about
    this", reads "Forest". This asserts the printed name and that no raw id
    survives, which the fixture's UUID-shaped ids make a real check.
    """
    journalled(tmp_path)
    with talking(serving(tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}/0").json())
        moments = body["moments"]
        assert isinstance(moments, list)
        first = moments[0]
        assert isinstance(first, dict)
        named = {card["name"] for card in rows(first, "state", "players", "you", "hand")}
        assert named == {"Forest", "Grizzly Bears"}


def test_a_replay_of_a_set_this_server_lacks_shows_the_id(tmp_path: Path) -> None:
    """The honest fallback, and the reason the catalogue is safe to use here.

    A journal can be from a set this server never imported. Saying "this is a
    card I cannot name" beats an empty space, which a player reads as a bug.
    """
    journalled(tmp_path)
    with talking(server(data_root=tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}/0").json())
        moments = body["moments"]
        assert isinstance(moments, list)
        first = moments[0]
        assert isinstance(first, dict)
        named = {card["name"] for card in rows(first, "state", "players", "you", "hand")}
        assert named == {FOREST, BEAR}


def test_a_damaged_game_does_not_shift_the_ones_after_it(tmp_path: Path) -> None:
    """A game is addressed by where it is in the file, not in the answer.

    The list route hands out file positions. Leaving a damaged game out of the
    answer while numbering by position in the answer made those two disagree,
    so `at/2` opened game 1 and `at/1` was a 404 -- silently showing one game
    under another game's name, which is the failure this whole format exists
    to prevent.
    """
    path = journalled(tmp_path)
    broken = replace(recording(), seed=8, events=(PlayLand(PlayerId("you"), InstanceId("nobody")),))
    with path.open("a", encoding="utf-8") as file:
        file.write(broken.as_json() + "\n")
        file.write(replace(recording(), seed=9).as_json() + "\n")

    with talking(serving(tmp_path)) as client:
        body = decoded(client.get(f"/replays/{NAME}").json())
        listed = {row["index"]: row["seed"] for row in rows(body, "games")}
        assert listed == {0: SEED, 2: 9}
        # Every index the list gave out opens the game the list named.
        for index, seed in listed.items():
            got = decoded(client.get(f"/replays/{NAME}/{index}").json())
            assert got["seed"] == seed
        # And the one it did not give out is honestly missing.
        assert client.get(f"/replays/{NAME}/1").status_code == HTTP_NOT_FOUND
