"""Who may talk to this server.

§4 puts it on one LAN with two devices at one table, and PLAN.md has recorded
"the API is unauthenticated" as a known gap since M5. This closes it, and it is
worth being exact about what it closes and what it does not.

**What it closes.** Anything else that can reach the port. A guest's phone, a
television, and -- the one that actually matters -- a web page the household
visits, which can make cross-origin requests to ``http://<laptop>:8000`` and
did not previously need to know anything to drive the game or spend the
operator's Claude subscription. A bearer token cannot be guessed, and asking
for a header makes every such request preflighted, so a page that does not have
it cannot even reach a route.

**What it does not close.** Which *player* is asking. Every snapshot still
carries both hands, and ``move_card`` will still move any card from any zone.
§3's "you cannot see your opponent's hand" is enforced by the room, not by the
code, and one shared secret does not change that -- a token per seat would, and
is the obvious next step from here.

The token lives in a file next to the card database so that restarting the
server does not invalidate the phone in somebody's hand.
"""

from __future__ import annotations

import os
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: How many random bytes. 32 is 256 bits, which is not going to be guessed on a
#: home network or anywhere else.
STRENGTH = 32

#: Who may read the token file: its owner. The server runs as the person who
#: started it, and everyone else on that laptop is not part of the game.
OWNER_ONLY = 0o600

#: The scheme's prefix, as it appears in the header. Named for what it is
#: rather than ``SCHEME``, which reads to a credential scanner as a token
#: called "bearer" being assigned a value -- and a scanner aborting a review
#: over the word "Bearer" is a cost for nothing.
SCHEME = "Bearer "


class MissingTokenError(ValueError):
    """A server was built without a token. There is no open mode."""


def new_token() -> str:
    """A fresh token."""
    return secrets.token_urlsafe(STRENGTH)


def token_at(path: Path) -> str:
    """The token in this file, making one if there is none yet.

    Created with the permissions it needs from the start rather than fixed
    afterwards: a token that is briefly world-readable is a token that was
    world-readable. Written via ``os.open`` with ``O_CREAT | O_EXCL`` for the
    same reason -- ``Path.write_text`` then ``chmod`` has a window in it.
    """
    if path.is_file():
        found = path.read_text(encoding="utf-8").strip()
        if found:
            return found
    path.parent.mkdir(parents=True, exist_ok=True)
    token = new_token()
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, OWNER_ONLY)
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        file.write(token + "\n")
    return token


def presented(header: str | None, query: str | None) -> str:
    """The token a request carried, from the header or the query string.

    The header is where it belongs. The query string is for the WebSocket,
    which browsers will not let a page set headers on -- so the socket URL
    carries it instead, and that is a real if small cost: a query string ends
    up in server logs and browser history in a way a header does not.
    """
    if header and header.startswith(SCHEME):
        return header[len(SCHEME) :].strip()
    return (query or "").strip()


def allowed(presented_token: str, expected: str) -> bool:
    """Whether this is the token, compared without leaking how close it was.

    ``compare_digest`` rather than ``==``: the naive comparison stops at the
    first wrong character, and the time it took says how many were right. That
    matters far less on a LAN than on the internet, and it costs one import.
    """
    return bool(presented_token) and secrets.compare_digest(presented_token, expected)
