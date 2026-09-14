"""The real thing, assembled once for every end-to-end test.

No fakes below the HTTP client. The cards come out of the real Scryfall reader
into the real SQLite store; their behaviour comes out of the real sealed FDN
fixture that a person signed; the rules are the real engine; the advice is the
real coach; and it is all reached over real HTTP and a real WebSocket.

The unit tests say each piece is right. This says they are the *same* pieces --
that an oracle id written by the extractor is the one the store hands back, that
a ``{T}: Add {G}`` a model proposed and a human accepted becomes a Forest the
mana solver will tap, and that the whole path holds together when a person
actually plays a turn with it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from helpers_api import TOKEN, NoCoach, talking
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import build
from mtgcoach.api.context import Claude
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient

    from mtgcoach.api.cards import Catalogue


REPO = Path(__file__).resolve().parent.parent.parent
CARDS = REPO / "tests" / "fixtures" / "scryfall_fdn_playable.json"
EFFECTS = REPO / "data" / "sets" / "FDN" / "effects.json"

FOREST = "b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6"
ELVES = "68954295-54e3-4303-a6bc-fc4547a4e3a3"
DRUID = "b1793c3b-25d6-4fae-a99d-cfdd2210ca67"
LIONS = "60ba93eb-39e6-4af2-9c66-cd38f72daff2"
GROWTH = "5748ebf1-24e3-499d-ab7c-c2cebd462a24"
PLAINS = "bc71ebf6-2056-41f7-be35-b2e5c34afa99"

#: The opening seven are the first seven, so this is the hand every test starts
#: with: three Forests, the Elves, a Druid, a Growth and one more Forest.
GREEN = (FOREST, FOREST, FOREST, ELVES, DRUID, GROWTH, FOREST, FOREST, DRUID, FOREST)
WHITE = (PLAINS, PLAINS, PLAINS, LIONS, LIONS, PLAINS, PLAINS, PLAINS, LIONS, PLAINS)

HTTP_OK = 200
HTTP_BAD_REQUEST = 400


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    """The real Foundations cards, read the way the real server reads them."""
    with CardStore.open() as store:
        store.add((card, SetCode("FDN")) for card in cards_in(CARDS))
        return build(store.cards_in_set(SetCode("FDN")), EFFECTS)


@pytest.fixture(scope="module")
def client(catalogue: Catalogue) -> Iterator[TestClient]:
    """A server holding the real card data, over a real store.

    The explainer is the one that refuses: everything below it is real, and a
    test that reached the actual ``claude`` command would be slow, would cost
    quota, and would pass or fail for reasons this repository does not control.
    ``test_coaching`` supplies its own.
    """
    app = create_app(catalogue, {"green": GREEN, "white": WHITE}, TOKEN, Claude(NoCoach()))
    with talking(app) as connected:
        yield connected
