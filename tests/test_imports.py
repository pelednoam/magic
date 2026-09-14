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
import re
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
    "packages/coach/src",
    "packages/rules/src",
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


#: Where each distribution's manifest lives, by the name it publishes.
DISTRIBUTIONS: dict[str, str] = {
    "packages/core": "mtgcoach-core",
    "packages/carddata": "mtgcoach-carddata",
    "packages/coach": "mtgcoach-coach",
    "packages/rules": "mtgcoach-rules",
    "packages/vision": "mtgcoach-vision",
    "services/api": "mtgcoach-api",
}

#: Which distribution each namespace package belongs to.
OWNERS: dict[str, str] = {
    "core": "mtgcoach-core",
    "carddata": "mtgcoach-carddata",
    "coach": "mtgcoach-coach",
    "rules": "mtgcoach-rules",
    "vision": "mtgcoach-vision",
    "api": "mtgcoach-api",
}

IMPORTED = re.compile(r"^\s*from\s+mtgcoach\.(\w+)|^\s*import\s+mtgcoach\.(\w+)", re.MULTILINE)


def _imports_of(distribution: Path) -> set[str]:
    """Every sibling distribution this one imports from."""
    found: set[str] = set()
    for path in (distribution / "src").rglob("*.py"):
        for first, second in IMPORTED.findall(path.read_text(encoding="utf-8")):
            found.add(OWNERS[first or second])
    return found


def _declared_by(distribution: Path) -> set[str]:
    """Every ``mtgcoach-*`` this distribution's manifest declares."""
    with (distribution / "pyproject.toml").open("rb") as f:
        declared = tomllib.load(f)["project"]["dependencies"]
    return {name for name in declared if name.startswith("mtgcoach-")}


@pytest.mark.parametrize(("where", "name"), sorted(DISTRIBUTIONS.items()))
def test_every_cross_package_import_is_declared(where: str, name: str) -> None:
    """A workspace install hides this until somebody installs one package alone.

    `uv sync` puts every package on the path whatever the manifests say, so an
    undeclared dependency imports fine here and fails only for the person who
    installs the wheel. Two reviewers found `services/api` importing
    `mtgcoach.rules` without declaring it, on the same diff that added it.
    """
    distribution = REPO_ROOT / where
    missing = _imports_of(distribution) - _declared_by(distribution) - {name}
    assert missing == set(), f"{name} imports {sorted(missing)} without declaring them"
