"""The harness writes a journal; the API reads it. This is that seam.

Two services, two formats written by hand, and no type that spans them -- by
design, because the alternative was a dependency cycle (the API has to read a
journal, and the harness already depends on the API). What keeps the two halves
honest is this: a line written by ``journal`` and ``recording``, read back by
``replays``, and checked against what was put in.

Without it, a field renamed on one side would go quiet: the reader is defensive
by necessity -- a journal is a file that a killed process may have truncated --
so a decision it no longer understands comes back as a moment with no advice
rather than as an error. Exactly the failure a child would find at the table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.api.replays import games_in
from mtgcoach.coach.advice import Explanation
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import AdvanceStep
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import Step
from mtgcoach.selfplay import journal
from mtgcoach.selfplay.journal import Decision, Journal

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.state import GameState

SEED = 11

#: Ten cards, which is an opening hand and three to draw.
DECK = tuple(f"Card {n}" for n in range(10))

SAID = Explanation(
    play="you-7",
    attack=("you-8",),
    because="It is the only land you can still play this turn.",
    in_short="Play the land.",
    watch_out=("They are holding two cards.",),
    check_yourself=("Did you already play a land?",),
)


def dealt() -> GameState:
    """A game to write down."""
    return start_game(
        {
            PlayerId(seat): tuple(
                CardInstance(InstanceId(f"{seat}-{n}"), OracleId(name))
                for n, name in enumerate(DECK)
            )
            for seat in ("you", "them")
        },
        first_player=PlayerId("you"),
    )


def test_a_journal_the_harness_wrote_is_one_the_api_can_walk(tmp_path: Path) -> None:
    """End to end across the two services, in the order they really happen."""
    state = dealt()
    path = tmp_path / "selfplay" / "season.jsonl"
    written = Journal(path)
    written.write(
        Decision(
            seed=SEED,
            turn=1,
            step=str(Step.UPKEEP),
            player="you",
            briefing="the board, as the model was shown it",
            answer=journal.fields(SAID),
            trusted=True,
        )
    )
    written.write_game(
        Recording(
            seed=SEED,
            decks=("elves", "goblins"),
            first="you",
            libraries=dealt_as(state),
            events=(AdvanceStep(),),
        )
    )

    (game,) = games_in(tmp_path, "season")
    assert game.seed == SEED
    assert game.decks == ("elves", "goblins")
    (moment,) = game.moments
    assert moment.step is Step.UPKEEP
    assert moment.player == "you"
    assert moment.trusted
    # The whole answer, field by field. A rename on either side lands here.
    assert moment.said == SAID
    # And the board is the one the harness dealt, not one shaped like it.
    assert moment.state.players[PlayerId("you")].hand == state.players[PlayerId("you")].hand


def test_the_game_id_is_what_joins_the_two_halves(tmp_path: Path) -> None:
    """Written by the harness on every line of a game, read by the API.

    The one field that makes the join exact. A seed says which *deal* and two
    runs of a season repeat it; position in the file is defeated by a run
    killed mid-game with another appended after it. Both halves are written by
    hand, so this is the test that keeps them agreeing on the name of it.
    """
    state = dealt()
    path = tmp_path / "selfplay" / "ids.jsonl"
    written = Journal(path)
    # The same moment of the same deal, twice: only the game id separates them.
    for game_id, seat in (("first-game", "them"), ("second-game", "you")):
        written.write(
            Decision(
                seed=SEED,
                game=game_id,
                turn=1,
                step=str(Step.UPKEEP),
                player=seat,
                briefing="",
                answer=journal.fields(SAID),
                trusted=True,
            )
        )
    # Both games carry the same seed, which is what a season re-run produces.
    written.write_game(
        Recording(
            seed=SEED,
            game="second-game",
            decks=("elves", "goblins"),
            first="you",
            libraries=dealt_as(state),
            events=(AdvanceStep(),),
        )
    )

    (game,) = games_in(tmp_path, "ids")
    # Only the second game's decision, though both sit in its stretch of file
    # and both carry its seed.
    assert [one.player for one in game.moments] == ["you"]
