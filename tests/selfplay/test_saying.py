"""A season, as something worth reading.

The output is the product: somebody reads it to decide what to do next, so it
has to lead with what went wrong and the seed that reproduces it.
"""

from __future__ import annotations

from mtgcoach.core.ids import PlayerId
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.coached import Tally
from mtgcoach.selfplay.records import Game, Kind, Season, Trouble
from mtgcoach.selfplay.saying import said

CLEAN = Game(seed=1, decks=("elves", "goblins"), turns=20, winner=PlayerId("you"), ending="life")


def test_a_clean_season_says_so() -> None:
    printed = said(Season(games=(CLEAN, CLEAN)))
    assert "2 games, 2 clean, 0 problem(s)" in printed
    assert "median" in printed


def test_a_problem_is_printed_with_the_seed_that_reproduces_it() -> None:
    """A seed is a whole game replayed exactly.

    That is the difference between finding a bug and finding it twice.
    """
    broken = Game(
        seed=42,
        decks=("cats", "pirates"),
        turns=9,
        winner=None,
        ending="decked",
        trouble=(Trouble(Kind.BROKEN, "lost a card", 9, Step.DRAW),),
    )
    printed = said(Season(games=(broken,)))
    assert "seed 42" in printed
    assert "cats v pirates" in printed
    assert "lost a card" in printed


def test_the_cards_nothing_can_speak_for_are_named() -> None:
    """The single most useful number for deciding what to work on next."""
    game = Game(
        seed=1,
        decks=("a", "b"),
        turns=1,
        winner=None,
        ending="life",
        unknown=tuple(f"Card {n}" for n in range(30)),
    )
    printed = said(Season(games=(game,)))
    assert "cards nothing can speak for (30)" in printed
    assert printed.rstrip().endswith("...")


def test_the_coachs_score_is_reported_when_it_played() -> None:
    tally = Tally(asked=10, refused=1, untrusted=2, disagreements=["named a card you cannot play"])
    printed = said(Season(games=(CLEAN,), coaching=(tally,)))
    assert "10 asked, 7 trusted, 2 failed checks, 1 no answer" in printed
    assert "disagreed: named a card you cannot play" in printed
