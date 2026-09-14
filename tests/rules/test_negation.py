"""A question and its rule stating the same fact with opposite signs.

The rules write restrictions as requirements -- "the chosen creatures must be
untapped" -- and a question names the thing being restricted -- "can a tapped
creature block?". One fact, two polarities, no shared word, and stemming
cannot help: "tapped" stems to `tap` and "untapped" to `untap`, which is
correct, because they are opposites.

Half of these are about what the map does *not* fire on. A bridge that fires
too readily is worse than none: it puts an unrelated passage in a prompt that
holds only eight.
"""

from __future__ import annotations

import pytest

from helpers_rules import PASSAGES
from mtgcoach.rules.negation import (
    COMBAT_DAMAGE,
    MUST_BE_UNTAPPED,
    TARGETS,
    UNBLOCKED,
    spelled_out,
)
from mtgcoach.rules.search import RuleIndex
from mtgcoach.rules.terms import query


@pytest.mark.parametrize(
    "question",
    [
        "can a tapped creature block?",
        "can I attack with a tapped creature?",
        "can a tapped creature attack?",
        "is a tapped creature allowed to be a blocker?",
        "do tapped creatures still block",
        "can he block with a tapped creature",
    ],
)
def test_a_tapped_creature_in_combat_finds_the_requirement(question: str) -> None:
    """508.1a and 509.1a are the answer.

    The only phrase they share with the question is "must be untapped", which
    is to say none of it.
    """
    assert MUST_BE_UNTAPPED in spelled_out(question), question


@pytest.mark.parametrize(
    "question",
    [
        "what does tapped mean?",
        "how do I tap a creature for mana?",
        "when do my tapped lands untap?",
        "does a tapped land still count?",
    ],
)
def test_tapped_on_its_own_is_left_alone(question: str) -> None:
    """Both halves are required.

    "What does tapped mean?" wants the glossary; adding the combat restriction
    would push it out of a list that holds eight.
    """
    assert MUST_BE_UNTAPPED not in spelled_out(question), question


def test_a_question_already_using_the_rules_word_is_left_alone() -> None:
    """The map does not add a word the question already has.

    A word-boundary match on "tapped" does not fire inside "untapped" --
    there is no boundary between "un" and "tapped" -- so this needs no
    special case.
    """
    assert spelled_out("does my creature have to be untapped to block?") == ()


@pytest.mark.parametrize(
    "question",
    [
        "what happens if nobody blocks my creature?",
        "what happens if my creature is not blocked?",
        "what if it isn't blocked?",
        "what happens when no one blocks",
        "my creature was never blocked, now what?",
        "what if nothing blocks it?",
    ],
)
def test_nobody_blocked_it_finds_the_rules_word_for_that(question: str) -> None:
    """The rules have one word for this and a person has three."""
    assert UNBLOCKED in spelled_out(question), question


@pytest.mark.parametrize(
    "question",
    [
        "how does trample work when blocked?",
        "can two creatures block the same attacker?",
        "how much damage does an unblocked creature do?",
        "what does blocked mean?",
    ],
)
def test_an_ordinary_blocking_question_is_left_alone(question: str) -> None:
    assert UNBLOCKED not in spelled_out(question), question


def test_a_phrase_is_added_once_however_many_entries_match() -> None:
    added = spelled_out("if my tapped creature attacks and nobody blocks it, what happens?")
    assert sorted(added) == sorted(set(added))
    assert set(added) == {MUST_BE_UNTAPPED, UNBLOCKED, COMBAT_DAMAGE}


def test_nobody_blocking_asks_about_damage_as_well_as_the_word() -> None:
    """A question asking "what happens" never says the word for what happens.

    Without this the two glossary entries titled "Unblocked ..." took the top
    of the list -- a title match is weighted four times a body one -- and
    510.1b, the rule that says the damage goes to the player, was not in the
    top eight at all. Verified live: the answerer refused for want of a rule
    to cite.
    """
    assert COMBAT_DAMAGE in spelled_out("what happens if nobody blocks my creature?")


def test_every_phrase_this_can_add_is_really_in_the_rules() -> None:
    """A target the document does not contain adds nothing but noise.

    Here against the excerpt, which carries 509.1a and 510.1b verbatim; and
    against the installed document by `tools/check_rules_phrasing.py`.
    """
    corpus = "\n".join(f"{p.title}\n{p.text}" for p in PASSAGES).lower()
    assert [target for target in sorted(TARGETS) if target not in corpus] == []


def test_the_added_phrase_reaches_the_query_quoted() -> None:
    assert '"must be untapped"' in query("can a tapped creature block?")


def test_the_question_this_was_written_for_now_finds_its_rule() -> None:
    """The last miss in `tools/retrieval_questions.json`.

    It was written down as a known gap rather than deleted, which is how it
    came to be fixed.
    """
    with RuleIndex.build(PASSAGES) as index:
        found = [p.reference for p in index.search("can a tapped creature block?")]
    assert "509.1a" in found, found


def test_nobody_blocking_finds_the_damage_rule() -> None:
    with RuleIndex.build(PASSAGES) as index:
        found = [p.reference for p in index.search("what happens if nobody blocks my creature?")]
    assert "510.1b" in found, found
