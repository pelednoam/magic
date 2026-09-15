"""Checking an answer's load-bearing words against what the prompt carried.

Two directions matter and both are here. A claim whose arithmetic or whose
ability nothing in the prompt mentions has to be reported -- that is the
finding. And an answer that stays inside the same evidence has to pass, because
a check that refuses correct answers is a check somebody turns off, and it
would take the first half with it.

``test_grounding_shipped`` runs the same probe against the real Comprehensive
Rules and the real card database. These use the excerpt, which is where the
boundaries are cheap to write down.
"""

from __future__ import annotations

from helpers_rules import PASSAGES
from mtgcoach.rules.corpus import Kind, Passage
from mtgcoach.rules.grounding import Given, problems
from mtgcoach.rules.keywords import Keywords, keywords_in

TRAMPLE = [p for p in PASSAGES if p.reference in {"702.19b", "Trample"}]
KEYWORDS = keywords_in(PASSAGES)

#: A card whose text mentions an ability the excerpt defines, so that grounding
#: a claim *in the card* can be told apart from grounding it in a rule. The
#: excerpt defines three keywords -- deathtouch, reach and trample -- so the
#: cases here are written with those rather than with flying, which would make
#: every assertion below pass for the wrong reason.
STINGER = "Deathtouch\nWhenever this creature deals damage, you gain 1 life."


def _given(*cards: str, keywords: Keywords = KEYWORDS) -> Given:
    """The evidence a prompt carried besides the rules."""
    return Given(cards=cards, keywords=keywords)


# --- arithmetic ---------------------------------------------------------------


def test_the_probe_is_reported() -> None:
    """R07's own example, against the passage it cites."""
    said = problems("Trample doubles all damage. Your creature hits twice as hard.", TRAMPLE)
    assert said == ("says something is doubled, which no rule and no card it was given says",)


def test_an_answer_that_repeats_the_rule_is_not_reported() -> None:
    """The check must let through a correct answer about the same passage."""
    correct = (
        "Assign lethal damage to each blocking creature first, then the rest may go "
        "to the player. The extra damage still gets through."
    )
    assert problems(correct, TRAMPLE) == ()


def test_halving_and_tripling_are_reported_the_same_way() -> None:
    assert "halved" in problems("The damage is halved.", TRAMPLE)[0]
    assert "tripled" in problems("It deals triple damage.", TRAMPLE)[0]


def test_a_doubling_the_evidence_does_perform_is_allowed() -> None:
    """A rule that really does double something grounds a claim that it does.

    701.10e writes "double the number", so an answer saying a count is doubled
    is repeating the evidence rather than inventing arithmetic.
    """
    doubling = [Passage("701.10e", "Double", "To double the number of counters...", Kind.RULE)]
    assert problems("The number of counters is doubled.", doubling) == ()


def test_the_words_for_one_operation_are_interchangeable() -> None:
    """Twice and doubles are one operation, and the rules use both words.

    Requiring the answer's exact spelling would refuse a correct paraphrase of
    a rule that was right there in the prompt.
    """
    rule = [Passage("702.4b", "Second Step", "the creature deals that damage twice", Kind.RULE)]
    assert problems("The damage is doubled.", rule) == ()


def test_double_strike_is_read_as_an_abilitys_name_not_as_arithmetic() -> None:
    """Double strike doubles nothing: it adds a combat damage step (CR 702.4b).

    Both ways round. An answer that only names the ability is not making an
    arithmetic claim, and a passage that only names the ability does not ground
    one -- otherwise 702.4b would license "trample doubles all damage" simply
    by mentioning the word four times.
    """
    named = [Passage("702.4b", "Double Strike", "a creature with double strike...", Kind.RULE)]
    assert problems("A creature with double strike assigns damage in two steps.", named) == ()
    assert problems("Trample doubles all damage.", named) != ()


def test_the_unsure_field_is_not_scanned() -> None:
    """Only the prose is passed in, and that is the point.

    "These rules do not say whether the damage is doubled" is the sentence this
    project most wants written. Scanning it would refuse the admission and
    teach the model to leave it out, so the caller passes the answer and the
    child's sentence and nothing else -- see ``answer._said``.
    """
    assert problems("Assign lethal damage first.", TRAMPLE) == ()


# --- abilities ----------------------------------------------------------------


def test_an_ability_nothing_in_the_prompt_mentions_is_reported() -> None:
    """A real rule number and the wrong subject, which reads exactly as right."""
    said = problems("Your creature has deathtouch, so any damage is lethal.", TRAMPLE, _given())
    assert said == (
        "says something has deathtouch, which no rule and no card it was given mentions",
    )


def test_an_ability_a_supplied_rule_mentions_is_allowed() -> None:
    assert problems("The attacker has trample.", TRAMPLE, _given()) == ()


def test_an_ability_only_the_card_text_mentions_is_allowed() -> None:
    """What half (a) bought half (b).

    The trample passages say nothing about deathtouch, so before the card text
    was in the prompt this claim had nothing to be grounded against and the
    check would have refused a correct sentence about a creature on the board.
    """
    said = "Your creature has deathtouch, so one point of damage is enough."
    assert problems(said, TRAMPLE, _given(STINGER)) == ()
    assert problems(said, TRAMPLE, _given()) != ()


def test_a_keyword_word_used_as_ordinary_english_is_not_a_claim() -> None:
    """A hundred and sixty keywords are single real words.

    "Reach" is the one this project has already been bitten by; see
    ``keywords``. Refusing sentences that merely contain such a word would make
    the check a nuisance that gets switched off, and the arithmetic check would
    go with it -- so a word is a claim only where something is said to have it.
    """
    assert "reach" in KEYWORDS.names
    assert problems("These rules reach that far only in combat.", TRAMPLE, _given()) == ()


def test_an_ability_the_answer_defines_is_a_claim() -> None:
    """An answer that defines an ability is explaining it, however it is put."""
    said = problems("Deathtouch means any damage is lethal.", TRAMPLE, _given())
    assert "deathtouch" in said[0]


def test_nothing_is_checked_without_the_documents_keyword_names() -> None:
    """The list comes from the document, never from a list written in Python.

    There are 160 and Wizards add several a year, so the default is to check
    nothing rather than to check against a list that will be wrong by the next
    set. ``asking`` passes the index's names, and a test of the route asserts
    it does.
    """
    assert problems("Your creature has deathtouch.", TRAMPLE) == ()
