"""Fail the build when CI runs less than the gate the README promises.

``tools/gate.sh`` is what a developer runs and what the README calls the full
gate. ``.github/workflows/ci.yml`` is what actually guards the trunk. They
drifted: CI omitted the CLI-flag check, both rules checks, the TypeScript
typecheck and the whole mobile test suite -- so a change to the events the app
sends when you tap a card could go green with nothing having typechecked it.

Nothing noticed, because nothing was looking. This looks: every command the
gate runs must appear somewhere in the workflow. Matched on the command rather
than the step name, because a name is prose and a command is the thing that
either ran or did not.

Not the other way round. CI may do *more* than the gate -- it fetches the
Comprehensive Rules, which a developer installs once by hand -- and a workflow
that was forbidden from adding a check would be a worse workflow.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

#: Where the two definitions live.
GATE: Final = Path("tools/gate.sh")
WORKFLOW: Final = Path(".github/workflows/ci.yml")

#: A command in ``gate.sh``, as it appears after the `&&` in an echo-and-run
#: line. The gate is written as `echo "== name" && <command>`, which is what
#: makes the pairing readable there and findable here.
RUNS: Final = re.compile(r'echo\s+"==[^"]*"\s+&&\s+(.+?)\s*$', re.MULTILINE)

#: Commands the gate runs that CI is not expected to run verbatim.
#:
#: The guard on the guard: every entry needs a reason, because an exemption
#: list is how a coverage check becomes decorative. There is one, and it is
#: the branch that exists *because* CI is a different environment.
EXEMPT: Final[tuple[tuple[str, str], ...]] = (
    (
        "npm install",
        "the gate's advice to a developer without node_modules; CI runs npm ci",
    ),
)


def commands(gate: str) -> list[str]:
    """Every command the gate runs, in order."""
    return [found.strip() for found in RUNS.findall(gate)]


def normalised(command: str) -> str:
    """One command, with the noise a workflow legitimately changes removed.

    CI adds `--output-format=github` so failures annotate the diff, and runs
    the app's checks from a `working-directory` rather than a subshell `cd`.
    Neither is the check being different; both would make a literal comparison
    useless.
    """
    stripped = command
    for noise in ("--output-format=github", "--no-install", "--reporter=dot"):
        stripped = stripped.replace(noise, "")
    stripped = re.sub(r"\(cd\s+\S+\s+&&\s*", "", stripped)
    stripped = stripped.replace(")", "")
    return " ".join(stripped.split())


def missing(gate: str, workflow: str) -> list[str]:
    """Every gate command the workflow does not run."""
    exempt = {normalised(command) for command, _ in EXEMPT}
    running = normalised(workflow)
    absent: list[str] = []
    for command in commands(gate):
        wanted = normalised(command)
        if not wanted or wanted in exempt:
            continue
        if wanted not in running:
            absent.append(command)
    return absent


def report(absent: Iterable[str]) -> int:
    """Print what CI is not running, and say what to do about it."""
    found = list(absent)
    if not found:
        return 0
    print(f"{WORKFLOW} runs less than {GATE}. Missing:")
    for command in found:
        print(f"  {command}")
    print(f"\nAdd each to {WORKFLOW}, or to EXEMPT in this file with a reason.")
    print("A green CI that checks less than the README promises is worse than")
    print("a red one, because nobody goes looking.")
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Compare the gate with the workflow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path())
    args = parser.parse_args(argv)
    gate = (args.root / GATE).read_text(encoding="utf-8")
    workflow = (args.root / WORKFLOW).read_text(encoding="utf-8")
    return report(missing(gate, workflow))


if __name__ == "__main__":
    sys.exit(main())
