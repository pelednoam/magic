# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright, and everything read out of it here is narrowed by ``wire``.

"""The coach route, with the model replaced by a canned answer.

The route's job is not to be clever -- it is to be the one place an answer can
reach a client, so that the check in ``coaching`` cannot be gone round. These
tests are about that: a good answer arrives, a made-up one is replaced by the
refusal, and no answer at all is a 503 rather than a broken page.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers import facts
from helpers_api import BEAR, FOREST, TOKEN, Canned, NoAnswers, server, talking
from helpers_coach import taps_for
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue
from mtgcoach.api.context import Claude
from mtgcoach.coach.advice import Explanation
from wire import flag, named, obj, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503

#: Untap, upkeep, draw -- then a main phase, where a land can be played.
STEPS_TO_MAIN = 4

SENSIBLE = Explanation(
    because="A land is free and you have nothing else to do.",
    in_short="Put down a land.",
)


def _game(client: TestClient) -> str:
    body = client.post("/games", json={"you": "green", "them": "other"}).json()
    session_id: str = body["session_id"]
    return session_id


def _land_in_hand(client: TestClient, session_id: str) -> str:
    """The instance id of a card the engine says can be played.

    A game starts at untap, where nothing can be played, so this walks the turn
    forward to the first step that offers a choice -- which is the main phase,
    and is also where a player would ever tap the button.
    """
    for _ in range(STEPS_TO_MAIN):
        body = client.get(f"/games/{session_id}").json()
        hand = rows(obj(obj(body, "advice"), "you"), "hand")
        playable = [card for card in hand if flag(card, "playable")]
        if playable:
            return text(playable[0], "instance_id")
        client.post(f"/games/{session_id}/events", json={"type": "advance_step"})
    msg = "nothing became playable"
    raise AssertionError(msg)


def test_an_answer_the_engine_agrees_with_is_passed_on() -> None:
    with talking(server(explainer=Canned(SENSIBLE))) as client:
        session_id = _game(client)
        response = client.post(f"/games/{session_id}/coach", json={"player": "you"})
        assert response.status_code == HTTP_OK
        body = response.json()
        assert flag(body, "trusted")
        assert text(obj(body, "explanation"), "in_short") == "Put down a land."


def test_a_recommendation_is_returned_as_the_instance_id_it_was_given() -> None:
    """The client keys its own list on these, so they have to survive intact."""
    coach = Canned(SENSIBLE)
    with talking(server(explainer=coach)) as client:
        session_id = _game(client)
        wanted = _land_in_hand(client, session_id)
        coach.said = Explanation(play=wanted, because="Play the land.", in_short="Land.")
        body = client.post(f"/games/{session_id}/coach", json={"player": "you"}).json()
        assert flag(body, "trusted")
        assert text(obj(body, "explanation"), "play") == wanted


def test_an_invented_card_is_refused_rather_than_shown() -> None:
    """The whole point of the layer, exercised through the route."""
    said = Explanation(play="not-a-card", because="Cast the dragon.", in_short="Dragon!")
    with talking(server(explainer=Canned(said))) as client:
        session_id = _game(client)
        response = client.post(f"/games/{session_id}/coach", json={"player": "you"})
        assert response.status_code == HTTP_OK
        body = response.json()
        assert not flag(body, "trusted")
        explanation = obj(body, "explanation")
        assert "Dragon" not in text(explanation, "in_short")
        assert "disagreed with the rules engine" in text(explanation, "because")
        assert any("not in hand" in problem for problem in words(explanation, "watch_out"))


def test_an_invented_attack_is_refused() -> None:
    said = Explanation(attack=("ghost",), because="Swing.", in_short="Attack!")
    with talking(server(explainer=Canned(said))) as client:
        session_id = _game(client)
        body = client.post(f"/games/{session_id}/coach", json={"player": "you"}).json()
        assert not flag(body, "trusted")


def test_no_coach_is_a_503_and_not_a_broken_page() -> None:
    """The engine's panel is still on screen; this only says the words failed."""
    with talking(server()) as client:
        session_id = _game(client)
        response = client.post(f"/games/{session_id}/coach", json={"player": "you"})
        assert response.status_code == HTTP_UNAVAILABLE
        assert "no coach in this test" in response.json()["detail"]


def test_coaching_a_game_that_is_not_there() -> None:
    with talking(server(explainer=Canned(SENSIBLE))) as client:
        response = client.post("/games/nope/coach", json={"player": "you"})
        assert response.status_code == HTTP_NOT_FOUND


def test_coaching_a_player_who_is_not_in_the_game() -> None:
    with talking(server(explainer=Canned(SENSIBLE))) as client:
        session_id = _game(client)
        response = client.post(f"/games/{session_id}/coach", json={"player": "nobody"})
        assert response.status_code == HTTP_BAD_REQUEST


def test_the_player_defaults_to_you() -> None:
    """The app's own seat, which is what a phone with one player will send."""
    with talking(server(explainer=Canned(SENSIBLE))) as client:
        session_id = _game(client)
        response = client.post(f"/games/{session_id}/coach", json={})
        assert response.status_code == HTTP_OK


def test_coaching_does_not_change_the_game() -> None:
    """Asking for advice is not a move, so nothing may move."""
    with talking(server(explainer=Canned(SENSIBLE))) as client:
        session_id = _game(client)
        before = client.get(f"/games/{session_id}").json()
        client.post(f"/games/{session_id}/coach", json={"player": "you"})
        assert client.get(f"/games/{session_id}").json() == before


def test_saying_nothing_about_an_unmodelled_card_is_refused() -> None:
    """The honesty rule, through the route.

    A card the catalogue has facts for but no abilities for is one the engine
    can put on the table and cannot reason about. An explanation that does not
    mention it would let the player believe it had been counted, so the server
    replaces it -- the same machinery an invented card gets, for the opposite
    kind of mistake.
    """
    strange = facts("Strange Thing", "{2}", power=1, toughness=1, creature=True)
    catalogue = Catalogue(
        cards={"Forest": FOREST, "Bear": BEAR, "Strange": strange},
        # No entry for "Strange": known card, unknown behaviour.
        rules={"Forest": (taps_for("{G}"),), "Bear": ()},
    )
    deck = ("Forest",) * 6 + ("Strange",) * 4
    app = create_app(
        catalogue, {"green": deck, "other": deck}, TOKEN, Claude(Canned(SENSIBLE), NoAnswers())
    )
    with talking(app) as client:
        session_id = _game(client)
        card = named(
            rows(client.get(f"/games/{session_id}").json(), "state", "players", "you", "hand"),
            "Strange Thing",
        )
        client.post(
            f"/games/{session_id}/events",
            json={
                "type": "move_card",
                "player": "you",
                "instance_id": card["instance_id"],
                "to": "battlefield",
            },
        )
        body = client.post(f"/games/{session_id}/coach", json={"player": "you"}).json()
        assert not flag(body, "trusted")
        assert any(
            "Strange Thing" in problem for problem in words(obj(body, "explanation"), "watch_out")
        )
