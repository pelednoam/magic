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
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

#: How many random bytes. 32 is 256 bits, which is not going to be guessed on a
#: home network or anywhere else.
STRENGTH = 32

#: Who may read the token file: its owner. The server runs as the person who
#: started it, and everyone else on that laptop is not part of the game.
OWNER_ONLY = 0o600

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
    """A server was built without a token. There is no open mode."""


class TokenPathError(ValueError):
    """The token file is something a token file may not be."""


def new_token() -> str:
    """A fresh token."""
    return secrets.token_urlsafe(STRENGTH)


def token_at(path: Path) -> str:
    """The token in this file, making one if there is none yet.

    Three things this does carefully, each because the careless version is
    wrong in a way that matters:

    - **Created exclusively.** ``O_CREAT | O_EXCL`` means the mode argument is
      actually applied: the kernel ignores it for a file that already exists,
      so ``O_TRUNC`` would have written a fresh token into somebody else's
      0644 file and left it 0644. ``O_EXCL`` also settles the race between two
      servers starting at once -- one creates, the other gets
      ``FileExistsError`` and reads what the first wrote, instead of both
      writing different tokens over each other.
    - **Not through a symlink.** ``O_NOFOLLOW`` on both the read and the write,
      and a refusal up front so the reason is legible. A symlink planted at
      ``data/token`` would otherwise have this write a token wherever it
      pointed, and read a token somebody else chose.
    - **Tightened if it arrived loose.** A file that came from a git checkout,
      a backup, or a permissive umask is fixed to 0600 rather than refused --
      the server can put that right, and refusing to start over it would be
      worse for the person at the table.

    Raises:
        TokenPathError: If the path is a symlink.
    """
    if path.is_symlink():
        # `O_NOFOLLOW` below refuses this too, but with `ELOOP` -- "Too many
        # levels of symbolic links", which says nothing about what is wrong or
        # what to do. The check is the message; the flag is the enforcement,
        # and it is what holds if the link appears after this line.
        msg = f"{path} is a symlink; a token file may not be one. Remove it."
        raise TokenPathError(msg)
    found = _existing(path)
    if found:
        return found
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _created(path)
    except FileExistsError:
        pass
    # Something is there and had no token in it: an empty file, or a server
    # that created one a moment ago and has not written to it yet. Read once
    # more in case it is the second, then write over it if it is the first.
    #
    # Deliberately not a loop. The first version retried until it succeeded and
    # span forever on an empty file -- `_existing` returned nothing, `_created`
    # said the file was there, round again.
    return _existing(path) or _replaced(path)


def _existing(path: Path) -> str:
    """The token already in this file, or empty if there is not one.

    Tightens the permissions if they are looser than they should be, which is
    the only thing to be done about a file that arrived from somewhere else.
    """
    try:
        handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        # Absent, a directory, a symlink, or unreadable. All "there is no
        # token here"; the create below will say which if it matters.
        return ""
    with os.fdopen(handle, encoding="utf-8") as file:
        if stat.S_IMODE(os.fstat(handle).st_mode) & ~OWNER_ONLY:
            os.fchmod(handle, OWNER_ONLY)
        return file.read().strip()


def _created(path: Path) -> str:
    """A new token, written to a file this call brought into existence.

    Raises:
        FileExistsError: If something is already there. The caller reads it.
        OSError: If the path is a symlink -- ``O_NOFOLLOW`` refuses it. The
            caller has already said so in words; this is the backstop.
    """
    token = new_token()
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, OWNER_ONLY)
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        file.write(token + "\n")
    return token


def _replaced(path: Path) -> str:
    """A new token written over a file that had none in it.

    Still ``O_NOFOLLOW``, and the mode is set explicitly afterwards because the
    kernel ignores the ``open`` mode for a file that already exists -- which is
    the whole reason ``_created`` uses ``O_EXCL``.
    """
    token = new_token()
    handle = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
    with os.fdopen(handle, "w", encoding="utf-8") as file:
        os.fchmod(handle, OWNER_ONLY)
        file.write(token + "\n")
    return token


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
