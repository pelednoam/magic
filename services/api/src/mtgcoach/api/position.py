"""The board a slow answer is about, and which revision of it that was.

Split from ``context`` at the line limit, and the seam is a real one: that
module is what every route shares, and this is what only the two *slow* routes
need -- the ones that spend a minute in a subprocess and come back to a game
that may have moved on in the meantime.

Which is the whole reason the revision travels beside the report. An answer
that takes a minute has to come back saying which board it was about, or the
client is left guessing whether it still applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.coach.report import advise
from mtgcoach.coach.table import table

if TYPE_CHECKING:
    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.coach.table import Table
    from mtgcoach.core.ids import PlayerId


@dataclass(frozen=True, slots=True)
class Position:
    """The board a slow answer is about, and which revision that was.

    Both slow routes need all of it and one of them needed six arguments to
    say so. Carrying the revision alongside the report is also the point of the
    thing: an answer that takes a minute has to come back saying which board it
    was about, or the client is left guessing.
    """

    report: TurnReport
    revision: int
    #: Only the rules route needs the battlefield; the turn coach's report
    #: already names every creature that matters.
    board: Table | None = None


def position(server: Server, game: Session, player: PlayerId, *, board: bool = False) -> Position:
    """Work out the board, once, for one of the slow routes."""
    return Position(
        report=advise(game.state, player, server.catalogue),
        revision=game.revision,
        board=table(game.state, player, server.catalogue) if board else None,
    )
