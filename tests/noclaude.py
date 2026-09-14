"""Two things no test in this suite may do.

Start the real ``claude``, and signal a process group.

The second is the sharper of the two. The stand-in processes carry pid 4242,
which on this machine is very likely a real process belonging to somebody --
so a test that exercises the kill path without patching ``os.killpg`` would
``SIGKILL`` their process tree. Nothing has, but "nothing has" is not a
property, and the failure would be silent and unrelated.

Registered as a pytest plugin in ``pyproject.toml`` (``-p noclaude``) rather
than written as ``tests/conftest.py``, because ``tests/e2e`` already has a
conftest and mypy refuses two modules with the same name on its path.

``create_app`` defaults both models to the local CLI, which is right for the
one production caller and wrong for everything else. ``helpers_api.server``
passes stand-ins, so every test that goes through it is safe -- but that is a
property of a helper, and a test written next week that calls ``create_app``
directly would quietly shell out: slow, quota-spending, and passing or failing
for reasons nothing in this repository controls.

So the guard is here rather than there, and it sits at the process boundary
rather than at ``Cli.run``. A test that stubs out the subprocess -- which is
how the CLI is tested -- replaces the same attribute and is unaffected. A test
that reaches an actual ``claude`` fails, and fails saying what to pass instead.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from pathlib import PurePath
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

ADVICE = (
    "a test tried to run the real `claude` command. Pass an explainer and an "
    "asker to create_app -- helpers_api.server does this for you -- or stub "
    "the subprocess, as tests/api/test_explainer_cli.py does."
)


def _is_claude(argv: object) -> bool:
    """Whether this command line starts the real CLI.

    The basename, exactly. "Ends with claude" also caught the ``fake-claude``
    script that ``tests/carddata/test_claudecli.py`` writes and runs on purpose
    -- which is a better test than a stub, and not the thing being guarded
    against.
    """
    if isinstance(argv, (str, bytes)):
        return PurePath(str(argv)).name == "claude"
    if isinstance(argv, Sequence) and argv:
        return PurePath(str(cast("Sequence[object]", argv)[0])).name == "claude"
    return False


def guarding[**P, R](start: Callable[P, R]) -> Callable[P, R]:
    """``start``, unless its first argument would run the CLI."""

    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        """Start the process, or refuse.

        Raises:
            AssertionError: If it would be the real ``claude``.
        """
        # Positional or by keyword: `subprocess.run(args=[...])` is legal and
        # went straight past a check that only looked at `args[0]`.
        if _is_claude(args[0] if args else kwargs.get("args")):
            raise AssertionError(ADVICE)
        return start(*args, **kwargs)

    return guarded


def _no_signalling(group: int, signal_number: int) -> None:
    """Never signal a process group.

    Raises:
        AssertionError: Always. A test that wants to watch the kill happen
            patches ``os.killpg`` itself, which replaces this.
    """
    msg = (
        f"a test tried to send signal {signal_number} to process group {group}. "
        "That is a real group on this machine. Patch os.killpg in the test."
    )
    raise AssertionError(msg)


@pytest.fixture(autouse=True, scope="session")
def _no_real_claude() -> Iterator[None]:
    """Wrap the process boundary for the whole session."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", guarding(subprocess.run))
        patch.setattr(subprocess, "Popen", guarding(subprocess.Popen))
        patch.setattr(os, "killpg", _no_signalling)
        yield
