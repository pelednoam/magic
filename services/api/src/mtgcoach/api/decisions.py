"""One game's decision lines, as moments a screen can show.

Split from ``replays`` at the line limit, and the seam is a real one: that
module is about finding the games in a journal and rebuilding their boards,
this one is about the advice that was given on them. Every field here is read
defensively, because a journal is a file on a disk that a killed process may
have half-written -- and a wrong field read confidently is worse on this screen
than anywhere else in the project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import Explanation
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState


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


def decisions(
    lines: tuple[dict[str, object], ...], game: str, seed: int
) -> dict[tuple[int, Step, str], dict[str, object]]:
    """One game's decisions, by the moment each was made.

    Joined by ``game``, an id the harness makes once per game and writes on
    every line of it. That is exact: it survives two runs of a season repeating
    a seed, and it survives a run killed mid-game with another appended after
    it -- neither of which position or seed survives on its own.

    A journal written before that id existed has none, and falls back to what
    was there before: ``lines`` is already the stretch of file this game was
    written during, and the seed is checked on top of it. Good enough for the
    journals that exist, and not good enough to keep as the only answer.

    Keyed by the player as well as the step. Today the harness asks only the
    active player and one step has one decision -- but the line carries a
    player, and a key that throws it away is a key that silently keeps the last
    of two the day the defender is asked at declare-blockers, which the rules
    require and this project will need.
    """
    found: dict[tuple[int, Step, str], dict[str, object]] = {}
    for entry in lines:
        if not _belongs(entry, game, seed):
            continue
        turn, step, player = entry.get("turn"), entry.get("step"), entry.get("player")
        if isinstance(turn, int) and isinstance(step, str) and step in set(Step):
            found[turn, Step(step), str(player)] = entry
    return found


def _belongs(entry: dict[str, object], game: str, seed: int) -> bool:
    """Whether this decision was made during this game."""
    if game:
        return entry.get("game") == game
    return not entry.get("game") and entry.get("seed") == seed


def moment(turn: int, step: Step, state: GameState, entry: dict[str, object]) -> Moment:
    """One decision, as something a screen can show."""
    said = entry.get("answer")
    return Moment(
        turn=turn,
        step=step,
        player=str(entry.get("player", "")),
        state=state,
        said=explanation(cast("dict[str, object]", said)) if isinstance(said, dict) else None,
        # `is True` rather than `bool(...)`: this is a file on a disk, and the
        # string "false" is truthy. Nothing the harness writes is a string
        # here, and "the coach was checked and passed" is not a claim to make
        # on the strength of that.
        trusted=entry.get("trusted") is True,
        problems=tuple(str(one) for one in _listed(entry.get("problems"))),
        error=str(entry.get("error", "")),
    )


def explanation(answer: dict[str, object]) -> Explanation:
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


def order(at: tuple[int, Step, str]) -> tuple[int, int, str]:
    """Where a decision comes in the game, so moments walk forwards."""
    turn, step, player = at
    return (turn, list(Step).index(step), player)
