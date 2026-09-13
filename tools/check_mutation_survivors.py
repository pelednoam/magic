"""Turn ``mutmut results`` into a gate that can actually fail.

``mutmut run`` exits 0 whether or not mutants survive, and ``mutmut results``
only prints. A nightly job that runs both is therefore green while the test
suite is failing to detect deliberately broken code -- which is the one thing
mutation testing exists to tell us.

Usage::

    mutmut results | python tools/check_mutation_survivors.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

#: Statuses meaning the mutation was not detected. ``no tests`` and
#: ``not checked`` count: a mutant nothing exercised is no better caught than
#: one the tests ran past.
ESCAPED: Final[frozenset[str]] = frozenset({"survived", "no tests", "not checked"})

#: Reported but not failed. These say something went wrong with the run rather
#: than with the tests, and failing on them would make the gate flaky.
TOLERATED: Final[frozenset[str]] = frozenset(
    {"suspicious", "timeout", "skipped", "check was interrupted by user"}
)


def parse_results(text: str) -> list[tuple[str, str]]:
    """Parse ``mutmut results`` output into ``(mutant_name, status)`` pairs.

    mutmut prints each non-killed mutant indented as ``    name: status``.
    Anything else in the stream is a heading or progress noise and is ignored.
    """
    pairs: list[tuple[str, str]] = []
    for raw in text.splitlines():
        if not raw.startswith("    ") or ": " not in raw:
            continue
        name, _, status = raw.strip().rpartition(": ")
        if name:
            pairs.append((name, status))
    return pairs


def escaped_mutants(pairs: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return the pairs whose status means the mutation went undetected."""
    return [(name, status) for name, status in pairs if status in ESCAPED]


def main(argv: Sequence[str] | None = None) -> int:
    """Read results from a file or stdin; fail if any mutant escaped."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results",
        nargs="?",
        help="File of `mutmut results` output. Reads stdin when omitted.",
    )
    args = parser.parse_args(argv)

    if args.results is None:
        text = sys.stdin.read()
    else:
        text = Path(args.results).read_text(encoding="utf-8")

    pairs = parse_results(text)
    escaped = escaped_mutants(pairs)
    tolerated = [p for p in pairs if p[1] in TOLERATED]
    unknown = [p for p in pairs if p[1] not in ESCAPED and p[1] not in TOLERATED]

    for name, status in escaped:
        print(f"ESCAPED  {name}: {status}")
    for name, status in tolerated:
        print(f"note     {name}: {status}")
    for name, status in unknown:
        print(f"note     {name}: {status} (unrecognised status)")

    if escaped:
        print(
            f"\n{len(escaped)} mutant(s) escaped. The tests run these lines "
            "without asserting on them."
        )
        return 1
    print(f"no mutants escaped ({len(pairs)} non-killed entries reported)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
