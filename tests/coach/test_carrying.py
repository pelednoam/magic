"""Describing what a card does, and doing it, are different claims.

``modelled`` answers the first. Nothing answered the second, so Giant Growth
came back playable with nothing said: its +3/+3 is described in the sealed
fixture, which is what ``modelled`` measures, and the reducer has no effect
execution at all. The tracker accepted the cast, moved the card to the
graveyard, and no toughness changed -- after which every number it showed was
computed from a board wrong by three points.
"""

from __future__ import annotations

from helpers import facts
from helpers_coach import Book, taps_for
from mtgcoach.core.abilities import (
    SpellAbility,
    StaticModifier,
    StaticRestriction,
    Trigger,
    TriggeredAbility,
    UnmodeledAbility,
)
from mtgcoach.core.carrying import carried_out, not_carried_out
from mtgcoach.core.effects import ModifyStats
from mtgcoach.core.ids import OracleId
from mtgcoach.core.targets import ANY_CREATURE, ENCHANTED, SELF
from mtgcoach.core.vocabulary import Duration, Restriction, TriggerEvent

GROWTH = SpellAbility((ModifyStats(3, 3, ANY_CREATURE, Duration.UNTIL_END_OF_TURN),))
ANTHEM = StaticModifier(1, 0, ANY_CREATURE)
CANT_BLOCK = StaticRestriction(Restriction.CANT_BLOCK, SELF)
PACIFISM = StaticRestriction(Restriction.CANT_ATTACK, ENCHANTED)
ON_ENTER = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())


def test_nothing_to_do_is_carried_out() -> None:
    """A vanilla creature does what it says by being on the battlefield."""
    assert carried_out(())
    assert not_carried_out(()) == ()


def test_a_mana_ability_is_carried_out() -> None:
    """The one kind this engine genuinely performs.

    The solver reads it, and a payment spends it (CR 605.1a).
    """
    assert carried_out((taps_for("{G}"),))


def test_a_restriction_on_the_card_itself_is_carried_out() -> None:
    """Applied by leaving the creature out of the side it cannot join."""
    assert carried_out((CANT_BLOCK,))


def test_a_restriction_on_an_attached_permanent_is_not() -> None:
    """``Permanent`` has no attachments, so the engine cannot tell which."""
    assert not carried_out((PACIFISM,))
    assert not_carried_out((PACIFISM,)) == ("the restriction it puts on another permanent",)


def test_a_spell_effect_is_not_carried_out() -> None:
    """Giant Growth. The finding, in one assertion."""
    assert not carried_out((GROWTH,))
    assert not_carried_out((GROWTH,)) == ("what it does when it resolves",)


def test_a_modifier_a_trigger_and_an_inexpressible_ability_are_not() -> None:
    """Each named by the part of the card that will not happen."""
    assert not_carried_out((ANTHEM,)) == ("the power and toughness it changes",)
    assert not_carried_out((ON_ENTER,)) == ("its trigger",)
    assert not_carried_out((UnmodeledAbility("Whenever ...", "no schema for this"),)) == (
        "an ability nothing could express",
    )


def test_one_ability_it_cannot_do_is_enough() -> None:
    """A card is carried out or it is not. Partly is not a thing to report."""
    assert not carried_out((taps_for("{G}"), GROWTH))


def test_a_card_never_reviewed_is_not_reported_as_handled() -> None:
    """The flaw in the first version of this, found before it shipped.

    An unreviewed card has no recorded abilities, and so did a vanilla
    creature -- both an empty list. Asked of the abilities alone, 392 of the
    imported cards claimed to be fully carried out. The question has to be
    asked of the catalogue, which can tell absent from empty.
    """
    book = Book(cards={"Bear": facts("Grizzly Bears", creature=True)})
    assert book.not_carried_out(OracleId("Bear")) == (
        "anything it does -- this card has not been reviewed",
    )


def test_a_card_reviewed_and_found_plain_is_reported_as_handled() -> None:
    """The other side of that distinction, which is the point of it."""
    book = Book(cards={"Bear": facts("Grizzly Bears", creature=True)}, rules={"Bear": ()})
    assert book.not_carried_out(OracleId("Bear")) == ()
