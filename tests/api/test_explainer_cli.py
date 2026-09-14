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
from test_explainer import ANSWER, REPORT, envelope

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport


def explain(fake: Fake | Raises | Never, report: TurnReport = REPORT) -> Explanation:
    """Run the explainer with the process boundary replaced."""
    explainer = ClaudeCliExplainer()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        patch.setattr(os, "killpg", kills_nothing)
        return explainer.explain(report, "the briefing")


def kills_nothing(_group: int, _signal: int) -> None:
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
