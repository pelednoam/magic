"""Where the rules document lives, and what happens when it does not.

Not installing it is a legitimate way to run this project: the tracker, the
engine and the turn coach all work without it. So the interesting case is the
missing one, and what it says.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from helpers_rules import EXCERPT
from mtgcoach.rules.corpus import CorpusError
from mtgcoach.rules.library import RULES_FILE, RulesNotInstalledError, index_at, rules_path

if TYPE_CHECKING:
    from pathlib import Path


def test_the_document_is_read_and_indexed() -> None:
    with index_at(EXCERPT) as index:
        assert [p.reference for p in index.search("trample")]


def test_the_path_is_under_the_data_directory(tmp_path: Path) -> None:
    assert rules_path(tmp_path) == tmp_path / RULES_FILE


def test_a_missing_document_says_how_to_install_it(tmp_path: Path) -> None:
    """An operator reading this at a kitchen table needs the fix, not a path."""
    with pytest.raises(RulesNotInstalledError) as refused:
        index_at(rules_path(tmp_path))
    said = str(refused.value)
    assert "curl" in said
    # The rules page, not a dated file. Wizards publish a new document with
    # every set, and an eighteen-month-old copy answers errataed cards with
    # confidence -- which is the failure the whole retrieval design avoids.
    assert "magic.wizards.com/en/rules" in said


def test_the_install_command_quotes_an_awkward_path(tmp_path: Path) -> None:
    """It is meant to be pasted into a shell, and a data root can have a space."""
    awkward = tmp_path / "my data"
    with pytest.raises(RulesNotInstalledError) as refused:
        index_at(rules_path(awkward))
    assert "'" in str(refused.value)


def test_a_document_that_is_not_the_rules_is_reported_as_such(tmp_path: Path) -> None:
    """A truncated download, or the HTML of an error page."""
    installed = tmp_path / RULES_FILE
    installed.parent.mkdir(parents=True)
    installed.write_text("<html>404</html>", encoding="utf-8")
    with pytest.raises(CorpusError):
        index_at(rules_path(tmp_path))


def test_a_directory_where_the_document_should_be_is_also_missing(tmp_path: Path) -> None:
    """`open` on a directory raises IsADirectoryError, which nothing catches."""
    (tmp_path / RULES_FILE).mkdir(parents=True)
    with pytest.raises(RulesNotInstalledError):
        index_at(rules_path(tmp_path))


def test_a_document_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    """Wizards publish it as UTF-8 with a BOM, which would corrupt line one."""
    installed = tmp_path / RULES_FILE
    installed.parent.mkdir(parents=True)
    installed.write_text(EXCERPT.read_text(encoding="utf-8"), encoding="utf-8-sig")
    with index_at(rules_path(tmp_path)) as index:
        assert index.cited(["702.19b"])
