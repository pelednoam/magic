"""The real card data, in the shape the coach asks for.

``CardLookup`` is a Protocol with two methods; this is the implementation that
reads the two places a card is actually described. They are separate on purpose
and stay separate here:

- the **store** knows what a card *is* -- its types, its cost, its stats. It is
  imported from Scryfall and is as complete as Scryfall.
- the **sealed fixture** knows what a card *does*. It is model output that a
  person has reviewed and signed, and it covers 52% of the box.

A card can be in one and not the other, and the coach copes with either: no
facts means "I cannot speak for this card", no abilities means "I know what it
is but not what it does". Loaded once at startup, because a set is a few hundred
cards and a query per card per frame is not a thing to do at a kitchen table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.carddata.enginefacts import UnmodellableCardError, facts_for
from mtgcoach.carddata.sealed import load
from mtgcoach.core.abilities import unmodelled_reasons
from mtgcoach.core.carrying import not_carried_out

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from mtgcoach.carddata.cards import Card
    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import OracleId


@dataclass(frozen=True, slots=True)
class Catalogue:
    """Everything this server knows about cards, indexed by oracle id."""

    cards: Mapping[str, CardFacts] = field(default_factory=dict[str, "CardFacts"])
    rules: Mapping[str, tuple[Ability, ...]] = field(
        default_factory=dict[str, tuple["Ability", ...]]
    )

    def facts(self, oracle_id: OracleId) -> CardFacts | None:
        """The engine's view of the card, or None when it is not known."""
        return self.cards.get(str(oracle_id))

    def abilities(self, oracle_id: OracleId) -> Sequence[Ability]:
        """The card's reviewed abilities, empty when there are none."""
        return self.rules.get(str(oracle_id), ())

    def modelled(self, oracle_id: OracleId) -> bool:
        """Whether the sealed fixture covers this card, all the way down.

        Absent from the fixture is not modelled. Present with an
        ``UnmodeledAbility`` in it is not modelled either -- the extractor named
        what the card does and could not express it, which is the honest half of
        a 52% number and the half a player has to be told about.
        """
        abilities = self.rules.get(str(oracle_id))
        if abilities is None:
            return False
        return not any(unmodelled_reasons(ability) for ability in abilities)

    def not_carried_out(self, oracle_id: OracleId) -> tuple[str, ...]:
        """What the engine will not do if this card is played, in words.

        A different question from ``modelled``, which asks whether the card's
        behaviour is *described*. Giant Growth's +3/+3 is described, counts
        towards the 52% figure, and nothing carries it out -- so the tracker
        accepts the cast and no toughness changes, and every number it shows
        afterwards is computed from a board that is wrong by three points.

        Asked here rather than of the abilities alone because only this knows
        the difference between a card reviewed and found to have no abilities
        (a vanilla creature, which carries out fine) and a card never reviewed
        at all (about which nothing is known). They are both an empty list.
        """
        abilities = self.rules.get(str(oracle_id))
        if abilities is None:
            return ("anything it does -- this card has not been reviewed",)
        return not_carried_out(abilities)

    def name(self, oracle_id: OracleId) -> str:
        """The printed name, falling back to the identifier when unknown.

        The fallback is deliberate: a client showing a raw oracle id is telling
        the player something true -- this is a card the server cannot name --
        which is better than an empty space they will read as a bug.
        """
        card = self.cards.get(str(oracle_id))
        return card.name if card is not None else str(oracle_id)


def build(cards: Iterable[Card], effects: Path | None = None) -> Catalogue:
    """Index a set's cards, and the reviewed abilities for them if there are any.

    A card whose cost the parser refuses is left out rather than approximated.
    It is then simply a card the coach cannot speak for, which is a state the
    whole system already handles, and the alternative is a mispriced spell.
    """
    facts: dict[str, CardFacts] = {}
    for card in cards:
        try:
            facts[str(card.oracle_id)] = facts_for(card)
        except UnmodellableCardError:
            continue
    rules: dict[str, tuple[Ability, ...]] = {}
    if effects is not None and effects.exists():
        rules = {str(c.oracle_id): tuple(c.abilities) for c in load(effects)}
    return Catalogue(cards=facts, rules=rules)
