"""A played game, as a sequence of moments somebody can step through.

The point of this is a child at a table with the game already over, walking it
one decision at a time and asking about it. So a moment carries the board *as
it was*, the advice the coach gave there, and whether that advice survived the
engine's checks.

**The board is rebuilt from the events, not re-derived.** A self-play journal
records the libraries a game was dealt and every event it applied, so a moment
is ``start_game`` then ``reduce.replay`` up to that point -- which is the same
machinery ``Session.consistent`` uses to prove a live game's cached state
matches its log. Asking the model again would produce a *different* game and
show a board that never existed; replaying the events cannot.

Moments are joined to decisions by turn and step, which is unique within a
game: a self-play game asks at most once per step, and the state a decision
was made from is the state on entering that step -- which is exactly what the
coach was shown.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtgcoach.api.recording import KIND, Recording, recorded
from mtgcoach.coach.advice import Explanation
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from mtgcoach.core.state import GameState

#: Where a journal lives, under the server's data root.
FOLDER = "selfplay"

#: What a journal file is called.
SUFFIX = ".jsonl"


class UnknownReplayError(KeyError):
    """No journal by that name, or nothing playable in it."""


@dataclass(frozen=True, slots=True)
class Moment:
    """One decision in a played game, and the board it was made from."""

    turn: int
    step: Step
    player: str
    state: GameState
    #: What the coach said, as the thing the coach returns. None when the model
    #: had no answer -- which is a real moment and worth showing, because the
    #: game carried on without advice and a child can see that it did.
    said: Explanation | None = None
    trusted: bool = False
    problems: tuple[str, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class Replay:
    """One game from a journal, ready to walk."""

    seed: int
    decks: tuple[str, str]
    moments: tuple[Moment, ...] = ()


def journals(data_root: Path) -> tuple[str, ...]:
    """Every journal on disk, newest first.

    Newest first because the interesting one is almost always the last run.
    """
    folder = data_root / FOLDER
    if not folder.is_dir():
        return ()
    found = sorted(folder.glob(f"*{SUFFIX}"), key=lambda one: one.stat().st_mtime, reverse=True)
    return tuple(one.stem for one in found)


def games_in(data_root: Path, name: str) -> tuple[Replay, ...]:
    """Every game a journal holds, in the order it played them.

    Raises:
        UnknownReplayError: If there is no such journal, or it holds no game
            that can be rebuilt. A journal of decisions with no recording is
            the shape a killed run leaves; it can still be replayed *inside*
            the harness, and cannot be shown, and saying which is better than
            an empty screen.
    """
    path = data_root / FOLDER / f"{name}{SUFFIX}"
    try:
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as unreadable:
        msg = f"{name}: {type(unreadable).__name__}"
        raise UnknownReplayError(msg) from unreadable
    played = tuple(_replay(recording, lines) for recording in _recordings(lines))
    if not played:
        msg = f"{name} has no game recording in it; it may be from an interrupted run"
        raise UnknownReplayError(msg)
    return played


def _recordings(lines: list[object]) -> Iterator[Recording]:
    """The game lines, in order."""
    for line in lines:
        found = recorded(line)
        if found is not None:
            yield found


def _replay(recording: Recording, lines: list[object]) -> Replay:
    """One game, rebuilt, with its decisions attached."""
    boards = _boards(recording)
    said = _decisions(lines, recording.seed)
    moments = tuple(
        _moment(turn, step, boards[turn, step], said.get((turn, step)))
        for (turn, step) in sorted(boards, key=lambda at: (at[0], _order(at[1])))
        if (turn, step) in said
    )
    return Replay(seed=recording.seed, decks=recording.decks, moments=moments)


def _boards(recording: Recording) -> dict[tuple[int, Step], GameState]:
    """The state on entering each step of the game.

    The *first* state seen at each turn and step, which is the board before
    anything was done there -- and so the board the coach was shown.
    """
    state = recording.opening()
    seen: dict[tuple[int, Step], GameState] = {(state.turn, state.step): state}
    for event in recording.events:
        state = apply(state, event)
        seen.setdefault((state.turn, state.step), state)
    return seen


def _decisions(lines: list[object], seed: int) -> dict[tuple[int, Step], dict[str, object]]:
    """Every decision of one game, by the moment it was made."""
    found: dict[tuple[int, Step], dict[str, object]] = {}
    for line in lines:
        if not isinstance(line, dict):
            continue
        entry = cast("dict[str, object]", line)
        if entry.get("kind") == KIND or entry.get("seed") != seed:
            continue
        turn, step = entry.get("turn"), entry.get("step")
        if isinstance(turn, int) and isinstance(step, str) and step in set(Step):
            found[turn, Step(step)] = entry
    return found


def _moment(turn: int, step: Step, state: GameState, entry: dict[str, object] | None) -> Moment:
    """One decision, as something a screen can show."""
    said = (entry or {}).get("answer")
    problems = (entry or {}).get("problems")
    return Moment(
        turn=turn,
        step=step,
        player=str((entry or {}).get("player", "")),
        state=state,
        said=_explanation(cast("dict[str, object]", said)) if isinstance(said, dict) else None,
        trusted=bool((entry or {}).get("trusted", False)),
        problems=tuple(str(one) for one in _listed(problems)),
        error=str((entry or {}).get("error", "")),
    )


def _explanation(answer: dict[str, object]) -> Explanation:
    """A recorded answer, back as the thing the coach returns.

    So a replayed moment goes out through ``views.explanation``, exactly like a
    live one -- and the app renders last night's advice with the component it
    already uses for this afternoon's.
    """
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


def _order(step: Step) -> int:
    """Where a step comes in a turn, so moments walk forwards."""
    return list(Step).index(step)
