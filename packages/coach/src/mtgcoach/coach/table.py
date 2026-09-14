"""What is actually on the table, for a question that is about it.

``TurnReport`` answers "what can I do", and for that it does not need to say
what is on the battlefield -- the attack plans already name the creatures that
matter. A rules question is different. "Can my creature block that one?" cannot
be answered from a turn, a step and a life total, and a prompt that offered only
those invited a general lecture in place of an answer about the board.

So this is the other half: both battlefields, named, with the three properties
that decide most beginner questions -- is it tapped, is it summoning sick, and
how big is it -- plus an explicit note on any card the engine cannot read, so a
question about *that* card is answered "look at the card" rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class Thing:
    """One permanent, as much of it as a rules question needs."""

    name: str
    tapped: bool = False
    summoning_sick: bool = False
    power: int | None = None
    toughness: int | None = None
    keywords: tuple[str, ...] = ()
    #: Set when the engine cannot read the card. Passed on rather than hidden.
    unreadable: bool = False

    def described(self) -> str:
        """One line, as a person would read it out."""
        parts = [self.name]
        if self.power is not None and self.toughness is not None:
            parts.append(f"{self.power}/{self.toughness}")
        parts.extend(self.keywords)
        if self.tapped:
            parts.append("tapped")
        if self.summoning_sick:
            parts.append("summoning sick")

        if self.unreadable:
            parts.append("THE ENGINE CANNOT READ THIS CARD -- say so rather than guessing")
        return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class Table:
    """Both battlefields, from one player's side of it."""

    yours: tuple[Thing, ...] = ()
    theirs: tuple[Thing, ...] = ()


def table(state: GameState, player_id: PlayerId, lookup: CardLookup) -> Table:
    """What both players have on the battlefield.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game.
    """
    mine = state.player(player_id).battlefield
    theirs = [s.battlefield for pid, s in state.players.items() if pid != player_id]
    return Table(
        yours=_things(mine, lookup),
        theirs=tuple(thing for field in theirs for thing in _things(field, lookup)),
    )


def _things(battlefield: Sequence[Permanent], lookup: CardLookup) -> tuple[Thing, ...]:
    """One battlefield, as lines."""
    return tuple(_thing(permanent, lookup) for permanent in battlefield)


def _thing(permanent: Permanent, lookup: CardLookup) -> Thing:
    """One permanent. A card with no facts is named by its id and flagged."""
    facts = lookup.facts(permanent.card.oracle_id)
    if facts is None:
        # No facts means we do not know whether it is a creature, so the flag
        # is not claimed either way -- the card is flagged unreadable and the
        # player is told to look at it.
        return Thing(
            name=lookup.name(permanent.card.oracle_id),
            tapped=permanent.tapped,
            unreadable=True,
        )
    return Thing(
        name=facts.name,
        tapped=permanent.tapped,
        # Only for creatures. The engine marks every permanent that arrived
        # this turn, because that is what the flag means; a land described as
        # "summoning sick" reads as a restriction that does not exist, and this
        # text is going in front of somebody learning what the phrase means.
        summoning_sick=permanent.summoning_sick and facts.is_creature,
        power=facts.power,
        toughness=facts.toughness,
        keywords=tuple(sorted(facts.keywords)),
        unreadable=not lookup.modelled(permanent.card.oracle_id),
    )
