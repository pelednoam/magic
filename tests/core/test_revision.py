"""The engine's own digest: what changes it, and what does not.

It exists because a journal that records only its events cannot say what engine
produced them -- which is what made a whole directory of them unreadable when
priority arrived and every recorded `advance_step` became illegal, with nothing
on disk saying the games predated the rule.

So these are about the two properties a digest has to have to be worth
recording: the same source gives the same answer, and a different source gives
a different one. Written against a directory the test builds, not against
`mtgcoach.core` -- a test that asserted a literal digest of the real package
would fail on every edit and teach everybody to update the literal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.revision import LENGTH, digest_of, engine

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


def _package(root: Path, files: Mapping[str, str]) -> Path:
    """A directory of source files, written out.

    Keyed by filename, because the filename is half of what is being tested:
    the digest covers each file's relative path as well as its bytes.
    """
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def test_the_same_source_gives_the_same_digest(tmp_path: Path) -> None:
    """Or two runs of one engine would look like two engines."""
    one = _package(tmp_path / "one", {"a.py": "x = 1\n"})
    two = _package(tmp_path / "two", {"a.py": "x = 1\n"})
    assert digest_of(one) == digest_of(two)


def test_changed_source_gives_a_different_digest(tmp_path: Path) -> None:
    before = digest_of(_package(tmp_path / "engine", {"a.py": "x = 1\n"}))
    after = digest_of(_package(tmp_path / "engine", {"a.py": "x = 2\n"}))
    assert before != after


def test_a_renamed_module_gives_a_different_digest(tmp_path: Path) -> None:
    """The path goes into the hash, not only the bytes.

    Without it, renaming a module -- or moving a function from one to another
    -- leaves the digest unchanged, and the digest would then be over a bag of
    text rather than over an engine.
    """
    one = digest_of(_package(tmp_path / "one", {"a.py": "x = 1\n"}))
    two = digest_of(_package(tmp_path / "two", {"b.py": "x = 1\n"}))
    assert one != two


def test_a_module_in_a_subpackage_counts(tmp_path: Path) -> None:
    """`core.combat` is a package of its own, and it is part of the engine."""
    bare = digest_of(_package(tmp_path / "one", {"a.py": "x = 1\n"}))
    nested = _package(tmp_path / "two", {"a.py": "x = 1\n"})
    (nested / "combat").mkdir()
    (nested / "combat" / "search.py").write_text("y = 2\n", encoding="utf-8")
    assert digest_of(nested) != bare


def test_something_that_is_not_source_does_not_count(tmp_path: Path) -> None:
    """A stray `.pyc`, a note, an editor's backup.

    None of them is the engine, and a digest that moved when one appeared would
    report a difference nobody made.
    """
    before = digest_of(_package(tmp_path / "engine", {"a.py": "x = 1\n"}))
    (tmp_path / "engine" / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "engine" / "a.pyc").write_bytes(b"\x00\x01")
    assert digest_of(tmp_path / "engine") == before


def test_the_real_engine_has_one_and_it_is_short_enough_to_read() -> None:
    """Carried in every journal line, so it is trimmed rather than full-length."""
    assert len(engine()) == LENGTH
    assert engine() == engine(), "cached, and stable within a process"
