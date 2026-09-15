"""What a season is, and playing one.

Split from ``cli`` so the command line is argparse and nothing else. The seam
is also the useful one for a caller that is not a terminal: a test, or a future
route, wants ``season(Run(...))`` and has no use for flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final
from uuid import uuid4

from mtgcoach.api.cards import build
from mtgcoach.api.claude import Cli
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.api.sources import Sources
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from mtgcoach.core.revision import engine
from mtgcoach.selfplay import dealing, playing
from mtgcoach.selfplay.answers import read
from mtgcoach.selfplay.coached import Coached
from mtgcoach.selfplay.journal import Journal
from mtgcoach.selfplay.moves import Seat
from mtgcoach.selfplay.policy import Greedy
from mtgcoach.selfplay.records import Game, Season
from mtgcoach.selfplay.replaying import Replayed

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState

#: The set the Beginner Box is, and the only one imported so far.
DEFAULT_SET: Final = SetCode("FDN")

#: An agent that keeps a tally: the coach, or a replay of one.
type Scored = Coached | Replayed


@dataclass(frozen=True, slots=True)
class Which:
    """Which game of the season this is.

    Three things that always travel together, and now travel as one rather than
    as three more positional arguments. ``id`` is what joins a game's decisions
    to its recording exactly; ``seed`` reproduces the deal and is a label
    beside it, because two runs of a season repeat it.
    """

    seed: int
    id: str
    decks: tuple[str, str]


@dataclass(frozen=True, slots=True)
class Run:
    """What to play.

    One object because ``season`` is otherwise seven arguments, six of which
    are paths and names that always travel together.
    """

    db: Path = Path("data/cards.sqlite3")
    data_root: Path = Path("data")
    set_code: SetCode = DEFAULT_SET
    games: int = 50
    seed: int = 0
    #: Whether the coach plays. One subprocess per decision, so a game is
    #: minutes rather than milliseconds -- see ``coached``.
    coach: bool = False
    #: Where to write every decision, so the season can be run again. A
    #: coached season without one cannot be: the coach is a language model,
    #: and a seed does not reproduce it.
    journal: Path | None = None
    #: A journal to play back instead of asking. See ``replaying``.
    replay: Path | None = None


def season(run: Run) -> Season:
    """Play ``run.games`` games, pairing every deck against another.

    Raises:
        ValueError: If the set has no cards imported.
    """
    db, data_root, set_code = run.db, run.data_root, run.set_code
    games, seed = run.games, run.seed
    with CardStore.open(str(db)) as store:
        cards = store.cards_in_set(set_code)
        if not cards:
            msg = f"no {set_code} cards in {db}; run `mtgcoach sets add {set_code}` first"
            raise ValueError(msg)
        catalogue = build(cards, effects_path(data_root, set_code))
        names = {card.name: card.oracle_id for card in cards}

    # What this season is played under, recorded on every game it writes. The
    # rules revision is deliberately absent: no rules document is consulted
    # here, so claiming one would be recording something that did not happen.
    sources = Sources(engine=engine(), cards=catalogue.revision)

    decks = dealing.table(data_root, set_code, names)
    if len(decks) < dealing.PLAYERS:
        msg = (
            f"only {len(decks)} {set_code} deck(s) can be dealt from {db}; "
            f"the import does not cover them. Run `mtgcoach sets add {set_code}`."
        )
        raise ValueError(msg)
    pairs = dealing.pairings(sorted(decks), seed)
    played: list[Game] = []
    tallies: list[Scored] = []
    for number in range(games):
        this = seed + number
        # One id per game, so the decisions written during it and the recording
        # written at the end of it can be joined exactly. A seed says which
        # *deal*; run the same season twice into one journal and it repeats.
        chosen = pairs[number % len(pairs)]
        which = Which(seed=this, id=uuid4().hex, decks=chosen)
        seats = tuple(
            Seat(seat, deck, _agent(run, which, offset, tallies))
            for offset, (seat, deck) in enumerate(
                ((dealing.YOU, chosen[0]), (dealing.THEM, chosen[1]))
            )
        )
        state = dealing.dealt(decks, chosen, this)
        finished = playing.play((seats[0], seats[1]), state, catalogue, this)
        played.append(finished)
        _recorded(run, which, state, finished, sources)
    return Season(games=tuple(played), coaching=tuple(agent.tally for agent in tallies))


def _recorded(run: Run, which: Which, dealt: GameState, game: Game, sources: Sources) -> None:
    """Write the game itself beside its decisions, if there is a journal.

    The decisions alone replay a game inside the harness. This is what lets
    anything *else* rebuild it -- the API serves a step-through of the game
    from the libraries and the event log, using `core` and nothing more.
    """
    if run.journal is None:
        return
    Journal(run.journal).write_game(
        Recording(
            seed=which.seed,
            game=which.id,
            decks=which.decks,
            first=str(dealt.active_player),
            libraries=dealt_as(dealt),
            events=game.log,
            sources=sources,
        )
    )


def _agent(run: Run, which: Which, offset: int, kept: list[Scored]) -> Greedy | Scored:
    """One seat's agent, and a handle on its tally if it keeps one.

    The two coached kinds share a seed with the game rather than with the
    seat, because a journal is keyed by the game -- the seat is in the key
    separately.
    """
    if run.replay is not None:
        playing_back = Replayed(
            answers=read(run.replay),
            seed=which.seed,
            game=which.id,
            journal=Journal(run.journal) if run.journal is not None else None,
        )
        kept.append(playing_back)
        return playing_back
    if not run.coach:
        return Greedy(seed=which.seed + offset)
    asking = Coached(
        explainer=ClaudeCliExplainer(Cli()),
        seed=which.seed,
        game=which.id,
        journal=Journal(run.journal) if run.journal is not None else None,
    )
    kept.append(asking)
    return asking
