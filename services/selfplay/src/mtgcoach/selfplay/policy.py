"""An agent that costs nothing, so a thousand games can be played.

It does not understand Magic. It plays a land if it has one, casts the most
expensive thing it can afford, and attacks with whatever the engine ranked
first. That is enough, because the harness is not grading the play -- it is
watching the invariants, and a policy that develops a board and swings into
blockers puts the engine through far more of itself than a careful one would.

The seeded coin is there so a season varies. Always taking the best attack
would mean every game of two of these is the same shape, and the states that
break things are the odd ones.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.selfplay.moves import Move

if TYPE_CHECKING:
    from mtgcoach.coach.report import Playable, TurnReport
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState

#: How often the policy declines an attack it could make. Not zero, because an
#: attack that never happens is a board that never empties, and not high,
#: because combat is the half of the engine most worth exercising.
HOLD_BACK = 0.15

#: How often it plays nothing in a main phase it could act in. Keeps hands
#: from emptying at the same rate every game.
DAWDLE = 0.1


@dataclass(slots=True)
class Greedy:
    """Plays out, attacks often, thinks about nothing."""

    seed: int = 0
    name: str = "greedy"
    _coin: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """One generator per agent, so two seats do not share a sequence."""
        self._coin = random.Random(self.seed)  # noqa: S311 - a game, not a secret

    def act(self, state: GameState, report: TurnReport, player: PlayerId) -> Move:
        """A card to play, or an attack, depending on what the step allows."""
        del state, player
        if report.attacks.plans and self._coin.random() > HOLD_BACK:
            best = report.attacks.plans[0]
            return Move(
                attack=tuple(creature.instance_id for creature in best.attackers),
                because=f"the engine ranked it first: {', '.join(best.names)}",
            )
        return self._develop(report)

    def _develop(self, report: TurnReport) -> Move:
        """Play a land if there is one, otherwise the biggest affordable thing."""
        playable = report.playable
        if not playable or self._coin.random() < DAWDLE:
            return Move()
        chosen = _land(playable) or max(playable, key=_cost)
        return Move(play=chosen.instance_id, because=f"played {chosen.name}")


def _land(playable: tuple[Playable, ...]) -> Playable | None:
    """The first land, if one can be played.

    Lands first, always. A policy that spends its main phase casting a
    one-drop and never makes its land drop stalls on two mana forever, and a
    board that never grows is a board that never reaches the interesting
    states.
    """
    return next((card for card in playable if card.is_land), None)


def _cost(card: Playable) -> int:
    """How many sources paying for it would use.

    The biggest affordable spell, as a stand-in for the best one. It is wrong
    often and does not matter: it reliably puts something on the table, which
    is the only property the harness needs from it.
    """
    return card.payment.count if card.payment else 0
