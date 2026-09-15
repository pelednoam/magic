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
    #: The permanent the ability is printed on. "Put a +1/+1 counter on this
    #: creature" has no other way to name its subject.
    SELF = "self"
    #: The permanent an Aura or Equipment is attached to -- Pacifism's
    #: "enchanted creature", a Cutlass's "equipped creature".
    #:
    #: A separate kind from SELF, and the separation is the point. The card
    #: fixture used to say `self` for both, on a stated "Aura convention", and
    #: the engine read it as SELF means it. So Pacifism's "can't attack or
    #: block" was applied to *Pacifism*, an enchantment that could not do
    #: either anyway -- and because the combat layer treats a SELF restriction
    #: as one it can apply, the card was exempted from the "this is not in the
    #: numbers" caveat. Combat advice ignored the Pacifism on the table and
    #: said nothing about doing so.
    #:
    #: Nothing can act on this yet: ``Permanent`` has no attachments, so the
    #: engine cannot know which creature an Aura is on. That is exactly why it
    #: needs its own name -- a restriction on ENCHANTED is a restriction the
    #: engine must *disclose*, and one on SELF is one it can apply.
    ENCHANTED = "enchanted"


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


#: The ability's own source.
SELF = TargetSpec(kinds=frozenset({TargetKind.SELF}))

#: Whatever the Aura or Equipment carrying the ability is attached to.
ENCHANTED = TargetSpec(kinds=frozenset({TargetKind.ENCHANTED}))

#: The commonest spec in the box, by a wide margin.
ANY_CREATURE = TargetSpec(kinds=frozenset({TargetKind.CREATURE}))
