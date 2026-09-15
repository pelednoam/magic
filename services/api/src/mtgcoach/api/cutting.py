"""Cutting a journal into the games that were played in it.

A journal is appended to as a season runs: each decision as it happens, then
the recording when a game ends. So the games are stretches of the file, and
finding them is a matter of position -- not of the seed, which two runs into
the same journal repeat.

Split from ``replays`` at the line limit; the seam is between finding the games
and rebuilding their boards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from mtgcoach.api.recording import KIND, Recording, recorded


@dataclass(frozen=True, slots=True)
class Written:
    """One game's lines: the recording, and the decisions made during it."""

    recording: Recording
    decisions: tuple[dict[str, object], ...] = ()


def games(lines: list[object]) -> list[Written]:
    """The journal, cut into games at each recording line.

    Decisions that come after the last recording belong to a game that never
    finished, and are dropped. That is the right way round: a recording is
    written when a game ends, so decisions with none after them are a run that
    was killed mid-game, and there is no board to show them against.

    A killed run leaves those decisions in the *middle* of the file, though,
    not at the end: append another run to the same journal and they sit just
    before somebody else's recording, and position alone would hand them to
    that game. So the seed has to agree as well, which ``decisions`` checks.
    The two together are what nothing slips past -- position separates two
    games that share a seed, the seed separates two games that share a stretch.
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
        found = one_recording(entry)
        if found is not None:
            made.append(Written(recording=found, decisions=tuple(pending)))
        pending = []
    return made


def one_recording(entry: dict[str, object]) -> Recording | None:
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
