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
from mtgcoach.carddata.manifest import sha256_of
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
    #: What each card actually says, verbatim from the printing. A third
    #: mapping rather than a field on ``CardFacts``, because ``core`` reasons
    #: about cards and must not be handed prose it would be tempted to parse --
    #: this is here to be quoted into a prompt and nowhere else.
    texts: Mapping[str, str] = field(default_factory=dict[str, str])
    #: Which sealed bytes this was built from: the sha256 of the effects file,
    #: which is the same checksum its manifest records. Recorded on a game so
    #: that a journal says what its cards *did* at the time, not just what
    #: happened -- see ``sources``. Empty for a catalogue built without a
    #: fixture, which is every catalogue written in a test.
    revision: str = ""

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

    def text(self, oracle_id: OracleId) -> str:
        """The card's printed rules text, or empty when the store has no card.

        Empty is not the same as "this card does nothing": Aegis Turtle really
        has no rules text, and a card absent from the store has none on file
        here. ``modelled`` is what tells those apart, and the prompt prints
        both -- the text when there is some, and the fact that there is none
        when there is not.
        """
        return self.texts.get(str(oracle_id), "")

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

    A card whose cost the parser refuses is left out of ``cards`` rather than
    approximated. It is then simply a card the coach cannot speak for, which is
    a state the whole system already handles, and the alternative is a
    mispriced spell. Its *text* is kept even so: what the coach cannot reason
    about, a player can still read.
    """
    # Listed once: ``cards`` may be a generator, and it is now read twice --
    # for the facts and for the printed text.
    listed = list(cards)
    facts: dict[str, CardFacts] = {}
    for card in listed:
        try:
            facts[str(card.oracle_id)] = facts_for(card)
        except UnmodellableCardError:
            continue
    rules: dict[str, tuple[Ability, ...]] = {}
    revision = ""
    if effects is not None and effects.exists():
        rules = {str(c.oracle_id): tuple(c.abilities) for c in load(effects)}
        # Checksummed here rather than read out of the manifest beside it: this
        # is the revision of the bytes actually loaded, and a manifest that
        # disagrees with them is the thing `mtgcoach effects check` exists to
        # catch. Recording what was read cannot inherit that disagreement.
        revision = sha256_of(effects)
    # Keyed off ``cards`` rather than ``facts``: a card whose cost the parser
    # refused is one the coach cannot reason about, and its text is exactly
    # what a player asking about it needs to see.
    texts = {str(card.oracle_id): _printed(card) for card in listed}
    return Catalogue(cards=facts, rules=rules, texts=texts, revision=revision)


def _printed(card: Card) -> str:
    """One card's rules text, with each face named when it has more than one.

    A transform or adventure card has no top-level text at all -- both halves
    live on the faces -- so a prompt built from the front face alone would
    quote half a card and look complete. Naming the faces is what makes the
    two halves readable as two halves.
    """
    if not card.is_multifaced:
        return card.front.oracle_text
    return "\n".join(f"{face.name}: {face.oracle_text}" for face in card.faces)
