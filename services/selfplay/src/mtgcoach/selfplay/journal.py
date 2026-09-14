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
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import Explanation

if TYPE_CHECKING:
    from pathlib import Path

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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(decision.as_json() + "\n")


@dataclass(frozen=True, slots=True)
class Answers:
    """Decisions read back, ready to be replayed."""

    said: dict[Moment, Decision] = field(default_factory=dict[Moment, Decision])

    def at(self, moment: Moment) -> Decision | None:
        """What was decided then, or None if this journal does not say."""
        return self.said.get(moment)

    def __len__(self) -> int:
        """How many decisions are in it."""
        return len(self.said)


def read(path: Path) -> Answers:
    """Every decision in a journal.

    A line that is not readable is skipped rather than fatal. A journal is
    written by a process that may have been killed mid-write, and losing the
    last line of a three-hour run is not a reason to refuse the other four
    hundred.

    Raises:
        OSError: If the file cannot be read at all.
    """
    said: dict[Moment, Decision] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        made = _decision(line)
        if made is not None:
            said[made.moment] = made
    return Answers(said=said)


def _decision(line: str) -> Decision | None:
    """One line, or None if it is not one."""
    if not line.strip():
        return None
    try:
        loaded = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return _from(cast("dict[str, object]", loaded))


def _from(loaded: dict[str, object]) -> Decision | None:
    """A decision from a decoded line, or None if it is missing what it needs."""
    seed, turn = loaded.get("seed"), loaded.get("turn")
    step, player = loaded.get("step"), loaded.get("player")
    if not (isinstance(seed, int) and isinstance(turn, int)):
        return None
    if not (isinstance(step, str) and isinstance(player, str)):
        return None
    answer = loaded.get("answer")
    problems = loaded.get("problems")
    return Decision(
        seed=seed,
        turn=turn,
        step=step,
        player=player,
        briefing=str(loaded.get("briefing", "")),
        answer=cast("dict[str, object]", answer) if isinstance(answer, dict) else None,
        error=str(loaded.get("error", "")),
        trusted=bool(loaded.get("trusted", False)),
        problems=tuple(str(one) for one in _listed(problems)),
    )


def explanation(answer: dict[str, object]) -> Explanation:
    """A journalled answer, back as the thing the coach returned."""
    return Explanation(
        play=str(answer.get("play", "")),
        attack=tuple(str(one) for one in _listed(answer.get("attack"))),
        because=str(answer.get("because", "")),
        in_short=str(answer.get("in_short", "")),
        watch_out=tuple(str(one) for one in _listed(answer.get("watch_out"))),
        check_yourself=tuple(str(one) for one in _listed(answer.get("check_yourself"))),
    )


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


def _listed(value: object) -> list[object]:
    """A JSON array, or nothing."""
    return cast("list[object]", value) if isinstance(value, list) else []
