"""What is on the table, for a question that is about it.

The turn report does not carry the battlefield -- it does not need to, because
its attack plans already name the creatures that matter. A rules question does:
"can my creature block that one?" has two creatures in it and neither is in a
turn report. These check that both sides arrive, with the three properties
beginner questions actually turn on, and that a card the engine cannot read is
flagged rather than guessed at.
"""

from __future__ import annotations

import pytest

from helpers import ME, UNKNOWN_ABILITY, YOU, facts
from helpers_coach import Book, game, land, on_battlefield
from mtgcoach.coach.table import Thing, table
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import PlayerId
from mtgcoach.core.player import PlayerState
from mtgcoach.core.state import GameState
from mtgcoach.core.steps import Step

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
FLYER = facts("Bird", "{1}{U}", "Flying", power=1, toughness=1, creature=True)
ODD = facts("Odd Thing", "{1}")
ANGEL = facts("Dazzling Angel", "{2}{W}", "Flying", power=2, toughness=3, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR, "Bird": FLYER, "Odd": ODD},
    rules={"Forest": FOREST_RULES, "Bear": (), "Bird": (), "Odd": (UNKNOWN_ABILITY,)},
)


def test_both_sides_arrive_on_the_right_side() -> None:
    board = table(game(battlefield=("Bear",), theirs=("Bird",)), ME, BOOK)
    assert [thing.name for thing in board.yours] == ["Grizzly Bears"]
    assert [thing.name for thing in board.theirs] == ["Bird"]


def test_an_empty_battlefield_is_empty_rather_than_missing() -> None:
    board = table(game(), ME, BOOK)
    assert board.yours == ()
    assert board.theirs == ()


def test_stats_and_keywords_come_from_the_card() -> None:
    (bird,) = table(game(battlefield=("Bird",)), ME, BOOK).yours
    assert (bird.power, bird.toughness) == (1, 1)
    assert bird.keywords == ("Flying",)


def test_a_card_with_no_fixed_power_keeps_it_unset() -> None:
    """A silent zero makes a Consuming Aberration look harmless. See CardFacts."""
    book = Book(cards={"Star": facts("Starfish", "{1}", creature=True)}, rules={"Star": ()})
    (thing,) = table(game(battlefield=("Star",)), ME, book).yours
    assert thing.power is None
    assert "1/1" not in thing.described()


def test_tapped_and_sick_are_reported() -> None:
    mine = PlayerState(
        library=(),
        hand=(),
        battlefield=(
            on_battlefield("Bear", "1", tapped=True),
            on_battlefield("Bird", "2", sick=True),
        ),
        graveyard=(),
        exile=(),
    )
    state = GameState(
        turn=1,
        active_player=ME,
        step=Step.PRECOMBAT_MAIN,
        players={ME: mine, YOU: PlayerState((), (), (), (), ())},
    )
    bear, bird = table(state, ME, BOOK).yours
    assert bear.tapped
    assert not bear.summoning_sick
    assert bird.summoning_sick
    assert not bird.tapped


def test_a_card_the_book_cannot_model_is_flagged() -> None:
    (thing,) = table(game(battlefield=("Odd",)), ME, BOOK).yours
    assert thing.unreadable
    assert "CANNOT READ THIS CARD" in thing.described()


def test_a_card_the_book_has_never_heard_of_is_flagged_and_still_named() -> None:
    """Named by its identifier, which tells the player something true."""
    (thing,) = table(game(battlefield=("Mystery",)), ME, BOOK).yours
    assert thing.unreadable
    assert thing.name == "Mystery"
    assert thing.power is None


def test_a_thing_reads_as_a_person_would_say_it() -> None:
    said = Thing("Bird", tapped=True, power=1, toughness=1, keywords=("Flying",)).described()
    assert said == "Bird, 1/1, Flying, tapped"


def test_a_plain_permanent_is_just_its_name() -> None:
    assert Thing("Forest").described() == "Forest"


def test_the_other_player_is_whoever_is_not_you() -> None:
    """Asked from the other seat, the sides swap."""
    board = table(game(battlefield=("Bear",), theirs=("Bird",)), YOU, BOOK)
    assert [thing.name for thing in board.yours] == ["Bird"]
    assert [thing.name for thing in board.theirs] == ["Grizzly Bears"]


def test_a_player_who_is_not_in_the_game_is_refused() -> None:

    with pytest.raises(IllegalEventError):
        table(game(), PlayerId("nobody"), BOOK)


def test_a_card_with_rules_text_arrives_with_the_text_and_not_a_warning() -> None:
    """What R07 was about, on the board summary's side of it.

    A permanent with rules text used to be listed as "has rules text not shown
    here", which told a model an instruction existed and left it to remember
    which. The line is now just the board, and the instruction comes with it in
    ``cards`` -- so the warning has gone because it is no longer true.
    """
    book = Book(
        cards={"Angel": ANGEL},
        rules={"Angel": ()},
        texts={"Angel": "Flying\nWhenever another creature you control enters, you gain 1 life."},
    )
    board = table(game(battlefield=("Angel",)), ME, book)
    (thing,) = board.yours
    assert "not shown here" not in thing.described()
    assert [card.text for card in board.cards] == [
        "Flying\nWhenever another creature you control enters, you gain 1 life."
    ]


def test_a_vanilla_creature_says_nothing_extra() -> None:
    (bear,) = table(game(battlefield=("Bear",)), ME, BOOK).yours
    assert bear.described() == "Grizzly Bears, 2/2"


def test_the_board_carries_the_text_of_every_card_on_it() -> None:
    """One object, so a prompt cannot be given the lines without the text.

    The board lines no longer warn that a card's text is missing, so a caller
    that had the lines and not the text would describe an ability-laden board
    as if every creature on it were vanilla -- which is the failure this fixed,
    reintroduced by a forgotten argument.
    """
    book = Book(
        cards={"Bear": BEAR, "Bird": FLYER},
        rules={"Bear": (), "Bird": ()},
        texts={"Bird": "Flying"},
    )
    board = table(game(battlefield=("Bear",), theirs=("Bird",)), ME, book)
    assert [(card.name, card.text) for card in board.cards] == [
        ("Grizzly Bears", ""),
        ("Bird", "Flying"),
    ]
