"""The authoritative game, and the log it is derived from.

One game, held on the server, so the phone and the laptop are two views of it
rather than two copies. §4: clients send *events*, the server reduces them and
broadcasts; there is no CRDT because there is no distributed edit -- there is
one game and two people sitting next to each other.

The log is the game. State is carried alongside it as a cache, not as the
record, and ``Session.consistent`` asserts the two agree by replaying from the
start. That is what makes undo free, and it is why the cache is safe: if it ever
drifts, a test says so rather than a player discovering it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING
from uuid import uuid4

from mtgcoach.core.reduce import apply, replay
from mtgcoach.core.state import start_game

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.events import Event
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


class UnknownSessionError(KeyError):
    """No game by that name. A restarted server, or a stale link."""


@dataclass(frozen=True, slots=True)
class Session:
    """One game: where it started, everything that has happened, where it is."""

    session_id: str
    initial: GameState
    events: tuple[Event, ...]
    state: GameState
    #: How many times this game has *changed*, which is not how many events it
    #: has: undo removes an event and is itself a change. Counting events made
    #: this go backwards on undo, and the client -- which uses it to discard a
    #: stale reply -- discarded every undo instead. Only ever increases.
    revision: int = 0

    def with_event(self, event: Event) -> Session:
        """The session after one more event.

        Raises:
            IllegalEventError: If the reducer rejects the event.
        """
        return replace(
            self,
            events=(*self.events, event),
            state=apply(self.state, event),
            revision=self.revision + 1,
        )

    def undone(self) -> Session:
        """The session with its last event taken back.

        Replayed from the start rather than inverted. An undo that computes the
        opposite of an event is a second implementation of the rules, and the
        second one is always the one that is wrong.
        """
        if not self.events:
            return self
        kept = self.events[:-1]
        return replace(
            self,
            events=kept,
            state=replay(self.initial, kept),
            revision=self.revision + 1,
        )

    @property
    def consistent(self) -> bool:
        """Whether the cached state is what the log says it should be."""
        return replay(self.initial, self.events) == self.state


@dataclass(slots=True)
class SessionStore:
    """Every game this server is holding.

    In memory, deliberately. A game lasts an evening, the server runs on the
    laptop in the same room, and a database would be a second place for the
    truth to live. When it needs to survive a restart, the event log is already
    the thing to persist.
    """

    games: dict[str, Session] = field(default_factory=dict[str, "Session"])

    def create(
        self, libraries: Mapping[PlayerId, tuple[CardInstance, ...]], first_player: PlayerId
    ) -> Session:
        """Start a game and remember it."""
        state = start_game(libraries, first_player)
        session = Session(uuid4().hex, initial=state, events=(), state=state)
        self.games[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        """The game by that name.

        Raises:
            UnknownSessionError: If there is no such game.
        """
        try:
            return self.games[session_id]
        except KeyError as exc:
            raise UnknownSessionError(session_id) from exc

    def record(self, session: Session) -> Session:
        """Store an advanced session, replacing what was there."""
        self.games[session.session_id] = session
        return session
