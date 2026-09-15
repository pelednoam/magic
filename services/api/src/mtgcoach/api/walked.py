"""A recorded game, as JSON a screen can page through.

Split from ``walking`` at the line limit, and the seam is a real one: that
module is four routes and their refusals, this is the shape they answer with.

Two things here are decisions rather than translation, and both are written
down where they are made: a game says which revisions it was played under and
which of those have moved (``listed``), and a moment shows **both** hands
(``moment``), which a live board never does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api import boardview, views

if TYPE_CHECKING:
    from mtgcoach.api.context import Server
    from mtgcoach.api.decisions import Moment
    from mtgcoach.api.replays import Replay
    from mtgcoach.api.views import Json


def listed(server: Server, game: Replay) -> dict[str, Json]:
    """One game, as a line to choose from -- and what it was played under.

    ``differs`` is the whole point of recording the revisions: it names which
    of the three have moved since, so "this journal will not open" becomes
    "this journal was made by a different engine". A revision the journal never
    recorded is not a difference -- see ``Sources.differs_from`` -- so an old
    journal reads as old rather than as three things having changed.
    """
    return {
        "index": game.index,
        "seed": game.seed,
        "decks": list(game.decks),
        "decisions": len(game.moments),
        "sources": game.sources.as_json(),
        "differs": list(game.sources.differs_from(server.sources)),
        # Why it cannot be shown, when it cannot. Empty for a game that
        # rebuilt. Beside `differs` because the two are read together: what
        # went wrong, and which version moved under it.
        "problem": game.problem,
    }


def walked(server: Server, game: Replay) -> dict[str, Json]:
    """One game, as something a screen can page through."""
    return {**listed(server, game), "moments": [moment(server, one) for one in game.moments]}


def moment(server: Server, one: Moment) -> dict[str, Json]:
    """One moment: where in the game, the board, and what was said about it.

    The board goes out as ``boardview.state`` -- the same shape a live game sends
    -- so the app renders a replayed position with the components it already
    has, and a position looks the same whether it is happening now or happened
    last night.

    With ``RECORDED`` for the seat, which is the one way it differs from a live
    board: **both hands are shown**, and the walk screen prints them under each
    battlefield. A recording is not a game in progress, nobody can act on what
    it shows, and knowing what each side held is most of why a decision it made
    makes sense -- "why didn't they block?" is the question this screen exists
    for. A live board withholds the other hand (CR 400.2); there is no player
    here to withhold it from.

    Named from the server's catalogue, for the same reason. A journal holds
    oracle ids, which are Scryfall's UUIDs; without the catalogue every card on
    the walk screen reads ``b2c6aa39-...`` while the *same* position one tap
    later, under "ask about this", reads "Forest". ``Catalogue.name`` falls
    back to the id for a card this server never imported -- which a replay of
    another set really can contain -- and that is the honest answer: this is a
    card the server cannot name.
    """
    return {
        "turn": one.turn,
        "step": str(one.step),
        "player": one.player,
        "state": boardview.state(one.state, server.catalogue, boardview.RECORDED),
        "said": views.explanation(one.said) if one.said is not None else None,
        "trusted": one.trusted,
        "problems": list(one.problems),
        "error": one.error,
    }
