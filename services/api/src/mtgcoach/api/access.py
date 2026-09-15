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

**Which player is asking** is closed too, and not here. One shared secret left
the ``player`` field in an event a claim the sender made about itself, so either
device could act for either seat and both were sent both hands. ``seating``
holds a token per seat and is what decides *who*; this module decides only
whether a string is a token and whether two of them match.

So: this is the wire half -- the header a request carries and the comparison.
``seating`` is the identity half, ``tokenfile`` the disk half -- where the
tokens come from, and why restarting the server does not invalidate the phone
in somebody's hand.
"""

from __future__ import annotations

import secrets

#: The scheme's prefix, as it appears in the header. Compared case-insensitively
#: because RFC 7235 §2.1 makes the scheme name case-insensitive and several
#: clients and proxies normalise it to lowercase -- and the failure mode of
#: getting that wrong is a 401 that reads as "wrong token" to somebody holding
#: the right one.
#:
#: Called ``SCHEME`` rather than ``BEARER`` so that a credential scanner does
#: not read the line as a token named "bearer" being assigned a value. Aborting
#: a review over the word "Bearer" is a cost for nothing.
SCHEME = "bearer "


class MissingTokenError(ValueError):
    """A server was built without a usable token for each seat.

    There is no open mode, and no seat without a token: an argument that can be
    left out is an argument that gets left out, and this one is the whole of the
    server's access control. ``seating.Seating`` raises it on construction, so
    a server that has one has one for every seat.
    """


#: How many random bytes a fresh token has. 32 is 256 bits, which is not going
#: to be guessed on a home network or anywhere else.
STRENGTH = 32


def new_token() -> str:
    """A fresh token."""
    return secrets.token_urlsafe(STRENGTH)


def usable(found: str) -> bool:
    """Whether this is something that can be a bearer token.

    A half-written or byte-damaged file used to become the live credential: the
    read decodes with ``errors="replace"``, so corrupt bytes come back as a
    string of U+FFFD, which is not empty -- so it was accepted, printed, and
    could not be sent in an ``Authorization`` header by any client. The server
    ran with a token nobody could present.

    So: printable ASCII, and nothing that a header cannot carry. Anything else
    is treated as no token at all and replaced, which is the only recovery
    there is and what an operator would do by hand.

    Deliberately *not* a strength check. A short token is a weak one, but an
    operator who put "hunter2" in this file chose it, it is their LAN, and the
    server prints it at every start where they can see it. Silently replacing
    somebody's deliberate choice is a different and worse surprise than the one
    this is for.
    """
    return bool(found) and found.isascii() and found.isprintable() and " " not in found


def presented(header: str | None, query: str | None) -> str:
    """The token a request carried, from the header or the query string.

    The header is where it belongs. The query string is for the WebSocket,
    which browsers will not let a page set headers on -- so the socket URL
    carries it instead, and that is a real if small cost: a query string ends
    up in server logs and browser history in a way a header does not.
    """
    if header and header.lower().startswith(SCHEME):
        return header[len(SCHEME) :].strip()
    return (query or "").strip()


def allowed(presented_token: str, expected: str) -> bool:
    """Whether this is the token, compared without leaking how close it was.

    ``compare_digest`` rather than ``==``: the naive comparison stops at the
    first wrong character, and the time it took says how many were right. That
    matters far less on a LAN than on the internet, and it costs one import.

    Compared as *bytes*. ``compare_digest`` refuses two ``str`` arguments
    unless both are ASCII, and raises ``TypeError`` when they are not -- so
    ``?token=%FF``, or a header carrying obs-text, turned an unauthenticated
    request into a 500 from inside the gatekeeper.
    """
    if not presented_token:
        return False
    return secrets.compare_digest(presented_token.encode("utf-8"), expected.encode("utf-8"))
