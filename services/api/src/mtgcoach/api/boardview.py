"""The board, as much of it as a client may see.

Split from ``views`` at the line limit, and the seam is a real one: that module
turns the *coach's* answers into JSON, this one turns the *game* into JSON. A
client reads both in one payload and they are written by different halves of
the project.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from mtgcoach.api.views import Json
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import OracleId, PlayerId
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.player import PlayerState
    from mtgcoach.core.state import GameState

    #: How a client is told what a card is called; see ``views.Naming``.
    Naming = Callable[[OracleId], str]


def state(game: GameState, names: Naming) -> dict[str, Json]:
    """The board, as much of it as a client may see.

    Every player's *library* is a count, never a list. A tracker that shows you
    the top of your own deck is a cheating tool, and one that shows your
    opponent's is a worse one -- §3's non-goals put both out of scope.

    ``names`` is passed in because the state does not know them: ``core`` holds
    no card data, and a client should not have to ask twice for the word printed
    on the card in front of it.
    """
    return {
        "turn": game.turn,
        "step": game.step.value,
        "active_player": str(game.active_player),
        "players": {str(pid): _player(player, names) for pid, player in game.players.items()},
        # Null while the game is going. The tracker used to have no way to know
        # a game had ended, so it carried on offering plays to a player who had
        # already lost.
        "over": _over(game) if game.over is not None else None,
    }


def _over(game: GameState) -> dict[str, Json]:
    """How the game ended, in the words a player needs.

    ``winner`` is null on a draw (CR 104.4b), which is a real outcome and not
    a missing answer -- so the client is told `drawn` separately rather than
    left to read a null as "we do not know".
    """
    assert game.over is not None  # noqa: S101 - narrowed by the caller
    return {
        "lost": [{"player": str(one.player), "why": one.why.value} for one in game.over.lost],
        "winner": _named(game.over.winner(game.players)),
        "drawn": game.over.drawn,
    }


def _named(player: PlayerId | None) -> Json:
    """A seat, or null."""
    return str(player) if player is not None else None


def _player(player: PlayerState, names: Naming) -> dict[str, Json]:
    """One player's half of the board."""
    return {
        "life": player.life,
        "library": len(player.library),
        "lands_played_this_turn": player.lands_played_this_turn,
        "hand": [_card(card, names) for card in player.hand],
        # The stack is a public zone (CR 400.2): both players can see what is
        # waiting to resolve, and a tracker that hid it would be hiding the one
        # thing a player needs in order to decide whether to answer it.
        "stack": [_card(card, names) for card in player.stack],
        "battlefield": [_permanent(p, names) for p in player.battlefield],
        "graveyard": [_card(card, names) for card in player.graveyard],
        "exile": [_card(card, names) for card in player.exile],
    }


def _card(card: CardInstance, names: Naming) -> dict[str, Json]:
    """One card, by all three of the things a client needs to call it."""
    return {
        "instance_id": str(card.instance_id),
        "oracle_id": str(card.oracle_id),
        "name": names(card.oracle_id),
    }


def _permanent(permanent: Permanent, names: Naming) -> dict[str, Json]:
    """One permanent, with the two states a tracker has to show."""
    return {
        **_card(permanent.card, names),
        "tapped": permanent.tapped,
        "summoning_sick": permanent.summoning_sick,
    }
