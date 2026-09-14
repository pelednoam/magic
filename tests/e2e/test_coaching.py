"""The coach route over the real cards, with the model's answer written here.

Everything below the explainer is real: the Scryfall reader, the store, the
signed effect fixture, the engine, the briefing. What is stubbed is the one
thing that cannot be: whether the words are good is a judgement, and whether
the *choice* is allowed is not -- so the choice is what these check.

The reason this matters more than the unit tests do is identity. A briefing
names cards by instance id, the model answers with one, and the checker looks
it up. Every one of those is a real id here, produced by the real dealer from
the real deck, rather than the word "Bear".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from conftest import GREEN, WHITE
from helpers_api import Canned
from mtgcoach.api.app import create_app
from mtgcoach.coach.advice import Explanation
from snapshot import ask, look, no_coach, send, start, verdicts
from wire import flag, obj, rows, text, words

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.api.cards import Catalogue

#: Untap, upkeep, draw, then the first main phase.
STEPS_TO_MAIN = 3

SAID = Explanation(
    because="A land is the only move, and any Forest is the same card.",
    in_short="Play a Forest.",
)


@pytest.fixture
def coach() -> Canned:
    """The model's answer, which each test rewrites once it knows the board."""
    return Canned(SAID)


@pytest.fixture
def client(catalogue: Catalogue, coach: Canned) -> Iterator[TestClient]:
    """The real server, with that answer standing in for the model."""
    app = create_app(catalogue, {"green": GREEN, "white": WHITE}, coach)
    with TestClient(app) as connected:
        yield connected


def _main(client: TestClient) -> tuple[str, dict[str, object]]:
    """A game walked to its first main phase."""
    session_id = start(client)
    body = look(client, session_id)
    for _ in range(STEPS_TO_MAIN):
        body = send(client, session_id, type="advance_step")
    return session_id, body


def test_a_real_forest_recommended_by_its_real_id_is_trusted(
    client: TestClient, coach: Canned
) -> None:
    """The whole identity chain: dealer, engine, briefing, checker."""
    session_id, body = _main(client)
    forest = verdicts(body, "you")["Forest"]
    assert flag(forest, "playable")
    coach.said = Explanation(
        play=text(forest, "instance_id"),
        because=SAID.because,
        in_short=SAID.in_short,
    )
    answer = ask(client, session_id)
    assert answer["trusted"] is True
    assert text(obj(answer, "explanation"), "play") == text(forest, "instance_id")


def test_recommending_a_card_the_engine_cannot_afford_is_refused(
    client: TestClient, coach: Canned
) -> None:
    """Llanowar Elves on turn one: real card, real reason, really refused."""
    session_id, body = _main(client)
    elves = verdicts(body, "you")["Llanowar Elves"]
    assert not flag(elves, "playable")
    coach.said = Explanation(
        play=text(elves, "instance_id"),
        because="Elves first, always.",
        in_short="Play the Elves!",
    )
    answer = ask(client, session_id)
    assert answer["trusted"] is False
    explanation = obj(answer, "explanation")
    assert "Elves!" not in text(explanation, "in_short")
    assert any("Llanowar Elves" in problem for problem in words(explanation, "watch_out"))


def test_no_coach_at_all_is_a_503(catalogue: Catalogue) -> None:
    """The engine's own advice is still in every snapshot; only the words fail."""
    from helpers_api import NoCoach  # noqa: PLC0415 - the point is this one app

    app = create_app(catalogue, {"green": GREEN, "white": WHITE}, NoCoach())
    with TestClient(app) as client:
        session_id = start(client)
        no_coach(client, session_id)
        # And the engine's own advice is still there, which is the point.
        assert rows(look(client, session_id), "advice", "you", "hand")
