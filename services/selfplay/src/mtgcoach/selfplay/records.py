"""What a game and a season of games leave behind.

The report is the product here, so it is a value rather than printed output: a
season can be summarised, compared between runs, or written to a file, and the
printing lives in one place at the edge.

``Trouble`` carries the turn and step because "card conservation broke" is not
a bug report and "card conservation broke on turn 7's declare-attackers step,
playing Elves into Goblins, seed 3" is one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.steps import Step
    from mtgcoach.selfplay.coached import Tally


class Kind(StrEnum):
    """What sort of thing went wrong.

    Separated because they mean different things about the code. A BROKEN
    invariant is a defect in the engine. A REFUSED event is the engine
    contradicting its own offer. A CRASH is anything nobody predicted. STUCK is
    a game that would not end, which is usually the harness and occasionally
    the step walker.
    """

    BROKEN = "invariant"
    REFUSED = "refused"
    CRASH = "crash"
    STUCK = "stuck"


@dataclass(frozen=True, slots=True)
class Trouble:
    """One thing that went wrong, and enough to find it again."""

    kind: Kind
    detail: str
    turn: int
    step: Step
    actor: PlayerId | None = None

    def __str__(self) -> str:
        """One line, for a person reading a run."""
        who = f" [{self.actor}]" if self.actor else ""
        return f"turn {self.turn} {self.step}{who}: {self.kind} -- {self.detail}"


@dataclass(frozen=True, slots=True)
class Game:
    """One finished game."""

    seed: int
    decks: tuple[str, str]
    turns: int
    winner: PlayerId | None
    ending: str
    trouble: tuple[Trouble, ...] = ()
    #: Cards either player held or played that the catalogue has no model for.
    #: Not trouble -- it is the honest state of the effect database -- but it
    #: is the single most useful number for deciding what to work on next.
    unknown: tuple[str, ...] = ()
    events: int = 0

    @property
    def clean(self) -> bool:
        """Whether the game finished with nothing wrong."""
        return not self.trouble


@dataclass(frozen=True, slots=True)
class Season:
    """Every game of a run."""

    games: tuple[Game, ...] = field(default_factory=tuple)
    #: One per coached seat, when the coach played. Empty for a policy run.
    coaching: tuple[Tally, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> int:
        """How many finished with nothing wrong."""
        return sum(1 for game in self.games if game.clean)

    @property
    def trouble(self) -> tuple[Trouble, ...]:
        """Everything that went wrong, across the whole run."""
        return tuple(problem for game in self.games for problem in game.trouble)

    @property
    def unknown(self) -> tuple[str, ...]:
        """Every card nothing could speak for, most often first."""
        seen: dict[str, int] = {}
        for game in self.games:
            for name in game.unknown:
                seen[name] = seen.get(name, 0) + 1
        return tuple(sorted(seen, key=lambda name: (-seen[name], name)))
