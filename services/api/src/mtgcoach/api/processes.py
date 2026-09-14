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
from contextlib import suppress

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
    """End the command and everything it started.

    Signalled whether or not the direct process is still running: ``claude``
    spawns more, and a parent that has returned says nothing about its
    children.

    Never the server's own group, and never group 0, which means "mine" to
    ``killpg``. Either would be this function killing the process that called
    it. Best effort otherwise -- an ``ESRCH`` means the group is already gone,
    which is the ordinary case.
    """
    if _is_ours(group):
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
