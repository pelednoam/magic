"""The token file: making one, reading it back, keeping it to its owner.

Split from ``access`` because the two halves have nothing in common. That
module is about a string in an HTTP header. This one is about a file on disk,
which is where all the care is: a lock held across read-decide-write, a mode
that has to be right, a symlink that must not be followed, a write that has to
be complete, and content that has to be checked before it becomes the thing the
server trusts.
"""

from __future__ import annotations

import fcntl
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

#: How much to read at a time. A token is 43 characters, so this is the whole
#: file in one call; the loop is there because `os.read` may return less.
READ_CHUNK = 4096


class TokenPathError(ValueError):
    """The token file is something a token file may not be."""


def new_token() -> str:
    """A fresh token."""
    return secrets.token_urlsafe(STRENGTH)


def token_at(path: Path) -> str:
    """The token in this file, making one if there is none yet.

    Everything happens under an exclusive ``flock`` on the file itself, which
    is what makes two servers starting at the same instant agree. The version
    before this one created exclusively and read on ``FileExistsError``, which
    looked like it settled the race and did not: between one process creating
    the file and writing to it, the other read it, found it empty, and wrote a
    *different* token over the top. Both then answered requests with the token
    they had in hand, one of which was no longer the one in the file. A lock
    held across read-decide-write is the only shape without that window.

    Two other things it does carefully:

    - **Not through a symlink.** ``O_NOFOLLOW``, and a refusal up front so the
      reason is legible. A symlink planted at ``data/token`` would otherwise
      have this write a token wherever it pointed, and read one somebody else
      chose.
    - **Tightened if it arrived loose.** The mode argument to ``open`` applies
      only when the call creates the file, so a 0644 file from a checkout, a
      backup or a permissive umask stays 0644 unless something says otherwise.
      Fixed rather than refused: the server can put it right, and refusing to
      start would be worse for the person at the table.

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
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = _opened(path)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        return _settled(handle)
    finally:
        # Closing releases the lock. Explicit rather than `os.fdopen`, because
        # a file object would close the descriptor on garbage collection at
        # some later moment, and the lock has to be gone before this returns.
        os.close(handle)


def _opened(path: Path) -> int:
    """The token file, open for reading and writing, tightened if it has to be.

    ``O_RDWR`` is what the lock needs, and it is refused outright on a file
    whose mode has no write bit -- a 0400 token from a restrictive umask or a
    careful backup. Refusing to start over that would contradict the promise
    above and strand the person at the table, so this puts the mode right and
    tries once more.

    Raises:
        TokenPathError: If it still cannot be opened. The path is wrong, or it
            belongs to somebody else, and neither is something to guess at.
    """
    try:
        return os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, OWNER_ONLY)
    except PermissionError:
        pass
    try:
        os.chmod(path, OWNER_ONLY, follow_symlinks=False)  # noqa: PTH101 - fd-less by design
        return os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    except OSError as exc:
        msg = f"{path} cannot be opened for writing ({type(exc).__name__}). Check who owns it."
        raise TokenPathError(msg) from exc


def _settled(handle: int) -> str:
    """The token, read or written, on a descriptor already locked.

    Split out because the lock is the interesting part of ``token_at`` and this
    is the boring part, and because a function that must only ever be called
    under a lock is easier to see when it is one function.
    """
    if stat.S_IMODE(os.fstat(handle).st_mode) & ~OWNER_ONLY:
        os.fchmod(handle, OWNER_ONLY)
    found = _read(handle).strip()
    if usable(found):
        return found
    # Empty, or not a token: this call created the file, or something else did
    # and left it that way, or what is in it is damaged. Under the lock there
    # is no fourth possibility and no need to look again.
    token = new_token()
    os.lseek(handle, 0, os.SEEK_SET)
    os.truncate(handle, 0)
    _write(handle, (token + "\n").encode("utf-8"))
    return token


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


def _write(handle: int, payload: bytes) -> None:
    """Every byte of it.

    ``os.write`` is allowed to write fewer bytes than it was given. A short
    write here would hand the running server the whole token and leave a prefix
    on disk, so the next start -- and any other process -- would disagree with
    it about what the credential is.
    """
    written = 0
    while written < len(payload):
        written += os.write(handle, payload[written:])


def _read(handle: int) -> str:
    """Everything on this descriptor, from the start.

    A token is 43 characters, so one read is the whole file -- but `os.read`
    is allowed to return less than asked for, and a short read that silently
    became "no token here" would write over a perfectly good one.
    """
    os.lseek(handle, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while chunk := os.read(handle, READ_CHUNK):
        chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")
