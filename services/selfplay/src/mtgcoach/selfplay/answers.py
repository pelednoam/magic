"""Reading a journal back: the decisions in it, keyed by the moment they were made.

Kept apart from writing because the two halves have different jobs and
different readers. ``Journal`` is used by the agent as a game happens, one
append at a time; this is used afterwards, by a replay or by a person asking
what the coach said on turn seven. Splitting them also keeps each under the
line limit, which is what forced the question.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import Explanation
from mtgcoach.selfplay.journal import Decision, Moment

if TYPE_CHECKING:
    from pathlib import Path


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
        game=str(loaded.get("game", "")),
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


def _listed(value: object) -> list[object]:
    """A JSON array, or nothing."""
    return cast("list[object]", value) if isinstance(value, list) else []
