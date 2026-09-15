"""The game itself, written down beside the decisions.

A journal's decision lines say what the coach was asked and what it answered.
That is enough to *replay* a game inside the harness, and not enough to show
one: a screen needs the board.

So a coached game also records what it takes to rebuild any moment of itself --
the libraries it was dealt and every event it applied, in order. Rebuilding is
then ``start_game`` and ``reduce.replay``, which is ``core`` and nothing else.
Two things follow, and both matter more than the bytes it costs:

- **Anything can read it.** The format lives here, in the API, rather than in
  the harness that writes it: the API has to *read* a journal and the harness
  already depends on the API, so putting it the other way round would be a
  dependency cycle.
- **It is exact.** The board is what those events produced, not a re-derivation
  that a later change to the engine could quietly alter. What a child is shown
  stepping through a game is what actually happened in it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.api.eventspec import written
from mtgcoach.api.sources import Sources
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.state import start_game

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState

#: What a line of this kind is called, so a reader can tell it from a decision.
KIND = "game"

#: What a card is written as: its instance id and its oracle id.
CARD_FIELDS = 2

#: The three revision fields, in the order a person reads them. One list, so
#: that the writer above and ``reading`` cannot disagree about the spelling of
#: a key -- which is the way a recorded revision silently becomes no revision.
SOURCE_FIELDS = ("engine", "cards", "rules")


@dataclass(frozen=True, slots=True)
class Recording:
    """One whole game: how it was dealt, and everything that happened."""

    seed: int
    decks: tuple[str, str]
    first: str
    #: The id the decisions of this game carry. Made once per game, so it joins
    #: them exactly -- see ``journal.Decision.game``. Empty for a recording
    #: written before this field existed.
    game: str = ""
    #: Each seat's library as it was dealt, before any hand was drawn.
    libraries: Mapping[str, tuple[tuple[str, str], ...]] = field(
        default_factory=dict[str, tuple[tuple[str, str], ...]]
    )
    events: tuple[Event, ...] = ()
    #: Which engine, card data and rules the game was played under. Empty
    #: fields for a recording written before this existed -- which is the whole
    #: of the migration: an old journal is *missing* this, not wrong about it,
    #: and refusing to open one over that would lose games nobody can replay
    #: again. See ``sources``.
    sources: Sources = field(default_factory=Sources)

    def opening(self) -> GameState:
        """The game as it began, hands drawn.

        Raises:
            ValueError: If the libraries are not two playable decks.
        """
        return start_game(
            {
                PlayerId(seat): tuple(
                    CardInstance(InstanceId(instance), OracleId(oracle))
                    for instance, oracle in cards
                )
                for seat, cards in self.libraries.items()
            },
            first_player=PlayerId(self.first),
        )

    def as_json(self) -> str:
        """One line, for appending to a journal."""
        return json.dumps(
            {
                "kind": KIND,
                "seed": self.seed,
                "game": self.game,
                "decks": list(self.decks),
                "first": self.first,
                "libraries": {
                    seat: [list(card) for card in cards] for seat, cards in self.libraries.items()
                },
                "events": [written(event) for event in self.events],
                # Written even when every field is empty, so that a reader can
                # tell "this journal predates the idea" from "this key was
                # dropped by something in between".
                "sources": dict(
                    zip(
                        SOURCE_FIELDS,
                        (self.sources.engine, self.sources.cards, self.sources.rules),
                        strict=True,
                    )
                ),
            },
            ensure_ascii=False,
        )


def dealt_as(state: GameState) -> dict[str, tuple[tuple[str, str], ...]]:
    """The libraries a game began with, as plain strings.

    Hand *then* library, which is the order they were dealt in: ``start_game``
    takes the opening hand off the front of the list it is given, so putting
    the library first hands back a differently-ordered deck and rebuilds a
    game that never happened. ``PlayerState.cards`` yields library first, which
    is what this used and why it did exactly that.

    Raises:
        ValueError: If anything has happened to the state already. A card
            anywhere but the hand or the library means this is not the deal,
            and no ordering of it would rebuild the game.
    """
    made: dict[str, tuple[tuple[str, str], ...]] = {}
    for seat, player in state.players.items():
        if player.battlefield or player.graveyard or player.exile:
            msg = f"{seat} has already played; this is not a game's opening state"
            raise ValueError(msg)
        made[str(seat)] = tuple(
            (str(card.instance_id), str(card.oracle_id)) for card in (*player.hand, *player.library)
        )
    return made
