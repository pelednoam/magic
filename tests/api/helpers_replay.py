"""The recorded game a replay test walks: its cards, and its event log.

Written here rather than by importing the harness on purpose: the API has to
read a journal, and ``tests/selfplay/test_journal_is_readable.py`` is what pins
the two halves of that format together. This one is free to record a *small*
game -- one turn and a land drop -- so a test that walks it can be read in one
screen.

``helpers_journal`` writes this to disk beside a few decisions and serves it.
Split at the line limit, and the seam is where the test itself divides: this is
what was played, that is how it was written down.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from helpers import facts
from mtgcoach.api.cards import Catalogue
from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.api.sources import Sources
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import PlayLand
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.passing import ending

if TYPE_CHECKING:
    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState

#: The game every replay test walks.
SEED = 7

#: And what it was called, so a route can ask for it by name.
NAME = "demo"

#: The oracle ids a journal's libraries are dealt from. UUID-shaped on purpose:
#: a real oracle id is Scryfall's UUID (``carddata.scryfall`` reads it straight
#: off the card), *not* the printed name. A fixture that used names here let a
#: board render every card as a raw id and still pass -- which is exactly what
#: happened, and what ``CATALOGUE`` below now makes impossible.
FOREST = "11111111-1111-1111-1111-111111111111"
BEAR = "22222222-2222-2222-2222-222222222222"

#: What those ids are called. A replay's board must print these words.
NAMED = {FOREST: "Forest", BEAR: "Grizzly Bears"}

#: A catalogue that knows them, for a server serving replays.
CATALOGUE = Catalogue(
    cards={
        oracle: replace(
            facts(name, land=name == "Forest", creature=name != "Forest"),
            oracle_id=OracleId(oracle),
        )
        for oracle, name in NAMED.items()
    },
    rules=dict.fromkeys(NAMED, ()),
)

#: Ten cards each: seven for an opening hand and three to draw.
DECK = (FOREST, FOREST, FOREST, BEAR, FOREST, BEAR, FOREST, FOREST, BEAR, BEAR)


def library(seat: str) -> tuple[CardInstance, ...]:
    """One seat's deck, with ids that say which seat they came from."""
    return tuple(
        CardInstance(InstanceId(f"{seat}-{n}"), OracleId(oracle)) for n, oracle in enumerate(DECK)
    )


def opening() -> GameState:
    """The game as it was dealt."""
    return start_game(
        {seat: library(str(seat)) for seat in (PlayerId("you"), PlayerId("them"))},
        first_player=PlayerId("you"),
    )


def played() -> tuple[Event, ...]:
    """A first turn: walk to the main phase, play a land, walk to the end.

    Far short of a game, and enough for what a replay test needs -- a board
    that changes, and a step to hang each kind of decision on.

    Built by *replaying* rather than by counting, because a step no longer ends
    on request: it ends when both players have passed in succession (CR 500.2),
    and which of them still has to pass is a question only the state can
    answer. This used to be a count of ``AdvanceStep``s -- a recorded log no
    player could have produced, and a journal of those is one the engine would
    now refuse. That is the compatibility cost of the fix, and it is paid here
    rather than hidden.
    """
    events: list[Event] = []
    state = _walk(opening(), Step.PRECOMBAT_MAIN, events)
    drop = PlayLand(PlayerId("you"), InstanceId("you-0"))
    state = apply(state, drop)
    events.append(drop)
    _walk(state, Step.END_STEP, events)
    return tuple(events)


def _walk(state: GameState, to: Step, events: list[Event]) -> GameState:
    """Walk to ``to``, appending the events it took, and hand back where it got."""
    while state.step is not to:
        for event in ending(state):
            state = apply(state, event)
            events.append(event)
    return state


#: What the fixture game says it was played under. A made-up engine digest on
#: purpose: it is not this engine's, so a test can see the list route say which
#: revision has moved -- which is the whole reason a game records them.
SOURCES = Sources(engine="0the-old-one", cards="0the-old-cards", rules="July 1, 2024")


def recording(sources: Sources = SOURCES) -> Recording:
    """The whole game, ready to be written down."""
    return Recording(
        seed=SEED,
        decks=("green", "other"),
        first="you",
        libraries=dealt_as(opening()),
        events=played(),
        sources=sources,
    )


def board_at(step: Step) -> GameState:
    """The state on entering one step of the recorded game."""
    state = opening()
    seen = {state.step: state}
    for event in played():
        state = apply(state, event)
        seen.setdefault(state.step, state)
    return seen[step]
