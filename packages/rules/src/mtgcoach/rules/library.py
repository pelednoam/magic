"""Where the Comprehensive Rules live on disk, and how to get them there.

Not vendored into the repository. It is a 900 KB document Wizards publishes and
revises with every set, it is not ours to redistribute, and a stale copy of the
rules is exactly the kind of confidently-wrong answer this project is built to
avoid. So it is a file the operator installs, and the server says plainly when
it is missing rather than answering without it.

Install it with:

    mkdir -p data/rules
    curl -L -o data/rules/comprehensive.txt
      "https://media.wizards.com/2025/downloads/MagicCompRules%2020250207.txt"

The file is UTF-8 with a byte-order mark, which ``utf-8-sig`` handles.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.rules.corpus import passages_in
from mtgcoach.rules.search import RuleIndex

if TYPE_CHECKING:
    from pathlib import Path

#: Where ``serve`` looks, relative to the data directory.
RULES_FILE = "rules/comprehensive.txt"


class RulesNotInstalledError(FileNotFoundError):
    """The Comprehensive Rules are not on disk, so no question can be answered."""


def rules_path(data_root: Path) -> Path:
    """Where the rules document should be."""
    return data_root / RULES_FILE


def index_at(path: Path) -> RuleIndex:
    """Read and index the rules document.

    Raises:
        RulesNotInstalledError: If the file is not there, with the command that
            puts it there -- an operator reading a stack trace at a kitchen
            table needs the fix, not the location of the raise.
    """
    if not path.is_file():
        msg = (
            f"the Comprehensive Rules are not at {path}. Install them with:\n"
            f"  mkdir -p {path.parent}\n"
            f'  curl -L -o {path} "https://media.wizards.com/2025/downloads/'
            'MagicCompRules%2020250207.txt"'
        )
        raise RulesNotInstalledError(msg)
    return RuleIndex.build(passages_in(path.read_text(encoding="utf-8-sig")))
