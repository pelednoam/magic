"""What an agent decides, and what an agent is.

Deliberately the same two fields the coach answers with -- a card to play and
a set of attackers -- so that Claude *is* an agent rather than something a
shim has to translate. An agent that plays badly is not a bug; an agent that
plays something the engine did not offer is, and that is what the harness
watches for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.ids import InstanceId, PlayerId
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class Move:
    """One decision: a card to play, and who attacks.

    Both optional and both independent, because the two are asked at different
    steps -- a main phase wants ``play`` and a declare-attackers step wants
    ``attack``. An agent answering the wrong one is not an error; the harness
    simply has nothing to apply.
    """

    #: A card in hand to put onto the battlefield, or None to do nothing.
    play: InstanceId | None = None
    #: The creatures to attack with. Empty is a real decision, not an absence.
    attack: tuple[InstanceId, ...] = ()
    #: Why, in the agent's own words. Recorded, never checked -- it is what
    #: makes a losing game readable afterwards.
    because: str = ""


@dataclass(frozen=True, slots=True)
class Seat:
    """One side of the table."""

    player: PlayerId
    deck: str
    agent: Agent


class Agent(Protocol):
    """Something that decides what to do with a position.

    The protocol is the whole point of the harness: the same game loop drives
    a policy that costs nothing and a Claude that costs a subprocess, and the
    watching is identical either way.
    """

    @property
    def name(self) -> str:
        """What to call this agent in a report."""
        ...

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """Decide. May return an empty ``Move``, which means "nothing"."""
        ...


@dataclass(frozen=True, slots=True)
class Idle:
    """An agent that never does anything.

    Useful on its own: a game of two of these should still walk every step of
    every turn, draw every card, and end by decking rather than by anything
    going wrong. That is a real test of the step walker, and the cheapest one
    there is.
    """

    name: str = "idle"
    #: Present so the dataclass has the shape the others have.
    _unused: tuple[()] = field(default=(), repr=False)

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """Nothing, whatever the position."""
        del state, report, player
        return Move()
