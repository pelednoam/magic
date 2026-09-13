"""Confine coverage opt-out comments to paths where coverage is truly impossible.

The coverage policy is 100% on every package whose code is deterministic. The
honest exception is the OpenCV pipeline, which cannot be unit-tested against
real glare and is gated on a recognition-accuracy corpus instead. Rather than
re-argue that exception per file forever, it is an explicit allowlist here --
and anything opting out from outside it fails the build.

Unreachable-by-design lines (``if TYPE_CHECKING:``, ``assert_never``, the
``__main__`` guard) are excluded via ``exclude_also`` in ``pyproject.toml``
rather than with an opt-out comment, which is what keeps this allowlist
meaningful.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: coverage.py's own default exclude pattern, copied verbatim from
#: ``coverage.config.DEFAULT_EXCLUDE``. An exact-substring search missed every
#: other spelling coverage honours -- no space after the hash, a space instead
#: of the colon, upper case -- so an opt-out could sit outside the allowlist,
#: be obeyed by coverage, and never be reported. Matching what coverage matches
#: is the only spelling-proof definition of "an opt-out".
PRAGMA_PATTERN: Final = re.compile(r"#\s*(pragma|PRAGMA)[:\s]?\s*(no|NO)\s*(cover|COVER)")

#: Path prefixes permitted to opt out of coverage. Empty by design: nothing
#: qualifies yet. The OpenCV pipeline is added here when it lands in M7, and
#: every addition should be argued for in the change that makes it.
ALLOWED_PREFIXES: Final[tuple[str, ...]] = ()

DEFAULT_ROOTS: Final[tuple[str, ...]] = ("packages", "services", "tools", "tests")


def is_allowed(path: Path, allowed: Iterable[str] = ALLOWED_PREFIXES) -> bool:
    """Whether ``path`` sits under a prefix permitted to opt out."""
    posix = path.as_posix()
    return any(posix.startswith(prefix) for prefix in allowed)


def find_pragmas(path: Path) -> list[int]:
    """Return the 1-based line numbers in ``path`` carrying an opt-out."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [number for number, line in enumerate(lines, 1) if PRAGMA_PATTERN.search(line)]


def find_violations(
    paths: Iterable[Path],
    allowed: Iterable[str] = ALLOWED_PREFIXES,
) -> list[tuple[Path, int]]:
    """Return ``(path, line_number)`` for each disallowed opt-out."""
    allowed = tuple(allowed)
    return [
        (path, number)
        for path in paths
        if not is_allowed(path, allowed)
        for number in find_pragmas(path)
    ]


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
    args = parser.parse_args(argv)

    paths: list[Path] = args.files or collect_python_files([Path(root) for root in DEFAULT_ROOTS])
    violations = find_violations(paths)
    for path, number in violations:
        print(f"{path}:{number}: coverage opt-out outside the allowlist")
    if violations:
        print(
            f"\n{len(violations)} disallowed opt-out(s). Cover the code, or argue "
            "the path into ALLOWED_PREFIXES in tools/check_pragma_allowlist.py."
        )
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
