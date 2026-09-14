"""Ending a subprocess, and everything it started, without ending ourselves.

``claude`` is a Node process that spawns more, so killing the one we launched
is not the same as killing what we launched -- and the difference is a handful
of orphans per timeout, holding the quota with nobody waiting on them.

Three attempts, and the third one is about not shooting the server:

- ``subprocess.run``'s timeout calls ``process.kill()``, which signals the
  direct child and never the group. ``start_new_session=True`` puts the child
  in its own group but ``run`` never signals it, so the comment claiming the
  tree was killed was documenting a bug.
- ``os.getpgid`` has to be asked before the child is reaped; afterwards it
  raises ``ESRCH``, which was suppressed, so the group went unsignalled in
  exactly the case the kill exists for.
- **And asking at all is a race.** ``setsid`` runs in the child, after the fork
  the parent has already returned from -- so a ``getpgid`` that wins the race
  reads the group the child *inherited*, which is the server's own. Killing
  that takes down the API on an ordinary coach request. There is no need to
  ask: a process that calls ``setsid`` leads a group whose id is its own pid,
  so the pid is the answer, and it is the answer before the child has run.

The guard below is belt and braces on top of that. Nothing this module does may
signal the group the server is in, whatever went wrong upstream.
"""

from __future__ import annotations

import os
import signal
import subprocess
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

#: How long to wait for a killed process to be reaped. It has had SIGKILL; if
#: it is still there after this, something is wrong that waiting will not fix.
REAP_SECONDS = 5


def group_of(process: subprocess.Popen[str]) -> int:
    """The group this child leads.

    Its own pid, by definition: it was started with ``start_new_session=True``,
    so it called ``setsid`` and became the leader of a new group numbered after
    itself. Derived rather than asked because ``os.getpgid`` raced that
    ``setsid`` and could return the group the child inherited -- the server's.
    """
    return process.pid


def kill_group(group: int, process: subprocess.Popen[str]) -> None:
    """End the command and everything it started, while it is safe to.

    Only while the leader is still running. Once it has been reaped its pid is
    free to be handed to something else, and the group id *is* that pid -- so
    signalling it afterwards is a chance to ``SIGKILL`` a stranger's process
    tree. That is a worse bug than the one this fixes, and there is no way to
    tell the two apart after the fact.

    What that gives up is a parent that exited leaving descendants behind. It
    is the case worth wanting and it is not the case that matters: the reason
    this exists is the timeout, and on a timeout the leader is alive by
    definition -- that is what timed out.

    Never the server's own group either, and never group 0, which means "mine"
    to ``killpg``. Both would be this function killing its own caller. Best
    effort otherwise -- an ``ESRCH`` means the group is already gone, which is
    the ordinary case.
    """
    if _is_ours(group) or process.poll() is not None:
        return
    with suppress(OSError):
        os.killpg(group, signal.SIGKILL)
    with suppress(OSError, ValueError, subprocess.TimeoutExpired):
        process.wait(timeout=REAP_SECONDS)


def _is_ours(group: int) -> bool:
    """Whether signalling this group would signal this process.

    ``group <= 0`` counts: ``killpg(0, ...)`` means "my group", and a negative
    id is not a group at all. ``os.getpgrp`` takes no arguments and cannot
    fail, so there is nothing here to handle.
    """
    return group <= 0 or group == os.getpgrp()


@contextmanager
def started(argv: Sequence[str], directory: str) -> Generator[subprocess.Popen[str]]:
    """The command, running, cleaned up however the block ends.

    ``Popen`` rather than ``run`` because of the cleanup. ``run``'s timeout path
    calls ``process.kill()``, which signals the direct child and nothing else,
    and it does not close the pipes either -- so a timed-out ``claude`` left
    its children alive and three file descriptors open, on the path that
    repeats.
    """
    process = subprocess.Popen(  # noqa: S603 - fixed argv, prompt via stdin, no shell
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        # Pinned, not inherited. `text=True` alone encodes stdin with the
        # ambient locale codec, so a card name or a question with a non-ASCII
        # character in it raised UnicodeEncodeError on a POSIX-locale server --
        # and Magic prints em-dashes.
        encoding="utf-8",
        errors="replace",
        cwd=directory,
        start_new_session=True,
    )
    group = group_of(process)
    try:
        yield process
    except BaseException:
        # Only on the way out badly. A clean exit means the command finished
        # and was reaped, and its pid can then be handed to something else --
        # so killing "its" group afterwards is a chance to SIGKILL a stranger.
        # The case the kill is for is the case that did not finish.
        kill_group(group, process)
        raise
    finally:
        close(process)


def close(process: subprocess.Popen[str]) -> None:
    """Shut the three pipes.

    ``communicate`` closes them when it returns; on the timeout path it does
    not, so every question that took too long leaked three file descriptors.
    """
    for pipe in (process.stdin, process.stdout, process.stderr):
        if pipe is not None:
            with suppress(OSError):
                pipe.close()
