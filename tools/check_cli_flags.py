"""Check that the local ``claude`` command still takes the flags we send it.

The tool lockdown is the headline safety property of the Claude layer, and the
tests that cover it replace ``subprocess.run`` -- so they pin the argv this
project writes, not that the CLI accepts it. If a flag is renamed or dropped,
every ``/coach`` and ``/ask`` request becomes a 503 in production while the
whole suite stays green, and if an unknown flag were ignored rather than
rejected the lockdown would simply not be applied.

This closes that gap the cheap way: read ``claude --help`` and look for the
flags. No model call, no quota, a few hundred milliseconds. It cannot prove the
flags *work* -- only a real run does that, and one is in the commit log -- but
it does catch the thing that actually happens, which is a CLI release moving
them.

Skipped, loudly, when ``claude`` is not installed: this is a check on the local
environment, and a machine without the CLI cannot run the coach anyway. That
does mean a green run on such a machine says nothing about the lockdown, which
is why the skip prints rather than passing silently.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from typing import Final

#: Every flag the API sends. Kept here rather than imported so that this script
#: has no dependency on the workspace being installed.
REQUIRED: Final[tuple[str, ...]] = (
    "--tools",
    "--strict-mcp-config",
    "--output-format",
    "--model",
    "-p",
)

#: The sentence that says an empty ``--tools`` means no tools at all. Without
#: it the flag might still exist and mean something else.
EMPTIES_TOOLS: Final = 'Use "" to disable all tools'

HELP_TIMEOUT: Final = 30


def help_text(executable: str = "claude") -> str:
    """What the command prints for ``--help``.

    Raises:
        RuntimeError: If it cannot be run or refuses.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [executable, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HELP_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        msg = f"could not run `{executable} --help`: {type(exc).__name__}"
        raise RuntimeError(msg) from exc
    if completed.returncode != 0:
        msg = f"`{executable} --help` exited {completed.returncode}"
        raise RuntimeError(msg)
    return completed.stdout + completed.stderr


def missing(text: str) -> list[str]:
    """Every flag the help text does not mention, plus the tools sentence.

    Flags are matched as whole words, because a substring search for ``-p``
    finds it inside ``--print`` -- so the check would have passed on a CLI that
    had dropped the short flag entirely.

    The sentence about an empty ``--tools`` is matched against whitespace-
    normalised text instead: the help is wrapped to the terminal, so it arrives
    split across lines.
    """
    words = set(re.split(r"[\s,|]+", text))
    absent = [flag for flag in REQUIRED if flag not in words]
    flat = " ".join(text.split())
    if EMPTIES_TOOLS not in flat:
        absent.append(f"the documented meaning of an empty --tools ({EMPTIES_TOOLS!r})")
    return absent


def main() -> int:
    """Check the flags, or say why the check was skipped."""
    if shutil.which("claude") is None:
        print("== claude CLI        SKIPPED: not installed, so the coach cannot run here")
        return 0
    absent = missing(help_text())
    for flag in absent:
        print(f"`claude --help` no longer mentions {flag}")
    if absent:
        print("\nThe coach's tool lockdown may not be applied.")
        print("Check services/api/src/mtgcoach/api/claude.py.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
