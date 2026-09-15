"""Reserving a slot or two for what the question's own paraphrases point at.

A phrase in ``phrasing`` is the rules' own wording for what a question asks, so
matching it is far better evidence than matching "cast" or "creature". In an OR
query of common words it loses anyway: bm25 normalises by length, and the rules
that answer a beginner's question are long. "Can I cast Giant Growth without a
creature?" put the phrase for CR 601.2c in the query, matched it, and ranked it
ninth of eight.

These are about the reservation, driven by a matcher written here rather than a
real index -- the ranking decision is what is being tested, not sqlite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.rules.corpus import Kind, Passage
from mtgcoach.rules.pointing import RESERVED, pointed_at

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mtgcoach.rules.pointing import Matcher

#: A question matching two entries of the map: a creature dying wants both the
#: definition (700.4) and the reason (lethal damage).
DYING = "when does my creature die from damage?"

#: And one matching none of them, which is most questions.
PLAIN = "how does trample work?"


def _passage(reference: str) -> Passage:
    """One passage, identified by its reference."""
    return Passage(
        reference=reference, title=reference, text=f"the text of {reference}", kind=Kind.RULE
    )


def _matcher(answers: Mapping[str, Sequence[str]]) -> Matcher:
    """A matcher that answers a phrase query from a script.

    Returns what it was asked for, so a test can say which phrase finds which
    passage and watch how the slots are filled.
    """

    def matching(wanted: str, limit: int) -> tuple[Passage, ...]:
        phrase = wanted.strip('"')
        return tuple(_passage(one) for one in answers.get(phrase, ())[:limit])

    return matching


def test_a_question_with_no_paraphrase_reserves_nothing() -> None:
    """Which is most questions, and must cost nothing."""
    assert pointed_at(_matcher({}), PLAIN, 8, 0) == ()


def test_each_phrase_contributes_its_best_hit() -> None:
    """One query per phrase, not one OR of all of them.

    The map lists its phrases most-precise-first and an OR throws that away:
    the common phrase wins the slot and the precise one is lost.
    """
    found = pointed_at(
        _matcher(
            {
                "put into a graveyard from the battlefield": ["700.4"],
                "lethal damage": ["Lethal Damage"],
            }
        ),
        DYING,
        8,
        0,
    )
    assert [p.reference for p in found] == ["700.4", "Lethal Damage"]


def test_no_more_than_the_reserved_number() -> None:
    """More would answer the map's question instead of the player's."""
    found = pointed_at(
        _matcher(
            {
                "put into a graveyard from the battlefield": ["700.4"],
                "lethal damage": ["704.5g"],
            }
        ),
        DYING,
        8,
        0,
    )
    assert len(found) <= RESERVED


def test_the_same_passage_is_not_reserved_twice() -> None:
    """Two phrases often point at one rule; it takes one slot, not two."""
    both = {
        "put into a graveyard from the battlefield": ["700.4"],
        "lethal damage": ["700.4"],
    }
    found = pointed_at(_matcher(both), DYING, 8, 0)
    assert [p.reference for p in found] == ["700.4"]


def test_a_phrase_that_matches_nothing_takes_no_slot() -> None:
    """The loop must not reserve an empty slot.

    Rare, because the map is checked against the installed document -- but a
    phrase can match the document and still lose to the limit.
    """
    found = pointed_at(_matcher({"lethal damage": ["704.5g"]}), DYING, 8, 0)
    assert [p.reference for p in found] == ["704.5g"]


def test_a_rule_named_by_number_leaves_less_room() -> None:
    """Half the answer at most, and the exact reference comes first.

    A question that both names a rule and paraphrases one would otherwise
    reserve six of eight slots between them, and the ranked search -- which is
    what answers the other 99% of questions -- would be squeezed out.
    """
    both = {
        "put into a graveyard from the battlefield": ["700.4"],
        "lethal damage": ["Lethal Damage"],
    }
    assert len(pointed_at(_matcher(both), DYING, 8, 3)) == 1
    assert pointed_at(_matcher(both), DYING, 8, 4) == ()
