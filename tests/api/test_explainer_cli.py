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

from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.coach.advice import ExplainerError
from mtgcoach.coach.report import advise
from test_explainer import ANSWER, BOOK, FOREST, FOREST_RULES, REPORT, envelope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport

type Run = subprocess.CompletedProcess[str]


class Fake:
    """A stand-in for ``subprocess.run`` that records how it was called."""

    def __init__(self, *, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        """Answer every call with this output."""
        self.completed = subprocess.CompletedProcess(["claude"], code, stdout, stderr)
        self.argv: tuple[str, ...] = ()
        self.stdin = ""

    def __call__(self, argv: Sequence[str], **kwargs: object) -> Run:
        """Record the call and return the canned result."""
        self.argv = tuple(argv)
        given = kwargs.get("input")
        self.stdin = given if isinstance(given, str) else ""
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


def _answered() -> Fake:
    """A command that answers properly."""
    return Fake(stdout=envelope(json.dumps(ANSWER)))


# --- the call ----------------------------------------------------------------


def test_sends_the_briefing_and_reads_the_reply() -> None:
    fake = _answered()
    assert explain(fake).play == "abc"
    assert fake.stdin == "the briefing"


def test_asks_the_model_it_was_configured_with() -> None:
    fake = _answered()
    explain(fake)
    assert fake.after("--model") == "opus"


def test_the_coach_may_not_edit_anything() -> None:
    """It is asked to think about a board, not to touch the repository."""
    fake = _answered()
    explain(fake)
    tools = fake.after("--disallowedTools")
    assert "Write" in tools
    assert "Bash" in tools


# --- the ways it fails --------------------------------------------------------


def test_a_failing_command_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="exited 1: boom"):
        explain(Fake(code=1, stderr="boom"))


def test_a_missing_command_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="could not ask the coach"):
        explain(Raises(FileNotFoundError("no claude")))


def test_a_slow_command_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="could not ask the coach"):
        explain(Raises(subprocess.TimeoutExpired("claude", 90)))


# --- turns with no decision in them -------------------------------------------


def test_an_empty_turn_is_answered_without_asking() -> None:
    """Most of a game is steps with no choice. Those cost nothing."""
    got = explain(Never(), advise(game(), ME, BOOK))
    assert "pass the turn" in got.in_short
    assert got.play == ""


def test_a_turn_with_an_unmodelled_card_is_still_asked_about() -> None:
    """The engine could not speak for it, so somebody has to."""
    book = Book(
        cards={"Forest": FOREST, "Odd": facts("Odd Thing", "{1}")},
        rules={"Forest": FOREST_RULES, "Odd": (UNKNOWN_ABILITY,)},
    )
    report = advise(game(battlefield=("Odd",)), ME, book)
    assert report.unknown
    fake = _answered()
    assert explain(fake, report).play == "abc"
    assert fake.stdin == "the briefing"
