"""Whether the engine can carry out what a card does, as opposed to describe it.

Two different claims, and conflating them is how a card came to be offered as
fully handled when nothing would happen if you played it.

``Catalogue.modelled`` answers the first: is this card's behaviour *represented*
in the sealed fixture, all the way down. Giant Growth's "+3/+3 until end of
turn" is -- there is a ``ModifyStats`` effect with the right numbers -- so it
counts as modelled, appears in the 52% figure, and is left out of the "cards
the coach cannot speak for" list.

Nothing carries it out. The reducer moves cards between zones; it has no effect
execution at all. So the tracker accepts the cast, puts the card in the
graveyard, and the creature's toughness never changes -- and every piece of
advice after that is computed from a board that is wrong by three points.

This answers the second claim. It is deliberately strict: a card counts only if
*every* ability it has is one the engine actually acts on, and there are two of
those. A mana ability, which the solver reads and the payment spends. A static
restriction on the card itself, which combat applies by leaving the creature out
of the side it cannot join. Everything else is described and not done.

A card with no abilities carries out trivially -- a vanilla Grizzly Bears does
what it says by being on the battlefield. **A card that has never been
reviewed also has no recorded abilities, and that is not the same thing**, so
the question is asked of the catalogue rather than of a bare list: only it can
tell an empty ability list from a missing one. The first version of this could
not, and reported 392 never-reviewed cards as fully handled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.abilities import ActivatedAbility, StaticRestriction
from mtgcoach.core.targets import TargetKind

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.abilities import Ability


def carried_out(abilities: Sequence[Ability]) -> bool:
    """Whether the engine acts on everything these abilities say."""
    return all(_acted_on(ability) for ability in abilities)


def not_carried_out(abilities: Sequence[Ability]) -> tuple[str, ...]:
    """What the engine will not do, in words, for a player who needs telling.

    Named by kind rather than by effect, because "the tracker will not apply
    its +3/+3" needs the numbers and this layer has the abilities. The sentence
    a player reads is built where the card's name is known; this says which
    part is missing.
    """
    return tuple(sorted({_missing(ability) for ability in abilities if not _acted_on(ability)}))


def _acted_on(ability: Ability) -> bool:
    """Whether this one ability is one the engine does something about."""
    if isinstance(ability, ActivatedAbility):
        # CR 605.1a. The solver reads these and a payment spends them, which is
        # the one kind of ability this engine genuinely performs.
        return ability.is_mana_ability
    if isinstance(ability, StaticRestriction):
        # Applied by leaving the creature out of the side it cannot join --
        # but only when its subject is the card itself. On anything else the
        # engine cannot tell which permanent is meant; see ``coach.statics``.
        return TargetKind.SELF in ability.affects.kinds
    return False


def _missing(ability: Ability) -> str:
    """Which kind of thing the engine will not do about this ability."""
    if isinstance(ability, ActivatedAbility):
        return "its activated ability"
    if isinstance(ability, StaticRestriction):
        return "the restriction it puts on another permanent"
    return _BY_KIND.get(type(ability).__name__, "what it does")


#: One phrase per ability kind, so the sentence a player reads names the part
#: of the card that will not happen rather than the card as a whole.
_BY_KIND = {
    "SpellAbility": "what it does when it resolves",
    "TriggeredAbility": "its trigger",
    "StaticModifier": "the power and toughness it changes",
    "UnmodeledAbility": "an ability nothing could express",
}
