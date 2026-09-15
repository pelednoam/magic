"""The board, as much of it as a client may see.

Split from ``views`` at the line limit, and the seam is a real one: that module
turns the *coach's* answers into JSON, this one turns the *game* into JSON. A
client reads both in one payload and they are written by different halves of
the project.

It takes the whole card lookup rather than a naming function, which it used to.
The stack now says where its top spell resolves to, and that is a type line --
so this module needs the card data, not just the words printed on the card. It
is the right trade: the client used to remember ``is_permanent`` from the hand
advice and send it back in ``resolve_spell``, which meant the app held a fact
about a card after the card had left the zone it read it from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mtgcoach.core import priority
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.api.views import Json
    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.player import PlayerState
    from mtgcoach.core.stack import StackObject
    from mtgcoach.core.state import GameState


#: What to pass as ``seat`` for a game nobody is playing: a recording being
#: stepped through, where every hand is shown.
#:
#: A named constant rather than a default, so that every call site says which
#: it is. A default of "hide nothing" is the one that leaks when somebody adds
#: a route and forgets, and it is not the kind of mistake this project gets to
#: make once.
RECORDED: Final = None


def state(game: GameState, cards: CardLookup, seat: str | None) -> dict[str, Json]:
    """The board, as much of it as this seat may see.

    ``seat`` is the player this payload is *for*, taken from the token the
    request carried and never from its body -- see ``gatekeeper.seat_of``. The
    other player's hand is withheld (CR 400.2: a hand is a hidden zone), which
    used to be true of the room and not of the server: both hands went to both
    devices and "you cannot see your opponent's hand" held because nobody
    looked. Pass ``RECORDED`` for a finished game being walked through, where
    there is no hidden information left to protect and showing both hands is
    the whole point.

    Every player's *library* is a count, never a list. A tracker that shows you
    the top of your own deck is a cheating tool, and one that shows your
    opponent's is a worse one -- §3's non-goals put both out of scope.

    ``cards`` is passed in because the state does not know any of it: ``core``
    holds no card data, and a client should not have to ask twice for the word
    printed on the card in front of it.
    """
    return {
        "turn": game.turn,
        "step": game.step.value,
        "active_player": str(game.active_player),
        "players": {
            str(pid): _player(player, cards, hidden=seat is not None and str(pid) != seat)
            for pid, player in game.players.items()
        },
        # One ordered stack for both seats, bottom first (CR 405.2). It was a
        # tuple inside each player instead, which gave two devices two orders
        # and no way to agree which spell resolves first.
        "stack": [_waiting(one, cards) for one in game.stack],
        # Who may act (CR 117.1), null when nobody may. The app had no way to
        # ask, so it cast and resolved in one gesture and the other player's
        # chance to answer never existed.
        "priority": _named(game.priority),
        # Who has passed since the last action (CR 117.4). Both devices need
        # it: one to know it is waiting, the other to know it is being waited
        # for.
        "passed": [str(player) for player in game.passed],
        # Who still has to pass before anything happens, in the order they act.
        # Derived, and sent anyway -- it is the sentence the screen shows, and
        # working it out on the client would be the client deciding a rule.
        "yet_to_pass": [str(player) for player in priority.yet_to_pass(game)],
        # Null while the game is going. The tracker used to have no way to know
        # a game had ended, so it carried on offering plays to a player who had
        # already lost.
        "over": _over(game) if game.over is not None else None,
    }


def _waiting(one: StackObject, cards: CardLookup) -> dict[str, Json]:
    """One spell on the stack, and the two things a client needs about it.

    Its controller, because a shared zone has to say whose each object is
    (CR 405.4) and a tracker that showed an unattributed spell would be showing
    a board nobody could read.

    And where it resolves to, which only this side knows: ``core`` cannot read
    a type line, ``ResolveSpell`` has to be told, and the client must not
    guess. Null for a card the coach cannot identify -- the same answer
    ``guard`` gives, which refuses the resolution rather than picking a zone.
    """
    facts = cards.facts(one.card.oracle_id)
    resolves_to = None
    if facts is not None:
        resolves_to = (ZoneName.BATTLEFIELD if facts.is_permanent else ZoneName.GRAVEYARD).value
    return {
        **_card(one.card, cards),
        "controller": str(one.controller),
        "resolves_to": resolves_to,
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


def _player(player: PlayerState, cards: CardLookup, *, hidden: bool) -> dict[str, Json]:
    """One player's half of the board.

    ``hidden`` is whether this is somebody else's half, in which case the hand
    is a count and not a list. Null rather than an empty list, because an empty
    list says "this player is holding nothing" and that is a different fact
    about the game -- one a player would act on.

    ``hand_size`` either way. How many cards an opponent is holding is public
    (CR 400.2 makes the *contents* hidden, not the number), it is the thing a
    player at a table actually counts, and sending it alongside means hiding
    the list costs the tracker nothing it should have had.

    No stack here any more. It was a field on each player -- see
    ``core.stack`` for why two of them could not answer which spell resolves
    first -- and it is one ordered list beside them now, which is where the
    rules have always had it (CR 405.1).
    """
    return {
        "life": player.life,
        "library": len(player.library),
        "lands_played_this_turn": player.lands_played_this_turn,
        "hand_size": len(player.hand),
        "hand": None if hidden else [_card(card, cards) for card in player.hand],
        "battlefield": [_permanent(p, cards) for p in player.battlefield],
        "graveyard": [_card(card, cards) for card in player.graveyard],
        "exile": [_card(card, cards) for card in player.exile],
    }


def _card(card: CardInstance, cards: CardLookup) -> dict[str, Json]:
    """One card, by all three of the things a client needs to call it."""
    return {
        "instance_id": str(card.instance_id),
        "oracle_id": str(card.oracle_id),
        "name": cards.name(card.oracle_id),
    }


def _permanent(permanent: Permanent, cards: CardLookup) -> dict[str, Json]:
    """One permanent, with the two states a tracker has to show."""
    return {
        **_card(permanent.card, cards),
        "tapped": permanent.tapped,
        "summoning_sick": permanent.summoning_sick,
    }
