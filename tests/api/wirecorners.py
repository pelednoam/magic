# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""The two payload shapes one played turn never reaches.

``wireturn`` plays a turn and unions every field it sees. Two shapes are not in
a turn: a *replay*, which needs a journal on disk, and a game that has *ended*,
which needs one player out. Both are in the contract, so both have to be walked
-- and a contract test that never finished a game would have declared `over`
covered while only ever seeing null.

Split out of ``test_wire_contract`` at the line limit; it is all the same test,
across four files, and that one is where the two sets get compared.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from driving import HTTP_OK, stepped
from helpers_api import server, talking
from helpers_journal import journalled, serving
from helpers_replay import NAME
from mtgcoach.core.player import STARTING_LIFE
from wire import decoded, text
from wirefields import keys

if TYPE_CHECKING:
    from pathlib import Path


def replayed(data_root: Path) -> set[str]:
    """Every field the three replay routes send.

    A separate server because these need a data root, and a separate journal
    because what they send depends on what is in it -- a game with an untrusted
    answer and a refused one in it, so `problems` and `error` are populated
    rather than merely present.
    """
    journalled(data_root)
    found: set[str] = set()
    with talking(serving(data_root)) as client:
        found.update(keys(decoded(client.get("/replays").json())))
        for path in (f"/replays/{NAME}", f"/replays/{NAME}/0"):
            got = client.get(path)
            assert got.status_code == HTTP_OK, got.text
            found.update(keys(decoded(got.json())))
        moment = client.post(f"/replays/{NAME}/0/at/0")
        assert moment.status_code == HTTP_OK, moment.text
        found.update(keys(decoded(moment.json())))
    return found


def finished() -> set[str]:
    """Every field a game that has *ended* sends.

    Its own game, played to a real conclusion, because the result fields exist
    only once one player is out -- and a contract test that never finished a
    game would declare `over` covered while only ever seeing null.
    """
    found: set[str] = set()
    with talking(server()) as client:
        created = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
        session = created["session_id"]
        assert isinstance(session, str)
        # Twenty life, gone. Then one step, which is the priority boundary
        # where CR 704.5a is checked -- and ending a step takes both players
        # passing first (CR 500.2), so `stepped` sends all three events.
        sent = client.post(
            f"/games/{session}/events",
            json={"type": "change_life", "player": "you", "amount": -STARTING_LIFE},
        )
        assert sent.status_code == HTTP_OK, sent.text
        found.update(keys(decoded(sent.json())))
        found.update(keys(stepped(client, session)))
        body = decoded(client.get(f"/games/{session}").json())
        assert text(body, "state", "over", "winner") == "them"
    return found
