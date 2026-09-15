"""An agent that is the coach, so the coach gets played rather than sampled.

The whole point of this one. A smoke test asks the coach about one position and
reads the answer; this asks it about every decision of a whole game and then
*applies* what it said, so the next position is a consequence of the last piece
of advice. Bad advice compounds, and compounding is the only way to see it.

It records more than it decides. Every turn it notes whether the answer passed
``advice.verify`` -- the same check the server puts in front of a player -- and
whether the card it named was one the engine offered. Those two numbers over
fifty decisions say more about whether the coach is usable than any single
answer does.

Slow and not free: one subprocess per decision, a second or two each, so a game
is minutes rather than milliseconds. Use it for one game at a time and use
``policy.Greedy`` for volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.coach.advice import ExplainerError, verify
from mtgcoach.coach.briefing import brief
from mtgcoach.core.ids import InstanceId
from mtgcoach.selfplay import journal
from mtgcoach.selfplay.moves import Move

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explainer, Explanation
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState
    from mtgcoach.selfplay.journal import Journal


@dataclass(slots=True)
class Tally:
    """How the coach did over a game.

    Kept on the agent rather than in the game record because it is about the
    *agent*, and a game played by two of these has two of them to compare.
    """

    asked: int = 0
    refused: int = 0
    untrusted: int = 0
    #: Every distinct reason a check failed, most recent last. The text is the
    #: engine's own, so this is a list of the ways the coach and the engine
    #: disagreed -- which is the most useful thing a season produces.
    disagreements: list[str] = field(default_factory=list[str])

    @property
    def trusted(self) -> int:
        """Answers that survived every check."""
        return self.asked - self.refused - self.untrusted


@dataclass(frozen=True, slots=True)
class Asked:
    """Where a decision was made, for the journal line."""

    state: GameState
    player: PlayerId
    briefing: str


@dataclass(frozen=True, slots=True)
class Answered:
    """And what came of it."""

    said: Explanation | None = None
    problems: tuple[str, ...] = ()
    error: str = ""


@dataclass(slots=True)
class Coached:
    """Asks the coach, applies what it says, keeps score, and writes it down."""

    explainer: Explainer
    name: str = "coach"
    tally: Tally = field(default_factory=Tally)
    #: Which game this is, so a journal line can be looked up again.
    seed: int = 0
    #: Which game this is, exactly. A seed says which *deal*; two runs of one
    #: season repeat it, and a reader joining decisions to games by seed alone
    #: would put the second run's advice beside the first run's board.
    game: str = ""
    #: Where to write what happened. None keeps nothing, which is what a test
    #: wants and what a run nobody intends to repeat can have.
    journal: Journal | None = None

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """Whatever the coach recommends, if it survived being checked.

        An answer that fails its checks is not played. That is the same rule
        the server applies on a player's behalf -- the refusal text goes on
        screen and the engine's own panel stays -- and a harness that played
        unchecked advice anyway would be measuring something nobody is ever
        shown.
        """
        self.tally.asked += 1
        briefing = brief(report)
        try:
            said = self.explainer.explain(report, briefing)
        except ExplainerError as unavailable:
            self.tally.refused += 1
            self.tally.disagreements.append(f"no answer: {unavailable}")
            self._wrote(Asked(state, player, briefing), Answered(error=str(unavailable)))
            return Move()
        problems = verify(said, report)
        self._wrote(Asked(state, player, briefing), Answered(said=said, problems=problems))
        if problems:
            self.tally.untrusted += 1
            self.tally.disagreements.extend(problems)
            return Move()
        return Move(
            play=InstanceId(said.play) if said.play else None,
            attack=tuple(InstanceId(one) for one in said.attack),
            because=said.because,
        )

    def _wrote(self, at: Asked, outcome: Answered) -> None:
        """Put this decision in the journal, if there is one."""
        if self.journal is None:
            return
        self.journal.write(
            journal.Decision(
                seed=self.seed,
                game=self.game,
                turn=at.state.turn,
                step=str(at.state.step),
                player=str(at.player),
                briefing=at.briefing,
                answer=journal.fields(outcome.said) if outcome.said is not None else None,
                error=outcome.error,
                trusted=outcome.said is not None and not outcome.problems,
                problems=outcome.problems,
            )
        )
