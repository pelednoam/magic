"""The check that the coach's tool lockdown is still spelled the way it is sent.

The tests that cover the lockdown replace ``subprocess.run``, so they pin the
argv this project writes rather than what the CLI accepts. A renamed flag would
turn every question into a 503 in production with the suite still green. This
reads the help text instead, which is cheap enough to run on every commit.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

import check_cli_flags as gate

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

GOOD = """
  -p, --print
  --model <model>
  --output-format <format>
  --strict-mcp-config
  --tools <tools...>   Specify the list of available tools from the
                       built-in set. Use "" to disable all
                       tools, "default" to use all tools.
"""


def test_a_help_text_with_everything_in_it_passes() -> None:
    assert gate.missing(GOOD) == []


def test_the_wrapped_sentence_is_found_across_lines() -> None:
    """It is wrapped to the terminal, so a plain substring search never found it."""
    assert gate.EMPTIES_TOOLS not in GOOD
    assert gate.missing(GOOD) == []


@pytest.mark.parametrize("flag", gate.REQUIRED)
def test_a_missing_flag_is_reported(flag: str) -> None:
    assert gate.missing(GOOD.replace(flag, "--gone")) == [flag]


def test_a_tools_flag_that_no_longer_empties_the_set_is_reported() -> None:
    """The flag surviving is not the same as it still meaning what we need."""
    changed = GOOD.replace('Use "" to disable all', "Use ALL to enable all")
    (reported,) = gate.missing(changed)
    assert "empty --tools" in reported


def _says(text: str) -> Callable[[], str]:
    """A `help_text` that returns this."""
    return lambda: text


def _installed(_name: str) -> str | None:
    """A `shutil.which` that finds the command."""
    return "/usr/bin/claude"


def _absent(_name: str) -> str | None:
    """A `shutil.which` that does not."""
    return None


def test_a_machine_without_the_cli_is_skipped_rather_than_failed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """This is a check on the local environment, not on the code."""
    monkeypatch.setattr(shutil, "which", _absent)
    assert gate.main() == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_a_good_cli_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", _installed)
    monkeypatch.setattr(gate, "help_text", _says(GOOD))
    assert gate.main() == 0


def test_a_changed_cli_fails_and_says_where_to_look(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(shutil, "which", _installed)
    monkeypatch.setattr(gate, "help_text", _says(GOOD.replace("--tools", "--gone")))
    assert gate.main() == 1
    said = capsys.readouterr().out
    assert "--tools" in said
    assert "claude.py" in said


def test_a_command_that_cannot_be_run_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="could not run"):
        gate.help_text(str(tmp_path / "not-there"))


def test_a_command_that_refuses_is_an_error() -> None:
    assert "exited" in _refusal()


def _refusal() -> str:
    """What `help_text` says about a command that exits non-zero."""
    with pytest.raises(RuntimeError) as refused:
        gate.help_text("false")
    return str(refused.value)


def test_a_command_that_answers_gives_back_what_it_printed() -> None:
    """`echo` stands in for the CLI: it exits zero and prints its argument."""
    assert "--help" in gate.help_text("echo")
