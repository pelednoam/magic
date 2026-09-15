"""Every decision a coached game made, written down so it can be run again.

A seed reproduces a deal exactly -- the engine generates no randomness, so a
game is a pure function of its libraries and its events. It does not reproduce
the *coach*, which is a language model and will answer differently tomorrow.
So a coached game is only repeatable if what the coach said is kept.

That is what this is. One line of JSON per decision, appended as it happens, so
a run interrupted at three in the morning keeps everything up to that point.
The line holds the exact briefing the model was given as well as the answer,
which makes the journal useful for two quite different things: replaying the
game exactly, and reading what a bad piece of advice was actually asked.

Keyed by turn, step and player rather than by order. Replaying in order would
silently misalign the moment a game diverged; a key that is missing is a
finding, and a loud one.

This is the writing half. ``answers`` reads a journal back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.api.recording import Recording
    from mtgcoach.coach.advice import Explanation

#: One decision's identity: which game, when in it, and whose.
type Moment = tuple[int, int, str, str]


@dataclass(frozen=True, slots=True)
class Decision:
    """What the coach was asked, what it said, and what became of it."""

    seed: int
    turn: int
    step: str
    player: str
    #: The exact prompt. Large, and worth every byte: a disagreement is only
    #: diagnosable next to the board the model was actually shown.
    briefing: str
    #: The answer's fields, or None when there was no answer at all.
    answer: dict[str, object] | None = None
    #: Why there was none, when there was none.
    error: str = ""
    trusted: bool = False
    #: Every way the answer disagreed with the engine, in the engine's words.
    problems: tuple[str, ...] = ()

    @property
    def moment(self) -> Moment:
        """What this decision is, for looking it up again."""
        return (self.seed, self.turn, self.step, self.player)

    def as_json(self) -> str:
        """One line, for appending."""
        return json.dumps(
            {
                "seed": self.seed,
                "turn": self.turn,
                "step": self.step,
                "player": self.player,
                "briefing": self.briefing,
                "answer": self.answer,
                "error": self.error,
                "trusted": self.trusted,
                "problems": list(self.problems),
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True, slots=True)
class Journal:
    """A file that decisions are appended to.

    Opened and closed per line rather than held open: a season runs for hours,
    and a file handle kept across all of it is a file handle that loses the
    last few decisions when something goes wrong.
    """

    path: Path

    def write(self, decision: Decision) -> None:
        """Append one decision."""
        self._append(decision.as_json())

    def write_game(self, recording: Recording) -> None:
        """Append the game itself: how it was dealt and what happened.

        Written at the end rather than the start, because the event log is not
        known until then. A run killed mid-game therefore keeps its decisions
        and loses its recording, which is the right way round -- the decisions
        are what the coach said, and the recording can be produced again by
        replaying them.
        """
        self._append(recording.as_json())

    def _append(self, line: str) -> None:
        """One line, opened and closed around it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")


def fields(said: Explanation) -> dict[str, object]:
    """An explanation as the plain object a journal line holds."""
    return {
        "play": said.play,
        "attack": list(said.attack),
        "because": said.because,
        "in_short": said.in_short,
        "watch_out": list(said.watch_out),
        "check_yourself": list(said.check_yourself),
    }
