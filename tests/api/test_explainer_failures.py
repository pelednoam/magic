"""Every way the command can fail, and what the player is told about it.

Two threads run through these. One is that the message reaches a client over a
policy that allows every origin, so it may carry an exit code and a duration
but not a path, a config location or an account. The other is that the process
has to be gone afterwards -- all of it, and only it.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from fakeprocess import Fake, Raises
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.coach.advice import ExplainerError
from test_explainer import REPORT
from test_explainer_cli import envelope_answer, explain, kills_nothing


def test_a_failing_command_is_an_error_without_its_stderr() -> None:
    """This message reaches a client, and the CORS policy is `*`.

    A CLI's stderr carries absolute paths, config locations and sometimes an
    account name. The exit code is the part a player can act on.
    """
    with pytest.raises(ExplainerError, match="exited 1") as refused:
        explain(Fake(code=1, stderr="/home/someone/.claude/config.json is bad"))
    assert "/home/someone" not in str(refused.value)


def test_a_missing_command_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="could not ask the coach"):
        explain(Raises(FileNotFoundError("/usr/local/bin/claude"), on_start=True))


def test_a_missing_command_does_not_leak_its_path() -> None:
    """Same reason as the exit code above: this message is sent to a client."""
    with pytest.raises(ExplainerError) as refused:
        explain(Raises(FileNotFoundError("/usr/local/bin/claude"), on_start=True))
    assert "/usr/local" not in str(refused.value)


def test_a_slow_command_says_how_long_it_waited() -> None:
    """A timeout is the one failure a player can do something about."""
    with pytest.raises(ExplainerError, match="longer than 90s"):
        explain(Raises(subprocess.TimeoutExpired("claude", 90)))


def test_a_slow_command_is_killed_as_a_group() -> None:
    """`run`'s timeout signals the direct child only, and `claude` is Node.

    Killing just the parent left its children alive, still holding the quota
    and still writing, after the request had already failed.
    """
    killed: list[int] = []

    def remember(group: int, _signal: int) -> None:
        killed.append(group)

    fake = Raises(subprocess.TimeoutExpired("claude", 90))
    explainer = ClaudeCliExplainer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "getpgid", _itself)
        patch.setattr(os, "killpg", remember)
        with pytest.raises(ExplainerError):
            explainer.explain(REPORT, "the briefing")
    assert killed == [4242], "the process group, not the process"


def _itself(pid: int) -> int:
    """A `getpgid` for a process that is its own group leader."""
    return pid


def test_the_guard_against_running_the_real_command_is_loaded() -> None:
    """`-p noclaude` is resolved through `pythonpath`, which is ini ordering.

    If that ever stops working the guard silently disappears and the first test
    to forget a stand-in spends real quota. This notices.
    """
    with pytest.raises(AssertionError, match="tried to run the real"):
        subprocess.run(["/usr/local/bin/claude", "-p"], check=False)


def test_the_group_is_the_child_pid_not_something_asked_for() -> None:
    """`setsid` runs in the child, after the fork the parent returned from.

    So a `getpgid` that wins the race reads the group the child *inherited* --
    the server's own -- and killing that takes the API down on an ordinary
    coach request. A process that calls `setsid` leads a group numbered after
    itself, so the pid is the answer, and it is the answer before the child has
    run at all.
    """
    fake = Raises(subprocess.TimeoutExpired("claude", 90))
    killed: list[int] = []

    def remember(group: int, _signal: int) -> None:
        killed.append(group)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "killpg", remember)
        # Would be asked in the racy version, and would answer wrongly.
        patch.setattr(os, "getpgid", _the_servers_group)
        with pytest.raises(ExplainerError):
            ClaudeCliExplainer().explain(REPORT, "the briefing")
    assert killed == [4242], "the child's pid, not whatever getpgid said"


def _the_servers_group(_pid: int) -> int:
    """What `getpgid` returns when it wins the race against `setsid`."""
    return os.getpgrp()


def test_the_pipes_are_shut_when_the_command_times_out() -> None:
    """`communicate` closes them when it returns; on a timeout it does not.

    So every question that took too long leaked three file descriptors, and the
    timeout path is the one that repeats.
    """
    fake = Raises(subprocess.TimeoutExpired("claude", 90))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "killpg", kills_nothing)
        with pytest.raises(ExplainerError):
            ClaudeCliExplainer().explain(REPORT, "the briefing")
    assert fake.started is not None
    assert fake.started.closed


def test_a_command_that_finished_is_not_killed_by_pid() -> None:
    """Its pid can have been handed to something else by then.

    `communicate` reaps the child, so killing "its" group afterwards is a
    chance to SIGKILL a stranger. The case the kill is for is the case that did
    not finish.
    """
    fake = envelope_answer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "killpg", _never_killed)
        assert ClaudeCliExplainer().explain(REPORT, "the briefing").play == "abc"


def _never_killed(group: int, _signal: int) -> None:
    """A `killpg` that must not be called.

    Raises:
        AssertionError: Always. Being called is the failure.
    """
    msg = f"killed group {group} after a clean exit, which may be somebody else's"
    raise AssertionError(msg)
