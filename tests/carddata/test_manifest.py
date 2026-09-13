"""The signed record of a sealed set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata import manifest as manifest_mod
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from pathlib import Path

FDN = SetCode("FDN")


def _fixture(tmp_path: Path, cards: int = 2) -> Path:
    path = tmp_path / "effects.json"
    path.write_text(
        json.dumps({"cards": [{"name": f"c{i}"} for i in range(cards)]}),
        encoding="utf-8",
    )
    return path


def _manifest(path: Path, cards: int = 2, modelled: int = 1) -> manifest_mod.Manifest:
    return manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=cards,
        modelled_count=modelled,
        sha256=manifest_mod.sha256_of(path),
    )


def test_a_manifest_round_trips(tmp_path: Path) -> None:
    effects = _fixture(tmp_path)
    record = _manifest(effects)
    path = tmp_path / "manifest.json"
    manifest_mod.write(path, record)
    assert manifest_mod.read(path) == record


def test_coverage_is_derived_not_stored(tmp_path: Path) -> None:
    record = _manifest(_fixture(tmp_path, 4), cards=4, modelled=3)
    assert record.coverage == 0.75


def test_coverage_of_an_empty_set_is_zero(tmp_path: Path) -> None:
    record = _manifest(_fixture(tmp_path, 0), cards=0, modelled=0)
    assert record.coverage == 0.0


def test_a_matching_fixture_has_no_problems(tmp_path: Path) -> None:
    effects = _fixture(tmp_path)
    assert manifest_mod.verify(effects, _manifest(effects)) == ()


def test_a_changed_file_is_caught(tmp_path: Path) -> None:
    """The whole point: bytes that moved after sealing."""
    effects = _fixture(tmp_path)
    record = _manifest(effects)
    effects.write_text(
        json.dumps({"cards": [{"name": "c0"}, {"name": "tampered"}]}), encoding="utf-8"
    )
    problems = manifest_mod.verify(effects, record)
    assert any("checksum mismatch" in p for p in problems)


def test_a_card_count_that_drifted_is_caught(tmp_path: Path) -> None:
    """The 782-vs-662 failure, in miniature."""
    effects = _fixture(tmp_path, cards=3)
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=99,
        modelled_count=1,
        sha256=manifest_mod.sha256_of(effects),
    )
    problems = manifest_mod.verify(effects, record)
    assert any("file holds 3 cards, manifest says 99" in p for p in problems)


def test_an_older_schema_version_is_caught(tmp_path: Path) -> None:
    """A fixture sealed under an older schema may decode to a different meaning."""
    effects = _fixture(tmp_path)
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION - 1,
        card_count=2,
        modelled_count=1,
        sha256=manifest_mod.sha256_of(effects),
    )
    assert any("schema version" in p for p in manifest_mod.verify(effects, record))


def test_a_missing_fixture_is_caught(tmp_path: Path) -> None:
    effects = _fixture(tmp_path)
    record = _manifest(effects)
    effects.unlink()
    assert manifest_mod.verify(effects, record) == ("effects.json is missing",)


def test_a_fixture_without_a_cards_list_counts_zero(tmp_path: Path) -> None:
    effects = tmp_path / "effects.json"
    effects.write_text(json.dumps({"cards": "lots"}), encoding="utf-8")
    record = _manifest(effects, cards=2)
    assert any("file holds 0 cards" in p for p in manifest_mod.verify(effects, record))


@pytest.mark.parametrize("field", ["schema_version", "card_count", "modelled_count"])
def test_a_bad_count_field_is_rejected(field: str, tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    body = {
        "set_code": "FDN",
        "schema_version": 1,
        "card_count": 2,
        "modelled_count": 1,
        "sha256": "abc",
    }
    body[field] = -1
    path.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="non-negative integer"):
        manifest_mod.read(path)


def test_the_checksum_reads_a_file_in_chunks(tmp_path: Path) -> None:
    """Large fixtures must not need to be held in memory to be checksummed."""
    path = tmp_path / "big.bin"
    payload = b"x" * (1 << 18)
    path.write_bytes(payload)
    assert manifest_mod.sha256_of(path) == hashlib.sha256(payload).hexdigest()
