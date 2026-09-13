"""What an effect applies to.

Grounded in the Beginner Box rather than invented: every field here exists
because a card in the box needs it. ``Deadly Riposte`` targets a *tapped*
creature, ``Elspeth's Smite`` an *attacking or blocking* one, ``Broken Wings``
an "artifact, enchantment, or creature with flying", and ``Prayer of Binding``
"up to one target nonland permanent an opponent controls".

Conditions are a closed enum rather than free text for the usual reason: a
string here would be unreadable by the engine and would quietly make a card look
supported when it was not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Controller(StrEnum):
    """Whose permanents an effect may choose among."""

    YOU = "you"
    OPPONENT = "opponent"
    ANY = "any"


class TargetKind(StrEnum):
    """What sort of object may be chosen."""

    CREATURE = "creature"
    PLAYER = "player"
    PLANESWALKER = "planeswalker"
    ARTIFACT = "artifact"
    ENCHANTMENT = "enchantment"
    LAND = "land"
    PERMANENT = "permanent"
    SPELL = "spell"
    CARD_IN_GRAVEYARD = "card_in_graveyard"


class Condition(StrEnum):
    """An extra restriction on what may be chosen."""

    ATTACKING = "attacking"
    BLOCKING = "blocking"
    TAPPED = "tapped"
    UNTAPPED = "untapped"
    HAS_FLYING = "has_flying"
    NONLAND = "nonland"
    ANOTHER = "another"


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """The set of things an effect may be pointed at.

    ``minimum`` of 0 expresses "up to one target", which is not the same as an
    untargeted effect: the spell is still cast, and may still be countered for
    having no legal target if one is chosen.
    """

    kinds: frozenset[TargetKind]
    controller: Controller = Controller.ANY
    conditions: frozenset[Condition] = field(default_factory=frozenset[Condition])
    minimum: int = 1
    maximum: int = 1

    @property
    def is_optional(self) -> bool:
        """Whether the effect may choose no target at all."""
        return self.minimum == 0


#: The commonest spec in the box, by a wide margin.
ANY_CREATURE = TargetSpec(kinds=frozenset({TargetKind.CREATURE}))
