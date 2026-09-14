"""What a game and a season leave behind.

The report is the product, so it is a value rather than printed output -- and
that makes it something to test. Every property here is one somebody reads
when deciding what to work on next.
"""

from __future__ import annotations

from mtgcoach.core.ids import PlayerId
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.records import Game, Kind, Season, Trouble

CLEAN = Game(seed=1, decks=("elves", "goblins"), turns=20, winner=PlayerId("you"), ending="life")
BROKEN = Game(
    seed=2,
    decks=("cats", "pirates"),
    turns=9,
    winner=None,
    ending="decked",
    trouble=(Trouble(Kind.BROKEN, "you had 60 cards and now has 59", 9, Step.DRAW),),
)


def test_a_trouble_reads_as_a_bug_report() -> None:
    """A bug report needs the turn, the step and the seed.

    "It broke on turn 7's declare-attackers step, playing Elves, seed 3" is.
    """
    said = str(Trouble(Kind.BROKEN, "lost a card", 7, Step.DECLARE_ATTACKERS, PlayerId("you")))
    assert "turn 7" in said
    assert "declare_attackers" in said
    assert "[you]" in said
    assert "lost a card" in said


def test_a_trouble_with_no_actor_says_nothing_about_one() -> None:
    assert "[" not in str(Trouble(Kind.CRASH, "boom", 1, Step.UNTAP))


def test_a_game_with_nothing_wrong_is_clean() -> None:
    assert CLEAN.clean
    assert not BROKEN.clean


def test_a_season_counts_its_clean_games() -> None:
    assert Season(games=(CLEAN, BROKEN, CLEAN)).clean == 2


def test_a_season_gathers_every_trouble() -> None:
    assert len(Season(games=(CLEAN, BROKEN, BROKEN)).trouble) == 2


def test_an_empty_season_has_nothing_to_say() -> None:
    assert Season().clean == 0
    assert Season().trouble == ()
    assert Season().unknown == ()


def test_the_commonest_unknown_card_comes_first() -> None:
    """The list decides what to work on, so its order is the whole point."""
    rare = Game(seed=1, decks=("a", "b"), turns=1, winner=None, ending="life", unknown=("Rare",))
    common = Game(
        seed=2, decks=("a", "b"), turns=1, winner=None, ending="life", unknown=("Common", "Rare")
    )
    another = Game(
        seed=3, decks=("a", "b"), turns=1, winner=None, ending="life", unknown=("Common",)
    )
    assert Season(games=(rare, common, another)).unknown == ("Common", "Rare")
