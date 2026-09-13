"""Auditing the coverage claim a manifest signs."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata import manifest as manifest_mod
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from pathlib import Path

FDN = SetCode("FDN")


def _fixture(tmp_path: Path, cards: int = 2, unmodelled: int = 1) -> Path:
    """A fixture where the first ``unmodelled`` cards carry an unmodelled ability."""
    path = tmp_path / "effects.json"
    rows: list[object] = [
        {
            "name": f"c{i}",
            "abilities": (
                [{"kind": "unmodeled", "text": "t", "reason": "r"}]
                if i < unmodelled
                else [{"kind": "spell", "effects": []}]
            ),
        }
        for i in range(cards)
    ]
    path.write_text(json.dumps({"cards": rows}), encoding="utf-8")
    return path


def test_an_overstated_coverage_claim_is_caught(tmp_path: Path) -> None:
    """A signed field nobody audits is decoration.

    The shipped manifest claimed 91 of 124 modelled while the fixture held 65,
    and `check` passed.
    """
    effects = _fixture(tmp_path, cards=4, unmodelled=2)
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=4,
        modelled_count=4,
        sha256=manifest_mod.sha256_of(effects),
    )
    problems = manifest_mod.verify(effects, record)
    assert any("file holds 2 modelled cards, manifest says 4" in p for p in problems)


def test_an_unmodelled_effect_inside_an_ability_counts(tmp_path: Path) -> None:
    """The blocking finding: nesting hid 26 cards from the coverage number."""
    effects = tmp_path / "effects.json"
    effects.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "name": "nested",
                        "abilities": [
                            {
                                "kind": "spell",
                                "effects": [{"kind": "unmodeled", "text": "t", "reason": "r"}],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=1,
        modelled_count=1,
        sha256=manifest_mod.sha256_of(effects),
    )
    assert any("0 modelled cards" in p for p in manifest_mod.verify(effects, record))


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


def test_a_card_that_is_not_an_object_is_skipped(tmp_path: Path) -> None:
    """A malformed row must not crash the audit, nor count as modelled."""
    effects = tmp_path / "effects.json"
    effects.write_text(json.dumps({"cards": ["not a card", 42]}), encoding="utf-8")
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=2,
        modelled_count=0,
        sha256=manifest_mod.sha256_of(effects),
    )
    assert manifest_mod.verify(effects, record) == ()


def test_an_ability_that_is_not_an_object_is_not_unmodelled(tmp_path: Path) -> None:
    """A malformed ability row is skipped, not silently treated as a gap."""
    effects = tmp_path / "effects.json"
    effects.write_text(
        json.dumps({"cards": [{"name": "odd", "abilities": ["not an ability"]}]}),
        encoding="utf-8",
    )
    record = manifest_mod.Manifest(
        set_code=FDN,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=1,
        modelled_count=1,
        sha256=manifest_mod.sha256_of(effects),
    )
    assert manifest_mod.verify(effects, record) == ()
