"""Ending a subprocess, and everything it started.

``claude`` is a Node process that spawns more, so killing the one we launched
is not the same as killing what we launched -- and the difference is a handful
of orphans per timeout, holding the quota with nobody waiting on them.

Two details cost three attempts to get right:

- ``subprocess.run``'s timeout calls ``process.kill()``, which signals the
  direct child and never the group. ``start_new_session=True`` puts the child
  in its own group but ``run`` never signals it, so the comment claiming the
  tree was killed was documenting a bug.
- ``os.getpgid`` has to be asked *before* the child is reaped. Afterwards it
  raises ``ESRCH``, which was suppressed -- so the group went unsignalled in
  exactly the case the kill exists for, a parent that exited leaving
  descendants behind. Reading a dead pid is also a reuse race.
"""

from __future__ import annotations

import os
import signal
import subprocess
from contextlib import suppress


def group_of(process: subprocess.Popen[str]) -> int | None:
    """This process's group, read while it is certainly still alive."""
    try:
        return os.getpgid(process.pid)
    except OSError:
        return None


def kill_group(group: int | None, process: subprocess.Popen[str]) -> None:
    """End the command and everything it started.

    The group is signalled whether or not the direct process is still running.
    ``claude`` is a Node process that spawns more, and a parent that has
    returned says nothing about its children -- which would otherwise sit there
    holding the quota with nobody waiting on them.

    Best effort: an ``ESRCH`` means the group is already gone, which is the
    ordinary case and not worth turning a finished answer into an error over.
    """
    if group is not None:
        with suppress(OSError):
            os.killpg(group, signal.SIGKILL)
    with suppress(OSError, ValueError, subprocess.TimeoutExpired):
        process.wait(timeout=5)
