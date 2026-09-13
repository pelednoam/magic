"""The mutation gate must fail on survivors, or it is decoration."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import check_mutation_survivors as gate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

RESULTS = """\
To apply a mutant on disk:
    mutmut apply <id>

    mtgcoach.core.steps.next_step__mutmut_3: survived
    mtgcoach.core.mana.parse__mutmut_1: killed
    mtgcoach.core.mana.parse__mutmut_2: timeout
    mtgcoach.core.mana.parse__mutmut_9: no tests
"""


def test_parse_ignores_headings_and_keeps_pairs() -> None:
    assert gate.parse_results(RESULTS) == [
        ("mtgcoach.core.steps.next_step__mutmut_3", "survived"),
        ("mtgcoach.core.mana.parse__mutmut_1", "killed"),
        ("mtgcoach.core.mana.parse__mutmut_2", "timeout"),
        ("mtgcoach.core.mana.parse__mutmut_9", "no tests"),
    ]


def test_parse_ignores_unindented_lines() -> None:
    assert gate.parse_results("name: survived\n") == []


def test_parse_ignores_indented_lines_without_a_status() -> None:
    assert gate.parse_results("    just a note\n") == []


def test_parse_ignores_a_bare_status() -> None:
    """A bare status rpartitions to an empty name, which is not a mutant."""
    assert gate.parse_results("    : survived\n") == []


def test_escaped_selects_only_undetected_statuses() -> None:
    pairs = gate.parse_results(RESULTS)
    assert gate.escaped_mutants(pairs) == [
        ("mtgcoach.core.steps.next_step__mutmut_3", "survived"),
        ("mtgcoach.core.mana.parse__mutmut_9", "no tests"),
    ]


def test_main_fails_on_survivors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "results.txt"
    path.write_text(RESULTS, encoding="utf-8")
    assert gate.main([str(path)]) == 1
    out = capsys.readouterr().out
    assert "ESCAPED  mtgcoach.core.steps.next_step__mutmut_3: survived" in out
    assert "2 mutant(s) escaped" in out
    assert "note     mtgcoach.core.mana.parse__mutmut_2: timeout" in out


def test_main_passes_when_nothing_escaped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "results.txt"
    path.write_text("    a.b__mutmut_1: killed\n", encoding="utf-8")
    assert gate.main([str(path)]) == 0
    assert "no mutants escaped" in capsys.readouterr().out


def test_unrecognised_status_is_reported_but_not_fatal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A future mutmut status must not silently become a pass or a failure."""
    path = tmp_path / "results.txt"
    path.write_text("    a.b__mutmut_1: teleported\n", encoding="utf-8")
    assert gate.main([str(path)]) == 0
    assert "unrecognised status" in capsys.readouterr().out


def test_main_reads_stdin_when_given_no_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(RESULTS))
    assert gate.main([]) == 1
    assert "2 mutant(s) escaped" in capsys.readouterr().out
