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

from mtgcoach.api.access import usable

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
    is what makes two servers starting at the same instant agree. Creating
    exclusively and reading on ``FileExistsError`` looked like it settled the
    race and did not: between one process creating the file and writing to it,
    the other read it empty and wrote a *different* token over the top, and
    both then answered with a token that was not the one on disk. A lock held
    across read-decide-write is the only shape without that window.

    Two other things it does carefully:

    - **Not through a symlink.** ``O_NOFOLLOW``, and a refusal up front so the
      reason is legible. One planted at ``data/token`` would otherwise have
      this write a token wherever it pointed, and read one somebody else chose.
    - **Tightened if it arrived wrong.** The mode argument to ``open`` applies
      only when the call creates the file, so a 0644 file from a checkout or a
      loose umask stays 0644 unless something says otherwise. Fixed rather than
      refused: the server can put it right, and refusing to start would be
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

    ``O_RDWR`` is what the lock needs, and a file with no write bit -- a 0400
    token from a careful backup -- refuses it outright. Refusing to start over
    that would contradict the promise above, so this puts the mode right and
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
        # Plain, without `follow_symlinks=False`: `chmod` is not in
        # `os.supports_follow_symlinks` on Linux, where passing it can raise
        # `NotImplementedError` -- which this `except OSError` would not catch,
        # so the recovery would crash instead of recovering. The symlink is
        # already refused at the top of `token_at`, and `O_NOFOLLOW` on the
        # line below refuses one that appeared since: if that happens, the
        # chmod touched somebody else's mode but no token is read or written.
        os.chmod(path, OWNER_ONLY)  # noqa: PTH101 - no descriptor to use yet
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
    # Not `& ~OWNER_ONLY`: that is false for 0400 and 0000, so a file missing
    # its *owner* bits was never put right -- and the only thing covering that
    # was `_opened`'s recovery, which is a worse place for it and was itself
    # broken. Any mode that is not exactly 0600 is made 0600.
    if stat.S_IMODE(os.fstat(handle).st_mode) != OWNER_ONLY:
        os.fchmod(handle, OWNER_ONLY)
    found = _read(handle).strip()
    if usable(found):
        return found
    # Empty, or not a token: this call created the file, or something else did
    # and left it that way, or what is in it is damaged. Under the lock there
    # is no fourth possibility and no need to look again.
    token = new_token()
    _replace(handle, (token + "\n").encode("utf-8"))
    return token


def _replace(handle: int, payload: bytes) -> None:
    """Put exactly these bytes in the file, or say that it could not be done.

    Three things, each for a way the naive version goes wrong. **Every byte**:
    ``os.write`` may write fewer than it was given, which would leave a prefix
    on disk and the whole token in memory. **Flushed**: without ``fsync`` the
    file can be empty after a power cut while the server answers happily.
    **Read back**: truncate-then-write is not atomic, and a prefix of a token
    is printable ASCII with no spaces -- exactly what ``usable`` accepts -- so
    a crash part-way would leave a short, guessable credential to be trusted at
    the next start. Reading it back makes that a refusal now, while somebody is
    watching.

    Raises:
        TokenPathError: If what is on disk afterwards is not what was written.
    """
    os.lseek(handle, 0, os.SEEK_SET)
    os.truncate(handle, 0)
    written = 0
    while written < len(payload):
        written += os.write(handle, payload[written:])
    os.fsync(handle)
    if _read(handle).encode("utf-8") != payload:
        msg = "the token file did not keep what was written to it; check the disk"
        raise TokenPathError(msg)


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
