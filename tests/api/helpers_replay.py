"""A journal on disk, of the shape a coached season leaves behind.

Written here rather than by importing the harness on purpose: the API has to
read a journal, and ``tests/selfplay/test_journal_is_readable.py`` is what
pins the two halves of that format together. This one is free to write a
*small* journal -- three decisions and one short game -- so a test that walks
it can be read in one screen.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING

from helpers import facts
from helpers_api import TOKEN
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue
from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import AdvanceStep, PlayLand
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import TURN_ORDER, Step

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from fastapi import FastAPI

    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState

#: The game every replay test walks.
SEED = 7

#: And what it was called, so a route can ask for it by name.
NAME = "demo"

#: The oracle ids a journal's libraries are dealt from. UUID-shaped on purpose:
#: a real oracle id is Scryfall's UUID (``carddata.scryfall`` reads it straight
#: off the card), *not* the printed name. A fixture that used names here let a
#: board render every card as a raw id and still pass -- which is exactly what
#: happened, and what ``CATALOGUE`` below now makes impossible.
FOREST = "11111111-1111-1111-1111-111111111111"
BEAR = "22222222-2222-2222-2222-222222222222"

#: What those ids are called. A replay's board must print these words.
NAMED = {FOREST: "Forest", BEAR: "Grizzly Bears"}

#: A catalogue that knows them, for a server serving replays.
CATALOGUE = Catalogue(
    cards={
        oracle: replace(
            facts(name, land=name == "Forest", creature=name != "Forest"),
            oracle_id=OracleId(oracle),
        )
        for oracle, name in NAMED.items()
    },
    rules=dict.fromkeys(NAMED, ()),
)

#: Ten cards each: seven for an opening hand and three to draw.
DECK = (FOREST, FOREST, FOREST, BEAR, FOREST, BEAR, FOREST, FOREST, BEAR, BEAR)

#: A full answer, so every field of the explanation view is exercised.
ANSWER: dict[str, object] = {
    "play": "you-1",
    "attack": ["you-4"],
    "because": "A land now is a spell next turn.",
    "in_short": "Play the Forest.",
    "watch_out": ["They have two untapped lands."],
    "check_yourself": ["Count their blockers first."],
}


def library(seat: str) -> tuple[CardInstance, ...]:
    """One seat's deck, with ids that say which seat they came from."""
    return tuple(
        CardInstance(InstanceId(f"{seat}-{n}"), OracleId(oracle)) for n, oracle in enumerate(DECK)
    )


def opening() -> GameState:
    """The game as it was dealt."""
    return start_game(
        {seat: library(str(seat)) for seat in (PlayerId("you"), PlayerId("them"))},
        first_player=PlayerId("you"),
    )


def played() -> tuple[Event, ...]:
    """A first turn: walk to the main phase, play a land, walk to the end.

    Far short of a game, and enough for what a replay test needs -- a board
    that changes, and a step to hang each kind of decision on.
    """
    events: list[Event] = list(_advances_to(Step.PRECOMBAT_MAIN))
    events.append(PlayLand(PlayerId("you"), InstanceId("you-0")))
    events.extend(_advances_to(Step.END_STEP, after=Step.PRECOMBAT_MAIN))
    return tuple(events)


def _advances_to(step: Step, after: Step = Step.UNTAP) -> tuple[Event, ...]:
    """Enough step advances to get from one step to another within a turn."""
    return tuple(AdvanceStep() for _ in range(TURN_ORDER.index(step) - TURN_ORDER.index(after)))


def recording() -> Recording:
    """The whole game, ready to be written down."""
    return Recording(
        seed=SEED,
        decks=("green", "other"),
        first="you",
        libraries=dealt_as(opening()),
        events=played(),
    )


def decisions() -> tuple[dict[str, object], ...]:
    """One of each kind of decision: agreed with, doubted, and never given."""
    return (
        _decision(Step.PRECOMBAT_MAIN, answer=ANSWER, trusted=True),
        _decision(
            Step.DECLARE_ATTACKERS,
            answer=ANSWER,
            problems=["Grizzly Bears cannot attack: it entered this turn."],
        ),
        _decision(Step.POSTCOMBAT_MAIN, error="no answer: the coach was not available"),
    )


def _decision(
    step: Step,
    answer: dict[str, object] | None = None,
    error: str = "",
    *,
    trusted: bool = False,
    problems: list[str] | None = None,
) -> dict[str, object]:
    """One journal line, as the harness writes it."""
    return {
        "seed": SEED,
        "turn": 1,
        "step": str(step),
        "player": "you",
        "briefing": "the board, as the model was shown it",
        "answer": answer,
        "error": error,
        "trusted": trusted,
        "problems": problems if problems is not None else [],
    }


def journalled(data_root: Path, name: str = NAME, extra: Sequence[str] = ()) -> Path:
    """Write the journal under a data root, and say where it went.

    ``extra`` goes in with the decisions, *before* the recording line, because
    that is where a line of this game belongs: a journal is cut into games at
    each recording, so a decision appended after one is a decision of the next
    game, not of this one.
    """
    path = data_root / "selfplay" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(one, ensure_ascii=False) for one in decisions()]
    lines.extend(extra)
    lines.append(recording().as_json())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def serving(data_root: Path) -> FastAPI:
    """A server that can show the fixture journal, and name the cards in it.

    Its own rather than ``helpers_api.server``'s, because a replay needs a
    catalogue keyed by the oracle ids the journal holds -- which is the whole
    point of the UUID-shaped ids above.
    """
    return create_app(CATALOGUE, {}, TOKEN, data_root=data_root)


def board_at(step: Step) -> GameState:
    """The state on entering one step of the recorded game."""
    state = opening()
    seen = {state.step: state}
    for event in played():
        state = apply(state, event)
        seen.setdefault(state.step, state)
    return seen[step]
