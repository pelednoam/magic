"""Killing the command's group, and never our own.

The whole module is one function with one job and one way to be catastrophic:
signal the wrong group and the server kills itself on an ordinary request. So
the tests are mostly about what it refuses to do.
"""

from __future__ import annotations

import os
import signal
from typing import TYPE_CHECKING, cast

import pytest

from fakeprocess import Fake
from mtgcoach.api.processes import close, group_of, kill_group

if TYPE_CHECKING:
    import subprocess


def _a_process(*, running: bool = True) -> subprocess.Popen[str]:
    """A stand-in process with a known pid, running unless said otherwise.

    Cast because the stand-in is what this module actually needs -- a ``pid``,
    a ``poll`` and a ``wait`` -- rather than the whole of ``Popen``, which
    cannot be built without starting something.
    """
    process = Fake().process
    if running:
        process.hang()
    return cast("subprocess.Popen[str]", process)


def test_the_group_is_the_pid() -> None:
    """By definition, for a child that called `setsid`."""
    assert group_of(_a_process()) == 4242


def test_a_reaped_process_group_is_never_signalled() -> None:
    """Its pid is free to be handed to something else by then.

    The group id *is* that pid, so signalling it afterwards is a chance to
    SIGKILL a stranger's process tree -- a worse bug than the orphans it would
    have cleaned up, and indistinguishable after the fact.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "killpg", _never)
        kill_group(4242, _a_process(running=False))


def test_the_group_is_signalled() -> None:
    killed: list[tuple[int, int]] = []

    def remember(group: int, signal_number: int) -> None:
        killed.append((group, signal_number))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "killpg", remember)
        kill_group(4242, _a_process())
    assert killed == [(4242, signal.SIGKILL)]


@pytest.mark.parametrize("group", [0, -1, -4242])
def test_a_group_that_means_us_is_never_signalled(group: int) -> None:
    """`killpg(0, ...)` means "my group"; a negative id is not a group."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "killpg", _never)
        kill_group(group, _a_process())


def test_our_own_group_is_never_signalled() -> None:
    """The failure mode this exists to prevent: the server killing itself."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "killpg", _never)
        kill_group(os.getpgrp(), _a_process())


def test_a_group_that_has_already_gone_is_not_an_error() -> None:
    """The ordinary case: the command finished and was reaped."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "killpg", _gone)
        kill_group(4242, _a_process())


def _never(group: int, _signal: int) -> None:
    """A `killpg` that must not be called."""
    msg = f"signalled group {group}, which is this process's own"
    raise AssertionError(msg)


def _gone(_group: int, _signal: int) -> None:
    """A `killpg` for a group that has already exited.

    Raises:
        ProcessLookupError: Always, as the real one would.
    """
    raise ProcessLookupError


def test_a_pipe_that_is_already_gone_is_skipped() -> None:
    """`Popen` leaves a pipe as None when it was not asked for one.

    It never is here, but `close` runs in a `finally` on every path and must
    not be the thing that raises on the way out of a failure.
    """
    process = Fake().process
    process.stdout = None  # type: ignore[assignment]
    close(cast("subprocess.Popen[str]", process))
    assert process.stdin.closed
    assert process.stderr.closed


def test_a_pipe_that_refuses_to_close_is_not_an_error() -> None:
    """Same reason: this is cleanup, not the request."""
    process = Fake().process
    process.stdin = _Stubborn()  # type: ignore[assignment]
    close(cast("subprocess.Popen[str]", process))
    assert process.stdout.closed


class _Stubborn:
    """A pipe whose `close` fails, as a closed file descriptor's would."""

    closed = False

    def close(self) -> None:
        """Refuse.

        Raises:
            OSError: Always.
        """
        raise OSError
