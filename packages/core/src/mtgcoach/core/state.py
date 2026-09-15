"""The whole game state, and how a game starts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mtgcoach.core import stack as stackzone
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.player import OPENING_HAND_SIZE, PlayerState
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.results import Over
    from mtgcoach.core.stack import StackObject

#: A game has exactly two players. Multiplayer changes turn order, priority and
#: combat targeting; rejecting it here is cheaper than pretending to support it.
PLAYER_COUNT = 2


@dataclass(frozen=True, slots=True)
class GameState:
    """The complete state of a game in progress.

    Not hashable: ``players`` is a mapping. Every field is otherwise immutable,
    and every transition returns a new state, so a state can be stored, compared
    and replayed safely.

    """

    turn: int
    active_player: PlayerId
    step: Step
    players: Mapping[PlayerId, PlayerState]
    #: How the game ended, or None while it is still going. Set by the
    #: state-based action check at the priority boundary; see ``results``.
    #: Once set, the reducer refuses every event -- a finished game is not a
    #: position anybody may act in, and the tracker used to let one carry on.
    over: Over | None = None
    #: Every spell waiting to resolve, bottom first, one order for both seats
    #: (CR 405.1, CR 405.2). It was a tuple on each player; see ``stack`` for
    #: why two of them could not answer which spell resolves first, and
    #: ``ZoneName`` for what that arrangement was originally for.
    stack: tuple[StackObject, ...] = ()
    #: Who may act (CR 117.1), or None when nobody may -- the untap and cleanup
    #: steps, and the moment after everybody has passed. Defaulted to None
    #: because a game begins in the untap step, where that is the right answer;
    #: a board built by hand at a step that hands out priority has to say so,
    #: and ``turn.advance`` does it for every game that is actually played.
    priority: PlayerId | None = None
    #: Who has passed since the last action, in order (CR 117.4's "in
    #: succession"). Emptied by anything anybody does, which is what stops a
    #: stale pass letting a spell resolve unanswered.
    passed: tuple[PlayerId, ...] = ()

    def player(self, player_id: PlayerId) -> PlayerState:
        """Return one player's state.

        Raises:
            IllegalEventError: If ``player_id`` is not in this game.
        """
        try:
            return self.players[player_id]
        except KeyError as exc:
            msg = f"no such player: {player_id!r}"
            raise IllegalEventError(msg) from exc

    def with_player(self, player_id: PlayerId, state: PlayerState) -> GameState:
        """Return a copy with one player's state replaced."""
        return replace(self, players={**self.players, player_id: state})

    def opponent_of(self, player_id: PlayerId) -> PlayerId:
        """Return the other player."""
        self.player(player_id)
        return next(pid for pid in self.players if pid != player_id)

    def cards_of(self, player_id: PlayerId) -> Iterator[CardInstance]:
        """Every card this player owns, the shared stack included.

        The basis of the conservation invariant: no event may change how many
        cards this yields for a player. ``PlayerState.cards`` answered it while
        the stack was a field on the player; a shared stack means the question
        spans two objects, and this is the one place that composes them. A
        self-play season checks it on every event, which is how an ordering bug
        that loses a card would be found in the first hundred games rather than
        in the app.
        """
        yield from self.player(player_id).cards()
        yield from stackzone.controlled_by(self.stack, player_id)

    def cards(self) -> Iterator[CardInstance]:
        """Every card in the game, in every zone, for both players."""
        for player_id in self.players:
            yield from self.cards_of(player_id)


def start_game(
    libraries: Mapping[PlayerId, tuple[CardInstance, ...]],
    first_player: PlayerId,
) -> GameState:
    """Begin a game: shuffled libraries in, opening hands drawn.

    The caller shuffles. The engine never generates randomness, so a game is a
    pure function of its starting libraries and its event log -- which is what
    makes replay, undo and end-of-game review exact rather than approximate.

    Raises:
        ValueError: If there are not exactly two players, if ``first_player`` is
            not one of them, or if a library is too small for an opening hand.
    """
    if len(libraries) != PLAYER_COUNT:
        msg = f"a game has exactly {PLAYER_COUNT} players, got {len(libraries)}"
        raise ValueError(msg)
    if first_player not in libraries:
        msg = f"first player {first_player!r} is not in the game"
        raise ValueError(msg)

    players: dict[PlayerId, PlayerState] = {}
    for player_id, library in libraries.items():
        if len(library) < OPENING_HAND_SIZE:
            msg = (
                f"{player_id!r} needs at least {OPENING_HAND_SIZE} cards to draw "
                f"an opening hand, got {len(library)}"
            )
            raise ValueError(msg)
        players[player_id] = PlayerState(
            library=library[OPENING_HAND_SIZE:],
            hand=library[:OPENING_HAND_SIZE],
            battlefield=(),
            graveyard=(),
            exile=(),
        )

    return GameState(
        turn=1,
        active_player=first_player,
        step=Step.UNTAP,
        players=players,
    )
