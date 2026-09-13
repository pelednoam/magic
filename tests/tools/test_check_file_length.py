"""The file-length gate must itself be correct, or it silently passes everything."""

from __future__ import annotations

from typing import TYPE_CHECKING

import check_file_length as gate

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _write(path: Path, lines: int) -> Path:
    path.write_text("\n".join(["x"] * lines), encoding="utf-8")
    return path


def test_count_lines(tmp_path: Path) -> None:
    assert gate.count_lines(_write(tmp_path / "a.py", 7)) == 7


def test_empty_file_counts_zero(tmp_path: Path) -> None:
    (tmp_path / "empty.py").write_text("", encoding="utf-8")
    assert gate.count_lines(tmp_path / "empty.py") == 0


def test_a_file_at_the_limit_passes(tmp_path: Path) -> None:
    assert gate.find_violations([_write(tmp_path / "a.py", 10)], max_lines=10) == []


def test_a_file_over_the_limit_fails(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.py", 11)
    assert gate.find_violations([path], max_lines=10) == [(path, 11)]


def test_violations_are_sorted_worst_first(tmp_path: Path) -> None:
    small = _write(tmp_path / "small.py", 12)
    huge = _write(tmp_path / "huge.py", 40)
    assert gate.find_violations([small, huge], max_lines=10) == [(huge, 40), (small, 12)]


def test_collect_skips_caches_and_missing_roots(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__pycache__").mkdir()
    kept = tmp_path / "pkg" / "real.py"
    kept.write_text("x\n", encoding="utf-8")
    (tmp_path / "pkg" / "__pycache__" / "cached.py").write_text("x\n", encoding="utf-8")

    found = gate.collect_python_files([tmp_path / "pkg", tmp_path / "absent"])
    assert found == [kept]


def test_main_passes_on_short_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "a.py", 3)
    assert gate.main([str(path)]) == 0
    assert capsys.readouterr().out == ""


def test_main_reports_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path / "a.py", 5)
    assert gate.main([str(path), "--max-lines", "2"]) == 1
    out = capsys.readouterr().out
    assert "5 lines exceeds the 2-line limit" in out
    assert "1 file(s) too long" in out


def test_main_with_no_arguments_scans_the_default_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert gate.main([]) == 0


def test_the_repository_itself_obeys_the_limit() -> None:
    """Dogfooding: this is the gate CI runs, asserted from inside the suite."""
    assert gate.main([]) == 0
