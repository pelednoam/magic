"""Running a season, and saying what happened.

The output is the product, so it is written for somebody deciding what to do
next: what went wrong, and the seed that reproduces it. These cover the
reporting and the refusal to start without cards; the loop itself is
`test_playing`.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.store import CardStore
from mtgcoach.coach.advice import ExplainerError, Explanation
from mtgcoach.core.ids import PlayerId, SetCode
from mtgcoach.core.steps import Step
from mtgcoach.selfplay import cli
from mtgcoach.selfplay.cli import Run, main, said, season
from mtgcoach.selfplay.coached import Tally
from mtgcoach.selfplay.records import Game, Kind, Season, Trouble

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


def test_a_set_with_no_cards_imported_is_refused(tmp_path: Path) -> None:
    """The same refusal `serve` makes, and for the same reason.

    A coach with no cards answers "I cannot speak for this" to everything.
    """
    empty = tmp_path / "cards.sqlite3"
    with CardStore.open(str(empty)):
        pass
    with pytest.raises(ValueError, match="run `mtgcoach sets add"):
        season(Run(db=empty, data_root=tmp_path, games=1))


def test_the_command_line_refuses_the_same_way(tmp_path: Path) -> None:
    empty = tmp_path / "cards.sqlite3"
    with CardStore.open(str(empty)):
        pass
    with pytest.raises(ValueError, match="sets add"):
        main(["--db", str(empty), "--data", str(tmp_path), "--games", "1"])


#: The same fixture the API tests use: enough real Foundations cards for the
#: box decklists to be playable, without being all of Scryfall.
PLAYABLE = Path(__file__).resolve().parents[1] / "fixtures" / "scryfall_fdn_playable.json"
DATA = Path(__file__).resolve().parents[2] / "data"
FDN = SetCode("FDN")


def _full(tmp_path: Path) -> Path:
    """A card database the box decklists can actually be dealt from.

    The real one, when it is there: the whole point of a season is playing the
    decks somebody owns, and the small fixture covers only part of them.
    """
    real = DATA / "cards.sqlite3"
    if real.is_file():
        return real
    db = tmp_path / "cards.sqlite3"
    with CardStore.open(str(db)) as store:
        store.add((card, FDN) for card in cards_in(PLAYABLE))
    return db


def test_a_set_the_import_does_not_cover_is_refused(tmp_path: Path) -> None:
    """A partial import is named as one.

    Silently skipping a missing card built a library of zero and failed inside
    `start_game` with "needs at least 7 cards", which says nothing about the
    real problem.
    """
    db = tmp_path / "cards.sqlite3"
    with CardStore.open(str(db)) as store:
        store.add((card, FDN) for card in list(cards_in(PLAYABLE))[:3])
    with pytest.raises(ValueError, match="does not cover them"):
        season(Run(db=db, data_root=DATA, set_code=FDN, games=1))


def test_a_whole_season_runs_and_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The end-to-end shape, on the real Beginner Box decks.

    Two agents, two games -- and the thing this exists to say: whether
    anything went wrong.
    """
    db = _full(tmp_path)
    run = season(Run(db=db, data_root=DATA, set_code=FDN, games=2, seed=3))
    assert len(run.games) == 2
    assert run.clean == 2, run.trouble
    assert all(game.events > 50 for game in run.games)
    assert main(["--db", str(db), "--data", str(DATA), "--games", "1"]) == 0
    assert "1 games, 1 clean" in capsys.readouterr().out


def test_a_season_with_the_coach_asks_the_coach(tmp_path: Path) -> None:
    """Wiring only.

    The coach itself is `test_agents`; this is that `--coach` reaches it,
    which is the argument most easily left unthreaded.
    """
    db = _full(tmp_path)
    asked: list[str] = []

    class Counting:
        """An explainer that says nothing, loudly."""

        def explain(self, report: object, briefing: str) -> Explanation:
            """Refuse.

            Raises:
                ExplainerError: Always.
            """
            del report
            asked.append(briefing)
            msg = "not now"
            raise ExplainerError(msg)

    with mock.patch.object(cli, "ClaudeCliExplainer", return_value=Counting()):
        run = season(Run(db=db, data_root=DATA, set_code=FDN, games=1, seed=0, coach=True))
    assert asked, "the coach was never asked"
    assert run.coaching, "and its score was never kept"
    assert run.coaching[0].refused == run.coaching[0].asked
