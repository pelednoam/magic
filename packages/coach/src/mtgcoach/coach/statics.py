"""Static abilities: the ones combat can apply, and the ones it cannot.

The engine's combat simulator works on printed power and toughness. Seven cards
in the Beginner Box change that from the battlefield, and reporting exact damage
while ignoring them is the worst thing this project can do -- a confident wrong
number is worse than no number.

They split three ways, and the split is what this module is for:

- **Restrictions on the card itself.** Vampire Interloper "can't block" is a
  static ability whose subject is the creature carrying it. Applicable today,
  and applied: such a creature is left out of the side it cannot join.
- **Restrictions that need an attachment.** Pacifism says "enchanted creature
  can't attack or block", and ``Permanent`` has no attachments -- the engine
  cannot know which creature it is on. Not applicable, and *disclosed*.
- **Modifiers.** Goblin Oriflamme's +1/+0 to attackers, an Equipment's +2/+1.
  Both need either attachments or an "affects other creatures" rule the combat
  model does not have. Not applicable, and disclosed.

Disclosure is the whole point of the second and third groups. The caveat goes in
front of the player next to the numbers, so "four damage, lethal" is read as
"four damage, lethal -- unless the Pacifism on the table says otherwise".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.abilities import StaticModifier, StaticRestriction
from mtgcoach.core.targets import TargetKind
from mtgcoach.core.vocabulary import Restriction

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.permanents import Permanent


def restricts_itself(abilities: Sequence[Ability], restriction: Restriction) -> bool:
    """Whether these abilities stop the card *carrying* them doing something.

    ``affects`` pointing at SELF is the case the engine can act on without
    knowing what is attached to what: the ability and its subject are the same
    permanent.
    """
    return any(
        isinstance(ability, StaticRestriction)
        and ability.restriction is restriction
        and TargetKind.SELF in ability.affects.kinds
        for ability in abilities
    )


def cannot_attack(abilities: Sequence[Ability]) -> bool:
    """Whether this card's own abilities stop it attacking."""
    return restricts_itself(abilities, Restriction.CANT_ATTACK)


def cannot_block(abilities: Sequence[Ability]) -> bool:
    """Whether this card's own abilities stop it blocking."""
    return restricts_itself(abilities, Restriction.CANT_BLOCK)


def caveats(battlefields: Sequence[Sequence[Permanent]], lookup: CardLookup) -> tuple[str, ...]:
    """What is on the table that the combat numbers do not account for.

    Named per card, because "some things are not modelled" is not actionable
    and "the Pacifism is not accounted for" is.
    """
    found: list[str] = []
    for battlefield in battlefields:
        for permanent in battlefield:
            abilities = lookup.abilities(permanent.card.oracle_id)
            reason = _unapplied(abilities)
            if reason:
                found.append(f"{lookup.name(permanent.card.oracle_id)}: {reason}")
    return tuple(sorted(set(found)))


def _unapplied(abilities: Sequence[Ability]) -> str:
    """Why this card's static abilities are not in the numbers, if they are not."""
    if any(isinstance(ability, StaticModifier) for ability in abilities):
        return "its power/toughness change is not in these numbers"
    attached = [
        ability
        for ability in abilities
        if isinstance(ability, StaticRestriction) and TargetKind.SELF not in ability.affects.kinds
    ]
    if attached:
        return "it restricts another permanent, which the engine cannot track yet"
    return ""
