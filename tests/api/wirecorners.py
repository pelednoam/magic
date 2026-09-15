# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""The two payload shapes one played turn never reaches.

``test_wire_contract`` plays a turn and unions every field it sees. Two shapes
are not in a turn: a *replay*, which needs a journal on disk, and a game that
has *ended*, which needs one player out. Both are in the contract, so both have
to be walked -- and a contract test that never finished a game would have
declared `over` covered while only ever seeing null.

Split out of that module at the line limit; it is the same test, in two files.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import server, talking
from helpers_replay import NAME, journalled, serving
from mtgcoach.core.player import STARTING_LIFE
from wire import decoded, text
from wirefields import keys

if TYPE_CHECKING:
    from pathlib import Path

#: The status the server returns when an event was accepted.
HTTP_OK = 200


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
        stepped = client.post(f"/replays/{NAME}/0/at/0")
        assert stepped.status_code == HTTP_OK, stepped.text
        found.update(keys(decoded(stepped.json())))
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
        # where CR 704.5a is checked.
        for event in (
            {"type": "change_life", "player": "you", "amount": -STARTING_LIFE},
            {"type": "advance_step"},
        ):
            sent = client.post(f"/games/{session}/events", json=event)
            assert sent.status_code == HTTP_OK, sent.text
            found.update(keys(decoded(sent.json())))
        body = decoded(client.get(f"/games/{session}").json())
        assert text(body, "state", "over", "winner") == "them"
    return found
