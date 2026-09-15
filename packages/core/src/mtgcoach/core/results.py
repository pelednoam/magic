"""How a game ends, recorded in the state rather than worked out afterwards.

A game that is over is a fact about the game, not an observation somebody
makes about it. It used to be the second thing: the state had no result field,
so a player could reach 0 life and the tracker would carry on advancing steps,
drawing cards and taking advice -- while the self-play harness, which had its
own life check outside the engine, knew perfectly well that the game had ended.
Two answers to one question, and the live path had the wrong one.

**When this is checked matters as much as what it checks.** CR 704.3: the game
checks for these conditions whenever a player would receive priority. Not after
every change -- a combat damage step kills creatures and changes life totals in
one go (CR 510.2), and a check wedged between those would end the game before
the deaths it caused had been applied. So ``turn.advance`` runs it, and a
single event is never interrupted part-way through.

That used to read "which is this engine's priority boundary", and it is worth
correcting rather than leaving: the engine now has three. A player receives
priority at the start of a step (CR 117.3a), after a spell resolves (CR 117.3b)
and after casting one (CR 117.3c), and only the first of those runs this check.
The gap is the same one it always was -- resolution has always handed priority
over in the rules, and this has always been checked a step late -- but
``priority`` makes the boundaries explicit, so a docstring that named one of
them as the boundary is now visibly wrong. Closing it is the state-based-action
work, not the priority work: the review's R05 is where it belongs, and running
this at three sites without the rest of CR 704.3 would be a second partial
answer to a question that already has one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.player import PlayerState


class Loss(StrEnum):
    """Why a player lost. One member per state-based action this can check."""

    #: CR 704.5a. Zero or less, checked rather than guarded against: life is
    #: allowed to pass through 0 during a larger operation.
    LIFE = "life"
    #: CR 704.5b, with CR 121.3. Attempting to draw from an empty library does
    #: not fail -- the attempt is remembered and loses the game at the next
    #: priority. Refusing the draw, which this engine used to do, makes the
    #: game unwinnable-by-decking impossible to reach instead of lost.
    EMPTY_LIBRARY = "empty_library"


@dataclass(frozen=True, slots=True)
class Lost:
    """One player, and the reason they are out."""

    player: PlayerId
    why: Loss


@dataclass(frozen=True, slots=True)
class Over:
    """The game is over. Who lost, and why.

    A tuple because both players can lose at once -- simultaneous lethal
    damage, or two empty libraries on the same draw -- and CR 104.4b makes that
    a draw rather than a win for whoever is listed first.
    """

    lost: tuple[Lost, ...]

    @property
    def drawn(self) -> bool:
        """Whether nobody won (CR 104.4b)."""
        return len(self.lost) > 1

    def winner(self, players: Iterable[PlayerId]) -> PlayerId | None:
        """The player still standing, or None if the game was a draw."""
        if self.drawn:
            return None
        out = {one.player for one in self.lost}
        return next((player for player in players if player not in out), None)


def losses(players: Mapping[PlayerId, PlayerState]) -> Over | None:
    """Every state-based loss that applies right now, or None if the game goes on.

    Life first, then the library, because that is the order a player checks:
    somebody at 0 has lost whatever their library says.

    Ordered by the mapping rather than by reason, so a draw lists the seats the
    way the game does and two runs of the same game read the same.
    """
    found = tuple(
        Lost(player, why) for player, state in players.items() if (why := _lost(state)) is not None
    )
    return Over(found) if found else None


def _lost(player: PlayerState) -> Loss | None:
    """Why this player is out, if they are."""
    if player.life <= 0:
        return Loss.LIFE
    if player.drew_from_empty:
        return Loss.EMPTY_LIBRARY
    return None
