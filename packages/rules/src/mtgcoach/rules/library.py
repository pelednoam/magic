"""Where the Comprehensive Rules live on disk, and how to get them there.

Not vendored into the repository. It is a 900 KB document Wizards publishes and
revises with every set, it is not ours to redistribute, and a stale copy of the
rules is exactly the kind of confidently-wrong answer this project is built to
avoid. So it is a file the operator installs, and the server says plainly when
it is missing rather than answering without it.

Install it with:

    mkdir -p data/rules
    curl -L -o data/rules/comprehensive.txt "$URL"

where ``$URL`` is the plain-text link on https://magic.wizards.com/en/rules --
the current one at the time of writing is

    https://media.wizards.com/2025/downloads/MagicCompRules%2020250207.txt

but that address carries its own date, and Wizards publish a new one with every
set. Pointing an operator at the page rather than at one file is deliberate: a
rules document eighteen months old answers questions about cards that have been
errataed, and does it confidently.

The file is UTF-8 with a byte-order mark, which ``utf-8-sig`` handles.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.rules.corpus import CorpusError, passages_in
from mtgcoach.rules.effective import effective_from
from mtgcoach.rules.search import RuleIndex

if TYPE_CHECKING:
    from pathlib import Path

#: Where ``serve`` looks, relative to the data directory.
RULES_FILE = "rules/comprehensive.txt"

#: The fewest passages an installed document can have and still be the rules.
#: The real one has a few thousand. A truncated download that happens to carry
#: the four markers parses to a handful, and without this the server indexed
#: it, said ``rules_available`` and answered questions out of a fragment --
#: which is the confidently-incomplete failure this package exists to avoid.
LEAST_CREDIBLE = 500


class RulesNotInstalledError(FileNotFoundError):
    """The Comprehensive Rules are not on disk, so no question can be answered."""


@dataclass(frozen=True, slots=True)
class Installed:
    """The rules this server has, and which revision they are.

    Together because they come out of one read of one file, and because a
    revision without the document it describes is a claim nothing backs. The
    revision is the document's own sentence -- "These rules are effective as of
    August 7, 2026" -- read by ``effective``; empty when the file does not say.
    """

    index: RuleIndex
    revision: str


def rules_path(data_root: Path) -> Path:
    """Where the rules document should be."""
    return data_root / RULES_FILE


def index_at(path: Path, least: int = LEAST_CREDIBLE) -> RuleIndex:
    """Read and index the rules document, without its revision.

    For a caller that only searches. ``installed_at`` is the one the server
    uses, because a game records which revision it was played under.

    Raises:
        RulesNotInstalledError: If the file is not there.
        CorpusError: If it is there but is not the rules.
    """
    return installed_at(path, least).index


def installed_at(path: Path, least: int = LEAST_CREDIBLE) -> Installed:
    """Read and index the rules document, and read off which revision it is.

    Raises:
        RulesNotInstalledError: If the file is not there, with the command that
            puts it there -- an operator reading a stack trace at a kitchen
            table needs the fix, not the location of the raise.
        CorpusError: If it is there but is not the rules, or is too little of
            them to be a real install. ``least`` is how little that is, a
            parameter only so that a test can index a short excerpt rather than
            carry a megabyte of Wizards' document.
    """
    if not path.is_file():
        msg = (
            f"the Comprehensive Rules are not at {path}. Download the plain-text "
            f"rules from https://magic.wizards.com/en/rules and save them there:\n"
            f"  mkdir -p -- {shlex.quote(str(path.parent))}\n"
            f'  curl -L -o {shlex.quote(str(path))} "$URL"'
        )
        raise RulesNotInstalledError(msg)
    text = path.read_text(encoding="utf-8-sig")
    found = passages_in(text)
    if len(found) < least:
        msg = (
            f"{path} parses to only {len(found)} rules; the Comprehensive Rules "
            "have a few thousand, so this is probably a truncated download"
        )
        raise CorpusError(msg)
    return Installed(index=RuleIndex.build(found), revision=effective_from(text))
