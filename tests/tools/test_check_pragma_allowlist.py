"""The opt-out allowlist is what stops the coverage policy becoming theatre.

The opt-out marker is never written literally in this file -- it is built from
``gate.PRAGMA`` -- so that the gate scanning the repository does not flag its
own test fixtures.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import check_pragma_allowlist as gate

if TYPE_CHECKING:
    import pytest

PRAGMA_LINE = f"def f() -> None:  # {gate.PRAGMA}\n"


def test_allowlist_is_empty_by_default() -> None:
    """Nothing qualifies yet. M7's OpenCV pipeline is the first candidate."""
    assert gate.ALLOWED_PREFIXES == ()


def test_is_allowed_matches_a_prefix(tmp_path: Path) -> None:
    assert gate.is_allowed(Path("packages/vision/src/pipeline.py"), ["packages/vision/"])
    assert not gate.is_allowed(Path("packages/core/src/state.py"), ["packages/vision/"])
    assert not gate.is_allowed(tmp_path / "x.py", [])


def test_find_pragmas_reports_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("import os\n\n" + PRAGMA_LINE, encoding="utf-8")
    assert gate.find_pragmas(path) == [3]


def test_find_pragmas_on_a_clean_file(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    assert gate.find_pragmas(path) == []


def test_violation_outside_the_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text(PRAGMA_LINE, encoding="utf-8")
    assert gate.find_violations([path], allowed=[]) == [(path, 1)]


def test_no_violation_inside_the_allowlist(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text(PRAGMA_LINE, encoding="utf-8")
    assert gate.find_violations([path], allowed=[path.as_posix()]) == []


def test_collect_skips_caches_and_missing_roots(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__pycache__").mkdir()
    kept = tmp_path / "pkg" / "real.py"
    kept.write_text("x\n", encoding="utf-8")
    (tmp_path / "pkg" / "__pycache__" / "c.py").write_text("x\n", encoding="utf-8")
    assert gate.collect_python_files([tmp_path / "pkg", tmp_path / "gone"]) == [kept]


def test_main_passes_on_a_clean_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.py"
    path.write_text("x = 1\n", encoding="utf-8")
    assert gate.main([str(path)]) == 0
    assert capsys.readouterr().out == ""


def test_main_reports_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "a.py"
    path.write_text(PRAGMA_LINE, encoding="utf-8")
    assert gate.main([str(path)]) == 1
    out = capsys.readouterr().out
    assert "coverage opt-out outside the allowlist" in out
    assert "1 disallowed opt-out(s)" in out


def test_main_with_no_arguments_scans_the_default_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert gate.main([]) == 0


def test_the_repository_itself_has_no_disallowed_pragmas() -> None:
    assert gate.main([]) == 0
