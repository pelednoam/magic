"""What a season reached, not just what it found.

A clean season is only reassuring in proportion to how much of a game of Magic
happened in it. Three hundred games in which nobody cast anything would be
three hundred clean games, and a harness that cannot tell those apart is not
evidence.

Written after a real miss: the deck pairings were walked in index order, so a
twelve-game coached season -- the expensive one -- played `cats` nine times.
Nothing reported it, because nothing was measuring it.
"""

from __future__ import annotations

from helpers_selfplay import BOOK, THEM, YOU, game

from mtgcoach.core.ids import PlayerId
from mtgcoach.selfplay.dealing import pairings
from mtgcoach.selfplay.moves import Idle, Seat
from mtgcoach.selfplay.playing import play
from mtgcoach.selfplay.policy import Greedy
from mtgcoach.selfplay.records import Game, Reached, Season

DECKS = ["cats", "elves", "goblins", "healing"]


def test_every_pairing_is_played_before_any_repeats() -> None:
    """A short season should be a spread, not a sample with holes."""
    every = pairings(DECKS, seed=0)
    assert len(every) == len(set(every)) == 12


def test_a_short_season_is_not_all_one_deck() -> None:
    """The bug this exists for.

    Walking `permutations` in order put the alphabetically first deck on one
    side of every early pairing, so twelve coached games at twenty minutes
    each spent three quarters of the budget on `cats`.
    """
    firsts = {first for first, _ in pairings(DECKS, seed=7)[:6]}
    assert len(firsts) > 1


def test_the_seed_chooses_which_spread() -> None:
    """Two runs differ, and either can be repeated."""
    assert pairings(DECKS, seed=1) != pairings(DECKS, seed=2)
    assert pairings(DECKS, seed=1) == pairings(DECKS, seed=1)


def test_a_game_records_what_it_reached() -> None:
    seats = (Seat(YOU, "x", Greedy(seed=1)), Seat(THEM, "y", Greedy(seed=2)))
    played = play(seats, game(), BOOK, seed=1)
    assert played.reached.lands > 0, "no land was ever played"
    assert played.reached.spells > 0, "nothing was ever cast"
    assert played.reached.biggest_board > 1, "no board ever grew"


def test_a_game_where_nothing_happened_says_so() -> None:
    """Two idle agents walk every step and reach nothing.

    Which is the point: the number distinguishes that from a real game.
    """
    seats = (Seat(YOU, "x", Idle()), Seat(THEM, "y", Idle()))
    played = play(seats, game(), BOOK, seed=1)
    assert played.clean
    assert played.reached.lands == 0
    assert played.reached.spells == 0
    assert played.reached.attacks == 0


def test_a_season_sums_what_its_games_reached() -> None:
    one = Game(
        seed=1,
        decks=("a", "b"),
        turns=1,
        winner=None,
        ending="life",
        reached=Reached(lands=3, spells=1, attacks=2, biggest_board=4, triggers=1),
    )
    two = Game(
        seed=2,
        decks=("b", "c"),
        turns=1,
        winner=None,
        ending="life",
        reached=Reached(lands=2, spells=5, attacks=0, biggest_board=9, triggers=0),
    )
    total = Season(games=(one, two)).reached
    assert (total.lands, total.spells, total.attacks, total.triggers) == (5, 6, 2, 1)
    assert total.biggest_board == 9, "the biggest board is the biggest, not the sum"


def test_a_season_names_the_decks_it_played() -> None:
    one = Game(seed=1, decks=("cats", "elves"), turns=1, winner=None, ending="life")
    two = Game(seed=2, decks=("elves", "goblins"), turns=1, winner=None, ending="life")
    run = Season(games=(one, two))
    assert run.decks == ("cats", "elves", "goblins")
    assert run.pairings == 2


def test_the_same_matchup_twice_counts_once() -> None:
    same = Game(seed=1, decks=("cats", "elves"), turns=1, winner=None, ending="life")
    assert Season(games=(same, same)).pairings == 1


def test_an_empty_season_reached_nothing() -> None:
    assert Season().reached == Reached()
    assert Season().decks == ()
    assert Season().pairings == 0


def test_the_winner_is_named_by_seat() -> None:
    """Kept here because `decks` is a property now and easy to break."""
    won = Game(seed=1, decks=("a", "b"), turns=1, winner=PlayerId("you"), ending="life")
    assert Season(games=(won,)).decks == ("a", "b")
