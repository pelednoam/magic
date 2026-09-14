"""Running the ``claude`` command, without running it.

``subprocess.Popen`` is replaced throughout. What is tested is the argv, what
goes in on stdin, and that a failure of any kind becomes an ``ExplainerError``
rather than a traceback.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from fakeprocess import Fake, Never, Raises
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.coach.advice import ExplainerError
from test_explainer import ANSWER, REPORT, envelope

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport


def explain(fake: Fake | Raises | Never, report: TurnReport = REPORT) -> Explanation:
    """Run the explainer with the process boundary replaced."""
    explainer = ClaudeCliExplainer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "killpg", _nothing)
        return explainer.explain(report, "the briefing")


def _nothing(_group: int, _signal: int) -> None:
    """A `killpg` that kills nothing, since nothing was started."""


def envelope_answer() -> Fake:
    """A command that answers properly."""
    return Fake(stdout=envelope(json.dumps(ANSWER)))


def test_sends_the_briefing_and_reads_the_reply() -> None:
    fake = envelope_answer()
    assert explain(fake).play == "abc"
    assert fake.stdin == "the briefing"


def test_asks_the_model_it_was_configured_with() -> None:
    fake = envelope_answer()
    explain(fake)
    assert fake.after("--model") == "opus"


def test_the_coach_gets_no_tools_at_all() -> None:
    """An empty allow-list, not a deny-list naming today's dangerous tools.

    The deny-list this replaced named the five write tools and left Read, Glob,
    Grep, WebFetch, WebSearch and Task enabled. That was verified to be
    exploitable: the same prompt with tools on read /etc/hostname and returned
    its contents. A rules question is unauthenticated text a player typed, so
    that is a file-read primitive and an egress primitive in one session.

    ``tools/check_cli_flags.py`` is the other half of this: it checks the flag
    still exists and still means what we need, which a stubbed subprocess
    cannot.
    """
    fake = envelope_answer()
    explain(fake)
    assert fake.after("--tools") == ""
    assert "--disallowedTools" not in fake.argv, "a deny-list rots; an allow-list does not"
    assert "--strict-mcp-config" in fake.argv, "an MCP server would put tools back"


def test_the_coach_runs_somewhere_private_and_empty() -> None:
    """The CLI reads a CLAUDE.md from its working directory as instructions.

    So the shared temp directory was a place any local user could leave one and
    have it prepended to every question this server asks.
    """
    fake = envelope_answer()
    explain(fake)
    assert isinstance(fake.cwd, str)
    where = Path(fake.cwd)
    assert "magic" not in fake.cwd
    assert list(where.iterdir()) == []
    assert where.stat().st_mode & 0o077 == 0, "readable only by this user"


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
