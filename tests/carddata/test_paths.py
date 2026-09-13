"""Per-set data layout, and the validation that keeps set codes inside it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.paths import (
    decks_dir,
    effects_path,
    manifest_path,
    set_dir,
    validate_set_code,
)
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from pathlib import Path

VALID = ["FDN", "BLB", "LTR", "M21", "ABCDEF", "30A"]

INVALID = [
    "fdn",  # lowercase
    "FD",  # too short
    "ABCDEFG",  # too long
    "",  # empty
    "../FDN",  # traversal
    "FDN/..",  # traversal
    "FD N",  # whitespace
    "FDN\n",  # trailing newline: \A..\Z rather than ^..$ is what rejects this
]


@pytest.mark.parametrize("code", VALID)
def test_valid_set_codes_are_accepted(code: str) -> None:
    validate_set_code(SetCode(code))


@pytest.mark.parametrize("code", INVALID)
def test_invalid_set_codes_are_rejected(code: str) -> None:
    with pytest.raises(ValueError, match="not a well-formed set code"):
        validate_set_code(SetCode(code))


def test_set_dir_layout(tmp_path: Path) -> None:
    assert set_dir(tmp_path, SetCode("FDN")) == tmp_path / "sets" / "FDN"


def test_artifact_paths(tmp_path: Path) -> None:
    base = tmp_path / "sets" / "FDN"
    assert effects_path(tmp_path, SetCode("FDN")) == base / "effects.json"
    assert manifest_path(tmp_path, SetCode("FDN")) == base / "manifest.json"
    assert decks_dir(tmp_path, SetCode("FDN")) == base / "decks"


@pytest.mark.parametrize("builder", [set_dir, effects_path, manifest_path, decks_dir])
def test_every_path_builder_validates(builder: object, tmp_path: Path) -> None:
    """No path builder may skip validation -- one that did would be the escape."""
    assert callable(builder)
    with pytest.raises(ValueError, match="not a well-formed set code"):
        builder(tmp_path, SetCode("../etc"))
