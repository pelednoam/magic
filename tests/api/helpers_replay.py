"""A journal on disk, of the shape a coached season leaves behind.

Written here rather than by importing the harness on purpose: the API has to
read a journal, and ``tests/selfplay/test_journal_is_readable.py`` is what
pins the two halves of that format together. This one is free to write a
*small* journal -- three decisions and one short game -- so a test that walks
it can be read in one screen.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import AdvanceStep, PlayLand
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import TURN_ORDER, Step

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState

#: The game every replay test walks.
SEED = 7

#: And what it was called, so a route can ask for it by name.
NAME = "demo"

#: Ten cards each: seven for an opening hand and three to draw. Named rather
#: than dealt from a catalogue, because a replay carries no card data -- the
#: oracle id *is* the name on this wire, and a test that used real cards would
#: be testing the catalogue instead of the replay.
DECK = ("Forest", "Forest", "Forest", "Bear", "Bell", "Growth", "Forest", "Forest", "Bear", "Bell")

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
        CardInstance(InstanceId(f"{seat}-{n}"), OracleId(name)) for n, name in enumerate(DECK)
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


def journalled(data_root: Path, name: str = NAME) -> Path:
    """Write the journal under a data root, and say where it went."""
    path = data_root / "selfplay" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(one, ensure_ascii=False) for one in decisions()]
    lines.append(recording().as_json())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def board_at(step: Step) -> GameState:
    """The state on entering one step of the recorded game."""
    state = opening()
    seen = {state.step: state}
    for event in played():
        state = apply(state, event)
        seen.setdefault(state.step, state)
    return seen[step]
