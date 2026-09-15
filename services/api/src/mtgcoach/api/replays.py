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

**A game is a stretch of the file, not a seed.** The harness appends each
decision as it happens and the recording when the game ends, so the decisions
belonging to a game are the ones between the previous recording and this one.
That is what joins them -- not the seed, which two runs into the same journal
will repeat, and which would then put one game's advice beside another game's
board. Position cannot collide; a seed can, and did in the obvious way the
moment anybody re-ran a season without deleting the journal first.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtgcoach.api.decisions import Moment, decisions, moment, order
from mtgcoach.api.recording import KIND, Recording, recorded
from mtgcoach.core.reduce import apply

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.state import GameState
    from mtgcoach.core.steps import Step

#: Where a journal lives, under the server's data root.
FOLDER = "selfplay"

#: What a journal file is called.
SUFFIX = ".jsonl"


class UnknownReplayError(KeyError):
    """No journal by that name, or nothing playable in it."""


@dataclass(frozen=True, slots=True)
class Replay:
    """One game from a journal, ready to walk."""

    #: Where it is in the journal. Its address, because it is the only thing
    #: about a game that is certainly unique.
    index: int
    seed: int
    decks: tuple[str, str]
    moments: tuple[Moment, ...] = ()


@dataclass(frozen=True, slots=True)
class Written:
    """One game's lines: the recording, and the decisions made during it."""

    recording: Recording
    decisions: tuple[dict[str, object], ...] = ()


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
    played = tuple(
        game
        for at, written in enumerate(_games(cast("list[object]", lines)))
        if (game := _replay(at, written)) is not None
    )
    if not played:
        msg = f"{name} has no game in it that can be rebuilt; it may be from an interrupted run"
        raise UnknownReplayError(msg)
    return played


def _games(lines: list[object]) -> list[Written]:
    """The journal, cut into games at each recording line.

    Decisions that come after the last recording belong to a game that never
    finished, and are dropped. That is the right way round: a recording is
    written when a game ends, so decisions with none after them are a run that
    was killed mid-game, and there is no board to show them against.
    """
    made: list[Written] = []
    pending: list[dict[str, object]] = []
    for line in lines:
        if not isinstance(line, dict):
            continue
        entry = cast("dict[str, object]", line)
        if entry.get("kind") != KIND:
            pending.append(entry)
            continue
        found = _recording(entry)
        if found is not None:
            made.append(Written(recording=found, decisions=tuple(pending)))
        pending = []
    return made


def _recording(entry: dict[str, object]) -> Recording | None:
    """A game line, or None if it cannot be trusted to rebuild one.

    A damaged deal is refused rather than repaired. Dropping one card from a
    library shifts every card after it, and the boards that then rebuild are
    boards that never existed -- which is worse than a game the screen cannot
    show, and much worse on this screen than anywhere else.
    """
    try:
        return recorded(entry)
    except ValueError:
        return None


def _replay(index: int, written: Written) -> Replay | None:
    """One game, rebuilt, with its decisions attached.

    None when the recording will not rebuild -- a library too short for an
    opening hand, a seat missing. A journal is a file that a killed process may
    have half-written, so one damaged game is not a reason to refuse the rest
    of a season.
    """
    try:
        boards = _boards(written.recording)
    except ValueError:
        return None
    said = decisions(written.decisions)
    moments = tuple(
        moment(turn, step, boards[turn, step], entry)
        for (turn, step, _), entry in sorted(said.items(), key=lambda one: order(one[0]))
        if (turn, step) in boards
    )
    return Replay(
        index=index,
        seed=written.recording.seed,
        decks=written.recording.decks,
        moments=moments,
    )


def _boards(recording: Recording) -> dict[tuple[int, Step], GameState]:
    """The state on entering each step of the game.

    The *first* state seen at each turn and step, which is the board before
    anything was done there -- and so the board the coach was shown.

    Raises:
        ValueError: If the recording's libraries are not a game.
    """
    state = recording.opening()
    seen: dict[tuple[int, Step], GameState] = {(state.turn, state.step): state}
    for event in recording.events:
        state = apply(state, event)
        seen.setdefault((state.turn, state.step), state)
    return seen
