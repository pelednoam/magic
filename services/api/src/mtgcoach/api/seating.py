"""One token per seat: which player a request is allowed to speak for.

``access`` closed the door on anything that cannot present a token. Its own
docstring then said what that left open, and this module is that sentence being
acted on -- so the paragraph is quoted here rather than there, where it is no
longer true:

    **What it does not close.** Which *player* is asking. [...] §3's "you
    cannot see your opponent's hand" is enforced by the room, not by the
    code, and one shared secret does not change that -- a token per seat
    would, and is the obvious next step from here.

With one secret, the ``player`` field in an event was a claim the sender made
about itself and nothing checked it: either device could draw the other
player's card, change their life total, or pass priority for them, and both
devices were sent both hands. ``docs/DECISIONS.md`` items 4 and 9 record that
as one hole with one fix, and this is the half of the fix that decides *who*.

The seats are the two the game is dealt to, and a token names exactly one of
them. What follows from that is in ``gatekeeper`` (a connection is stamped with
the seat it authenticated as), ``acting`` (an event may only name that seat) and
``boardview`` (the other player's hand is not sent).

**Both tokens are equally powerful over the game they name.** This is not a
privilege system: the seat is an identity, not a rank. A device holding the
other seat's token is that player as far as this server is concerned, which is
exactly what a token in somebody's hand means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mtgcoach.api.access import MissingTokenError, allowed, new_token, usable

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The two seats a game is dealt to, in the order a person reads them. The
#: names are the ``PlayerId``s ``app.new_game`` creates, and they are here so
#: that the seats the *tokens* cover and the seats the *game* has cannot drift
#: apart -- which would issue a credential for a seat nobody sits in.
SEATS: Final[tuple[str, str]] = ("you", "them")

#: What separates a seat from its token on disk. A space, so a line is
#: ``you <token>`` and can be read out loud across a kitchen table.
SEPARATOR: Final = " "

#: How many fields a line of the file has.
FIELDS: Final = 2


@dataclass(frozen=True, slots=True)
class Seating:
    """Who may speak for each seat.

    Validated on construction rather than where it is used, because every use
    is a security decision and none of them should have to check first.

    Raises:
        MissingTokenError: If this is not one usable, distinct token for each
            seat. There is no open mode, no seat without a token, and no seat
            sharing one -- two seats holding the same token is one token, which
            is the arrangement this class exists to replace.
    """

    tokens: Mapping[str, str]

    def __post_init__(self) -> None:
        """Refuse anything that is not a token per seat."""
        if set(self.tokens) != set(SEATS):
            seated = ", ".join(sorted(self.tokens)) or "nobody"
            msg = f"a seating needs a token for each of {SEATS}; this has {seated}"
            raise MissingTokenError(msg)
        for seat, token in self.tokens.items():
            if not usable(token):
                msg = f"the token for {seat!r} is not something an Authorization header can carry"
                raise MissingTokenError(msg)
        if len({*self.tokens.values()}) != len(SEATS):
            msg = "two seats share a token, which is one token; give each seat its own"
            raise MissingTokenError(msg)

    def seat(self, presented: str) -> str | None:
        """Which seat this token names, or None when it names none.

        Every seat is compared, always, and the first match does not stop the
        loop. There are two of them, so the cost is one extra ``compare_digest``
        and what it buys is that the *time* this takes says nothing -- not
        which seat was hit, and not that any was.
        """
        found: str | None = None
        for name in SEATS:
            if allowed(presented, self.tokens[name]):
                found = name
        return found

    def token(self, seat: str) -> str:
        """The token for one seat, for printing it where its holder can see it.

        Raises:
            KeyError: If there is no such seat. Every seat in ``SEATS`` has
                one; anything else is a caller with a typo.
        """
        return self.tokens[seat]


def fresh() -> Seating:
    """A new token for each seat.

    Separate tokens, generated separately. Deriving the second from the first
    -- a suffix, a counter, a hash -- would mean that holding one seat's token
    is holding the other's, and the whole of this module is that not being so.
    """
    return Seating({seat: new_token() for seat in SEATS})


def written(seating: Seating) -> str:
    """The seating as the file holds it: one ``seat token`` line per seat.

    In ``SEATS`` order rather than sorted, so the file reads in the order the
    server prints it and an operator comparing the two is comparing two things
    in the same order.
    """
    lines = [f"{seat}{SEPARATOR}{seating.token(seat)}" for seat in SEATS]
    return "\n".join(lines) + "\n"


def parsed(text: str) -> Seating | None:
    """The seating in this text, or None when it is not one.

    None rather than a raise, and strictly: the caller's answer to "this is not
    a seating" is to make a fresh one, and that is the right answer to every
    way it can fail to be one -- an empty file, a half-written line, a damaged
    byte, or the *single* token this file used to hold before seats existed.

    That last one is the reason this is strict rather than forgiving. One token
    in this file was a credential for both seats, so reading it as either seat's
    token would keep exactly the hole the seating closes. It is replaced, both
    devices are told the new tokens, and the old one stops working -- which is
    what rotating a credential looks like from the inside.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split(SEPARATOR)
        if len(parts) != FIELDS:
            return None
        seat, token = parts
        if seat in found:
            return None
        found[seat] = token
    try:
        return Seating(found)
    except MissingTokenError:
        return None
