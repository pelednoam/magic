"""Where the coach stops, and what it says when it gets there.

Two different silences, and both used to be one. A card the engine cannot
identify, and a card it can identify and cannot understand -- 59 of the
Beginner Box's 124 are the second kind. Plus the refusals: a board the solver
will not answer for exactly is a sentence on a card, never an exception.
"""

from __future__ import annotations

from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.report import advise

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
GROWTH = facts("Giant Growth", "{G}", instant=True)
OGRE = facts("Ogre", "{3}{R}", power=3, toughness=3, creature=True)

BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR, "Growth": GROWTH, "Ogre": OGRE},
    # A card is modelled when it has an entry here, even an empty one: a
    # vanilla creature is fully understood, it simply does nothing. A card
    # *missing* from this map is one the coach cannot speak for.
    rules={"Forest": FOREST_RULES, "Bear": (), "Growth": (), "Ogre": ()},
)


def test_a_card_the_fixture_cannot_express_is_named_too() -> None:
    """The failure that mattered: 59 of the box's 124 cards look like this.

    They are in the sealed fixture, they have perfectly good facts, and the
    extractor could not express what they do. Reporting only cards with no
    facts left every one of them looking fully understood -- so the coach gave
    confident advice about half the box with `unknown` empty.
    """
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Puzzle", "{2}{U}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    assert advise(game(hand=("Puzzle",)), ME, book).unknown == ("Puzzle",)


def test_a_vanilla_creature_is_fully_understood() -> None:
    """An empty ability list is an answer, not an absence.

    This is the distinction the fix turns on: `abilities()` returning nothing
    means either "it does nothing" or "I have never seen this card", and a
    coach that cannot tell them apart is guessing about one of them.
    """
    assert advise(game(hand=("Bear",)), ME, BOOK).unknown == ()


def test_a_card_missing_from_the_fixture_is_named() -> None:
    book = Book(cards={**BOOK.cards, "Absent": facts("Absent", "{1}")}, rules=BOOK.rules)
    assert advise(game(hand=("Absent",)), ME, book).unknown == ("Absent",)


def test_an_unknown_card_is_named_by_its_printed_name_when_there_is_one() -> None:
    """An oracle id helps nobody holding the card."""
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Chandra's Whatever", "{3}{R}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    assert advise(game(hand=("Puzzle",)), ME, book).unknown == ("Chandra's Whatever",)


def test_a_blocker_the_coach_cannot_identify_is_named() -> None:
    """It is left out of combat silently, so the attack maths would be wrong.

    The advisor reports exact damage and "nothing blocks"; the player is
    looking at a creature across the table that the coach never counted.
    """
    report = advise(game(battlefield=("Bear",), theirs=("Mystery",)), ME, BOOK)
    assert report.unknown == ("Mystery",)


def test_their_hand_is_not_looked_at() -> None:
    """Their battlefield is public. Their hand is the one thing §3 forbids."""
    state = game(battlefield=("Bear",), theirs=("Bear",))
    assert advise(state, ME, BOOK).unknown == ()


# --- the engine's refusals are answers, never errors -------------------------


def test_a_board_too_big_for_the_solver_is_a_reason_not_a_crash() -> None:
    """Seventeen untapped Forests, and the whole report used to be a 500.

    Worse than it sounds: the API records an event before building the advice,
    so one accepted event left a game that could never be read again.
    """
    state = game(hand=("Bear",), battlefield=("Forest",) * 17)
    (card,) = advise(state, ME, BOOK).hand
    assert not card.playable
    assert any("untapped sources" in reason for reason in card.reasons)


def test_the_rest_of_the_report_survives_it() -> None:
    report = advise(game(hand=("Bear",), battlefield=("Forest",) * 17), ME, BOOK)
    assert report.life == 20
    assert report.turn == 1
