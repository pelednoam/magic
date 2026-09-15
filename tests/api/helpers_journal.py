"""A journal on disk, of the shape a coached season leaves behind.

The file, where ``helpers_replay`` is the game: three decision lines and one
recording, written small enough that a test walking it can be read in one
screen. Split from that module at the line limit, and the seam is where the
test itself divides -- one half is what was played, the other is how it was
written down and served.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from helpers_api import SEATING
from helpers_replay import CATALOGUE, NAME, SEED, SOURCES, recording
from mtgcoach.api.app import create_app
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from fastapi import FastAPI

    from mtgcoach.api.sources import Sources


#: A full answer, so every field of the explanation view is exercised.
ANSWER: dict[str, object] = {
    "play": "you-1",
    "attack": ["you-4"],
    "because": "A land now is a spell next turn.",
    "in_short": "Play the Forest.",
    "watch_out": ["They have two untapped lands."],
    "check_yourself": ["Count their blockers first."],
}


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


def journalled(
    data_root: Path,
    name: str = NAME,
    extra: Sequence[str] = (),
    sources: Sources = SOURCES,
) -> Path:
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
    lines.append(recording(sources).as_json())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def serving(data_root: Path) -> FastAPI:
    """A server that can show the fixture journal, and name the cards in it.

    Its own rather than ``helpers_api.server``'s, because a replay needs a
    catalogue keyed by the oracle ids the journal holds -- which is the whole
    point of the UUID-shaped ids above.
    """
    return create_app(CATALOGUE, {}, SEATING, data_root=data_root)
