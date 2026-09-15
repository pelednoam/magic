"""The evidence half of the prompt, section by section.

``test_question`` covers the instructions and the fence round the player's own
words. These cover what is quoted: the retrieved rules, the turn, the two
battlefields, and -- the section R07 was about -- what the cards actually say.

The budget has tests of its own because the failure it prevents is silent. A
prompt that grows with the board eventually gets truncated by something that
will not say so, and a card whose text was dropped without a word is exactly
the card a model will answer about from memory.
"""

from __future__ import annotations

from mtgcoach.coach.printed import PrintedCard
from mtgcoach.rules.evidence import MOST_CARD_TEXT, card_text, rules_found

ANGEL = PrintedCard(
    "Dazzling Angel",
    "Flying\nWhenever another creature you control enters, you gain 1 life.",
)
FOREST = PrintedCard("Forest", "({T}: Add {G}.)")


def test_the_cards_own_words_go_in_verbatim() -> None:
    """Verbatim, not the engine's model of them rendered back into prose."""
    said = card_text([ANGEL])
    assert "Whenever another creature you control enters, you gain 1 life." in said
    assert "Dazzling Angel" in said


def test_the_section_says_a_card_is_not_a_rule() -> None:
    """A model shown two verbatim quotations will otherwise cite the card.

    Only a rule reference may be cited -- the checker compares citations
    against the retrieved passages -- so an answer citing "Dazzling Angel" is
    thrown away, and it was thrown away for doing what the prompt implied.
    """
    assert "cite rules, not cards" in card_text([ANGEL])


def test_an_empty_position_prints_no_heading() -> None:
    """A heading with nothing under it reads as evidence that was lost."""
    assert card_text([]) == ""


def test_every_card_fits_in_the_default_budget_on_a_real_sized_board() -> None:
    """Twenty distinct cards of the longest Foundations text still fit.

    The set's longest card is 368 characters and its average is 139, against a
    kitchen-table position of perhaps fifteen distinct cards -- so the budget is
    not a limit a family reaches. This pins that: a budget that silently started
    cutting would make the section's promise -- here is what these cards say --
    false with nothing failing.
    """
    long = [PrintedCard(f"Card {at}", "x" * 368) for at in range(20)]
    assert "their text is not" not in card_text(long)


def test_a_board_past_the_budget_names_the_cards_it_could_not_quote() -> None:
    """The old "read the card" escape hatch, now applied only where it is true."""
    many = [PrintedCard(f"Card {at}", "x" * 500) for at in range(40)]
    said = card_text(many)
    assert "their text is not" in said
    assert "Card 39" in said
    assert len(said) < MOST_CARD_TEXT * 2


def test_a_card_that_fits_exactly_is_quoted() -> None:
    """The boundary, because an off-by-one here drops a card in silence."""
    said = card_text([FOREST], budget=len(FOREST.name) + len(FOREST.text))
    assert "Add {G}" in said
    assert "their text is not" not in said


def test_a_card_one_character_past_the_budget_is_named_instead() -> None:
    said = card_text([FOREST], budget=len(FOREST.name) + len(FOREST.text) - 1)
    assert "Add {G}" not in said
    assert "Forest" in said


def test_retrieving_nothing_says_so_and_forbids_answering_from_memory() -> None:
    said = rules_found([])
    assert "RULES FOUND: none" in said
    assert "not answer from memory" in said
