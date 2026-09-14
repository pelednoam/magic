"""What mana you could make right now.

The mana solver takes ``ManaSource``s; the game state holds ``Permanent``s. This
is the step between, and it is where two rules that beginners lose games to get
applied: a tapped land makes nothing, and a land that arrived this turn is fine
but a *creature* that did is not (CR 302.6 -- summoning sickness stops a ``{T}``
cost, which is why Llanowar Elves does nothing the turn you play it, and why
haste has to be checked: the same rule exempts it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.abilities import ActivatedAbility
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.manacost import COLORS, ManaSource

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.permanents import Permanent


def available(battlefield: Sequence[Permanent], lookup: CardLookup) -> tuple[ManaSource, ...]:
    """Every source of mana this battlefield could tap right now."""
    found: list[ManaSource] = []
    for permanent in battlefield:
        card = lookup.facts(permanent.card.oracle_id)
        if card is None:
            continue
        colours = _colours_from(lookup.abilities(permanent.card.oracle_id), permanent, card)
        if colours is not None:
            found.append(ManaSource(permanent.instance_id, colours))
    return tuple(found)


def _colours_from(
    abilities: Sequence[Ability], permanent: Permanent, card: CardFacts
) -> frozenset[str] | None:
    """The colours this permanent could make, or None if it can make none.

    None and the empty set are different answers: the empty set is a source of
    *colourless* mana, which pays generic costs and ``{C}``.
    """
    if permanent.tapped:
        return None
    produced: set[str] = set()
    usable = False
    for ability in abilities:
        if not isinstance(ability, ActivatedAbility) or not _payable(ability, permanent, card):
            continue
        # CR 605.1a: a mana ability makes mana and does nothing else. Narrowing
        # here rather than through ``is_mana_ability`` because the type has to
        # come with it -- asking the property and then testing each effect again
        # left a branch that could not be false.
        making = [effect for effect in ability.effects if isinstance(effect, ProduceMana)]
        if not making or len(making) != len(ability.effects):
            continue
        usable = True
        for effect in making:
            produced |= colours_in(effect.mana)
    return frozenset(produced) if usable else None


def _payable(ability: ActivatedAbility, permanent: Permanent, card: CardFacts) -> bool:
    """Whether this ability's cost can be paid without help.

    A mana ability that costs mana is not a *source* of mana to the solver: it
    would have to be paid for out of the same pool the solver is trying to fill,
    and that is a loop this layer deliberately does not enter. Nothing in the
    Beginner Box has one; a filter land would, and would need a real answer.
    """
    if ability.cost.mana or ability.cost.sacrifice_self:
        return False
    if not (ability.cost.tap and permanent.summoning_sick and card.is_creature):
        return True
    # CR 302.6 exempts haste from both halves of summoning sickness: a hasty
    # creature can attack and can pay a {T} cost the turn it arrives. Ignoring
    # that told a player their hasty mana creature made nothing.
    return card.has("Haste")


def colours_in(mana: str) -> frozenset[str]:
    """The colours a produced-mana string could make.

    Read directly rather than parsed as a cost: ``{G}`` and ``{W}{U}`` are
    outputs, not prices, and a producer that makes two mana of two colours is
    still a source of both.
    """
    return frozenset(letter for letter in mana.upper() if letter in COLORS)
