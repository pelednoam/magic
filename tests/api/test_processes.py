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
from mtgcoach.api.processes import group_of, kill_group

if TYPE_CHECKING:
    import subprocess


def _a_process() -> subprocess.Popen[str]:
    """A stand-in process with a known pid.

    Cast because the stand-in is what this module actually needs -- a ``pid``
    and a ``wait`` -- rather than the whole of ``Popen``, which cannot be built
    without starting something.
    """
    return cast("subprocess.Popen[str]", Fake().process)


def test_the_group_is_the_pid() -> None:
    """By definition, for a child that called `setsid`."""
    assert group_of(_a_process()) == 4242


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
