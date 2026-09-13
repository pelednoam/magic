"""Fail the build when a module grows past the project's line limit.

The limit is not aesthetic. Small modules keep ``mypy --strict`` errors local,
make 100% branch coverage reachable file by file, keep mutation testing finite,
and keep review-agent diffs small enough for four models to reason about in one
pass. Ruff has no file-length rule, so this fills the gap.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

MAX_LINES: Final = 200

DEFAULT_ROOTS: Final[tuple[str, ...]] = ("packages", "services", "tools", "tests")


def count_lines(path: Path) -> int:
    """Return the number of lines in ``path``."""
    return len(path.read_text(encoding="utf-8").splitlines())


def find_violations(
    paths: Iterable[Path],
    max_lines: int = MAX_LINES,
) -> list[tuple[Path, int]]:
    """Return ``(path, line_count)`` for every file exceeding ``max_lines``.

    Results are sorted longest first so the worst offender is reported at the
    top of the failure.
    """
    violations = [(path, count) for path in paths if (count := count_lines(path)) > max_lines]
    return sorted(violations, key=lambda item: item[1], reverse=True)


def collect_python_files(roots: Iterable[Path]) -> list[Path]:
    """Return every ``.py`` file under ``roots``, sorted, skipping caches."""
    found = [
        path
        for root in roots
        if root.exists()
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    return sorted(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Check the given files, or the default roots when none are given."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Files to check.")
    parser.add_argument("--max-lines", type=int, default=MAX_LINES)
    args = parser.parse_args(argv)

    paths: list[Path] = args.files or collect_python_files([Path(root) for root in DEFAULT_ROOTS])
    violations = find_violations(paths, args.max_lines)
    for path, count in violations:
        print(f"{path}: {count} lines exceeds the {args.max_lines}-line limit")
    if violations:
        print(f"\n{len(violations)} file(s) too long. Split them.")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
