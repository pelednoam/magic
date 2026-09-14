"""Running the ``claude`` command, without running it.

``subprocess.run`` is replaced throughout. What is tested is the argv, what goes
in on stdin, that a failure of any kind becomes an ``ExplainerError`` rather
than a traceback -- and that a turn with no decision in it never spends a
subprocess at all.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.coach.advice import ExplainerError
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.vocabulary import TriggerEvent
from test_explainer import ANSWER, REPORT, envelope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport

type Run = subprocess.CompletedProcess[str]

#: A creature whose ability fires on the clock, so a turn has a reminder on it.
RINGS = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())


class Fake:
    """A stand-in for ``subprocess.run`` that records how it was called."""

    def __init__(self, *, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        """Answer every call with this output."""
        self.completed = subprocess.CompletedProcess(["claude"], code, stdout, stderr)
        self.argv: tuple[str, ...] = ()
        self.stdin = ""
        self.cwd: object = None

    def __call__(self, argv: Sequence[str], **kwargs: object) -> Run:
        """Record the call and return the canned result."""
        self.argv = tuple(argv)
        given = kwargs.get("input")
        self.stdin = given if isinstance(given, str) else ""
        self.cwd = kwargs.get("cwd")
        return self.completed

    def after(self, flag: str) -> str:
        """The argument following ``flag``."""
        return self.argv[self.argv.index(flag) + 1]


class Raises:
    """A stand-in that fails the way a missing or slow command fails."""

    def __init__(self, error: Exception) -> None:
        """Fail every call with this error."""
        self.error = error

    def __call__(self, _argv: Sequence[str], **_kwargs: object) -> Run:
        """Never return.

        Raises:
            Exception: Whatever this stand-in was built with.
        """
        raise self.error


class Never:
    """A stand-in that fails the test if the command is run at all."""

    def __call__(self, argv: Sequence[str], **_kwargs: object) -> Run:
        """Never return.

        Raises:
            AssertionError: Always. Being called is the failure.
        """
        msg = f"asked the model about a turn with nothing in it: {argv}"
        raise AssertionError(msg)


def explain(fake: Fake | Raises | Never, report: TurnReport = REPORT) -> Explanation:
    """Run the explainer with ``subprocess.run`` replaced."""
    explainer = ClaudeCliExplainer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", fake)
        return explainer.explain(report, "the briefing")


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

    The deny-list this replaced named the five write tools and left Read,
    Glob, Grep, WebFetch, WebSearch and Task enabled. That was verified to be
    exploitable: the same prompt with tools on read /etc/hostname and returned
    its contents. A rules question is unauthenticated text a player typed, so
    that is a file-read primitive and an egress primitive in one session.
    """
    fake = envelope_answer()
    explain(fake)
    assert fake.after("--tools") == ""
    assert "--disallowedTools" not in fake.argv, "a deny-list rots; an allow-list does not"
    assert "--strict-mcp-config" in fake.argv, "an MCP server would put tools back"


def test_the_coach_runs_somewhere_with_nothing_in_it() -> None:
    """The working directory is what the CLI puts in its own system prompt."""
    fake = envelope_answer()
    explain(fake)
    assert fake.cwd not in {"", None}
    assert "magic" not in str(fake.cwd)


# --- the ways it fails --------------------------------------------------------


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
        explain(Raises(FileNotFoundError("/usr/local/bin/claude")))


def test_a_missing_command_does_not_leak_its_path() -> None:
    """Same reason as the exit code above: this message is sent to a client."""
    with pytest.raises(ExplainerError) as refused:
        explain(Raises(FileNotFoundError("/usr/local/bin/claude")))
    assert "/usr/local" not in str(refused.value)


def test_a_slow_command_says_how_long_it_waited() -> None:
    """A timeout is the one failure a player can do something about."""
    with pytest.raises(ExplainerError, match="longer than 90s"):
        explain(Raises(subprocess.TimeoutExpired("claude", 90)))
