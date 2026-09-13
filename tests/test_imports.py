"""Every module must be importable -- and therefore visible to the coverage gate.

coverage.py discovers unexecuted files by walking the configured source
directories, but it will not descend into a directory that has no
``__init__.py``. Our packages share the ``mtgcoach`` PEP 420 namespace, which
by definition has none, so a module that no test imports was reported by
coverage not as 0% but not at all -- and the run still passed at "100%".

Importing every module closes that hole: an unimported file becomes a traced
file, and its uncovered lines then count against the gate like any other.
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Roots that map a file path to a module name. Must match the coverage
#: ``source`` list in pyproject.toml; test_source_roots_match_coverage_config
#: below fails if they drift apart.
SOURCE_ROOTS = (
    "packages/core/src",
    "packages/carddata/src",
    "packages/vision/src",
    "services/api/src",
    "tools",
)


def _module_names() -> list[str]:
    names: list[str] = []
    for root in SOURCE_ROOTS:
        base = REPO_ROOT / root
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            parts = list(path.relative_to(base).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            if parts:
                names.append(".".join(parts))
    return names


MODULES = _module_names()


def test_the_walk_found_something() -> None:
    """A typo in SOURCE_ROOTS would silently make this whole file a no-op."""
    assert len(MODULES) >= 9


@pytest.mark.parametrize("name", MODULES)
def test_every_module_imports(name: str) -> None:
    importlib.import_module(name)


def test_source_roots_match_coverage_config() -> None:
    """Drift here reopens the hole this file exists to close."""
    with (REPO_ROOT / "pyproject.toml").open("rb") as f:
        configured = tomllib.load(f)["tool"]["coverage"]["run"]["source"]
    assert sorted(configured) == sorted(SOURCE_ROOTS)
