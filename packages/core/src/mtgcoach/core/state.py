"""The whole game state, and how a game starts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.player import OPENING_HAND_SIZE, PlayerState
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import PlayerId

#: A game has exactly two players. Multiplayer changes turn order, priority and
#: combat targeting; rejecting it here is cheaper than pretending to support it.
PLAYER_COUNT = 2


@dataclass(frozen=True, slots=True)
class GameState:
    """The complete state of a game in progress.

    Not hashable: ``players`` is a mapping. Every field is otherwise immutable,
    and every transition returns a new state, so a state can be stored, compared
    and replayed safely.

    The stack is absent until spell casting arrives in M4. An empty tuple now
    would be a field no event can change.
    """

    turn: int
    active_player: PlayerId
    step: Step
    players: Mapping[PlayerId, PlayerState]

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

    def cards(self) -> Iterator[CardInstance]:
        """Every card in the game, in every zone, for both players."""
        for player in self.players.values():
            yield from player.cards()


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
