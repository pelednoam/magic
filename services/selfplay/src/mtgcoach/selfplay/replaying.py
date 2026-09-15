"""Playing a coached game again, from what the coach said the first time.

The engine is deterministic, so a seed reproduces a deal and a policy exactly.
The coach is not: it is a language model, and asking it the same question
tomorrow is a different experiment rather than the same one. So a coached game
is repeatable only from a journal, and this is the agent that reads one.

Two things to do with that, and they answer different questions:

- **Replay.** The same journal, the same seed: the identical game, in a second
  rather than twenty minutes, as many times as you like. This is what makes a
  bad decision something to study rather than something that happened once.
  Change the engine, replay, and the journal tells you whether the change
  altered a game the coach had already played.
- **Re-ask.** The same seeds with the coach live again, and compare the tallies.
  That measures how *stable* the advice is, which no single run can.

A moment the journal does not have is refused rather than guessed. Replay whose
gaps are quietly filled with "do nothing" is not a replay, and the divergence
it hides is the most interesting thing that could have happened.

A replay writes a journal of its own when given one, and that journal is about
*this* run: the same answers, today's verdicts, and a recording of the game
they actually produced. Which is how a coached run from before the harness
recorded games becomes one that can be stepped through -- in seconds, without
asking the model anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.coach.advice import verify
from mtgcoach.core.ids import InstanceId
from mtgcoach.selfplay import answers
from mtgcoach.selfplay.coached import Tally
from mtgcoach.selfplay.journal import Decision
from mtgcoach.selfplay.moves import Move

if TYPE_CHECKING:
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState
    from mtgcoach.selfplay.answers import Answers
    from mtgcoach.selfplay.journal import Journal


class DivergedError(LookupError):
    """The replay asked for a moment the journal does not have.

    Which means the game went somewhere the recorded one did not -- so either
    the engine changed under it, or the journal is from a different seed. Both
    are worth stopping for.
    """


@dataclass(slots=True)
class Replayed:
    """Plays a game back out of a journal."""

    answers: Answers
    seed: int = 0
    #: Which game this is, exactly. A seed says which *deal*; two runs of one
    #: season repeat it, and a reader joining decisions to games by seed alone
    #: would put the second run's advice beside the first run's board.
    game: str = ""
    name: str = "replay"
    tally: Tally = field(default_factory=Tally)
    #: Where to write this run's decisions. None keeps nothing, which is what
    #: a test wants and what a run nobody intends to walk through can have.
    journal: Journal | None = None

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """Whatever the coach said at this exact moment, the first time.

        The answer is checked again rather than trusted because it was trusted
        before. That is the point of replaying against a changed engine: an
        answer that passed last week and fails today is exactly the regression
        worth knowing about, and the journal records what the verdict *was* so
        the two can be compared.

        Raises:
            DivergedError: If the journal has nothing for this moment.
        """
        moment = (self.seed, state.turn, str(state.step), str(player))
        found = self.answers.at(moment)
        if found is None:
            msg = f"the journal has no decision for {moment}"
            raise DivergedError(msg)
        self.tally.asked += 1
        if found.answer is None:
            self.tally.refused += 1
            self.tally.disagreements.append(f"no answer: {found.error}")
            self._wrote(state, player, found, ())
            return Move()
        said = answers.explanation(found.answer)
        problems = verify(said, report)
        self._wrote(state, player, found, problems)
        if problems:
            self.tally.untrusted += 1
            self.tally.disagreements.extend(
                f"{problem} (journal said trusted={found.trusted})" for problem in problems
            )
            return Move()
        return Move(
            play=InstanceId(said.play) if said.play else None,
            attack=tuple(InstanceId(one) for one in said.attack),
            because=said.because,
        )

    def _wrote(
        self,
        state: GameState,
        player: PlayerId,
        found: Decision,
        problems: tuple[str, ...],
    ) -> None:
        """Put this decision in the journal, if there is one.

        The answer is the one the coach gave; the *verdict* is today's. That is
        deliberate and is the whole point of replaying against a changed
        engine: the new journal describes the run that just happened, and the
        tally carries the comparison with what the old one said.
        """
        if self.journal is None:
            return
        self.journal.write(
            Decision(
                seed=self.seed,
                game=self.game,
                turn=state.turn,
                step=str(state.step),
                player=str(player),
                briefing=found.briefing,
                answer=found.answer,
                error=found.error,
                trusted=found.answer is not None and not problems,
                problems=problems,
            )
        )
