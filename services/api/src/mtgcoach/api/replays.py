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
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.api.cutting import games
from mtgcoach.api.decisions import Moment, decisions, moment, order
from mtgcoach.api.sources import Sources
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.reduce import apply

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.api.cutting import Written
    from mtgcoach.api.recording import Recording
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
    #: Which engine, card data and rules it was played under, as recorded.
    #: Empty for a journal written before that was recorded, which is most of
    #: the ones on disk -- and is exactly the case this exists to make legible.
    sources: Sources = field(default_factory=Sources)
    #: Why this game cannot be shown, when it cannot. Empty when it rebuilt.
    #: A game with a problem has no moments and is still listed, because the
    #: listing is where somebody finds out *why* -- and what it was played
    #: under is beside it.
    problem: str = ""


def _decoded(text: str) -> list[object]:
    """Every line of a journal, up to the first one that is not JSON.

    Stopping rather than refusing the file: a journal is appended to by a
    process that can be killed mid-write, so a half-written last line is the
    normal shape of an interrupted run -- and losing a whole season's games to
    it was the loudest possible response to the quietest possible problem.

    Stopping rather than skipping, for the same reason as a truncated event
    log: a *recording* that failed to decode would otherwise hand its game's
    decisions to the next recording along, which is one game's advice beside
    another game's board. Everything before the damage is good; nothing after
    it can be trusted to mean what it says.
    """
    found: list[object] = []
    for line in text.splitlines():
        if not line:
            continue
        try:
            found.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return found


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
        UnknownReplayError: If there is no such journal, or it holds no
            recording at all -- the shape a killed run leaves. Such a journal
            can still be replayed *inside* the harness and cannot be shown, and
            saying which is better than an empty screen. A game that is there
            and will not rebuild is a listed game with a reason, not an error.
    """
    path = data_root / FOLDER / f"{name}{SUFFIX}"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as unreadable:
        msg = f"{name}: {type(unreadable).__name__}"
        raise UnknownReplayError(msg) from unreadable
    lines = _decoded(text)
    played = tuple(_replay(at, written) for at, written in enumerate(games(lines)))
    if not played:
        # No *recording* at all, which is the shape a killed run leaves: a
        # journal of decisions can still be replayed inside the harness and
        # cannot be shown. A game that merely will not rebuild is listed with
        # its reason instead -- see ``_replay``.
        msg = f"{name} has no game recorded in it; it may be from an interrupted run"
        raise UnknownReplayError(msg)
    return played


def _replay(index: int, written: Written) -> Replay:
    """One game, rebuilt, with its decisions attached -- or the reason it is not.

    Two ways a recording will not rebuild and both are real: a deal that is not
    a game (``ValueError`` out of ``start_game`` -- a library too short for an
    opening hand, a seat missing), and an event the engine now refuses
    (``IllegalEventError`` out of ``apply``). The second is not hypothetical:
    ``docs/SELFPLAY.md`` says in as many words that a replay against a stricter
    engine diverges, and a game recorded before a rule was tightened is exactly
    that. Neither is a reason to refuse the rest of a season, and neither may
    be a 500.

    It used to drop such a game from the list, which threw away the one thing
    that explains it: the recording *says* which engine played it. It is listed
    with no moments, the reason, and the revisions -- so "this will not open"
    arrives with "played under a different engine" rather than a guess.
    """
    said = decisions(written.decisions, written.recording.game, written.recording.seed)
    try:
        boards = _boards(written.recording)
    except (ValueError, IllegalEventError) as unplayable:
        return Replay(
            index=index,
            seed=written.recording.seed,
            decks=written.recording.decks,
            sources=written.recording.sources,
            problem=f"{type(unplayable).__name__}: {unplayable}",
        )
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
        sources=written.recording.sources,
    )


def _boards(recording: Recording) -> dict[tuple[int, Step], GameState]:
    """The state on entering each step of the game.

    The *first* state seen at each turn and step, which is the board before
    anything was done there -- and so the board the coach was shown.

    Raises:
        ValueError: If the recording's libraries are not a game.
        IllegalEventError: If an event in it cannot be applied to the board it
            reached -- which a game recorded before the engine grew stricter
            really can contain.
    """
    state = recording.opening()
    seen: dict[tuple[int, Step], GameState] = {(state.turn, state.step): state}
    for event in recording.events:
        state = apply(state, event)
        seen.setdefault((state.turn, state.step), state)
    return seen
