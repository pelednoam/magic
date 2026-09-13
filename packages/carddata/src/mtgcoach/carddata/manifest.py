"""The signed record of what a sealed set contains.

A fixture and a manifest that disagree is the failure this exists to catch: the
effects file says 124 cards, the set has 130, and nothing notices until a coach
reasons about a card whose behaviour was never extracted. The manifest records
the count and a checksum of the exact bytes, and the review agent's preflight
audits it on every change.

The checksum is over the file as written, so the encoder's sorted output is not
cosmetic -- a fixture whose bytes moved for no reason could not be checksummed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    require_object,
    require_str,
)
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.carddata.jsondata import JsonObject

#: Bumped when the effect or ability schema changes shape. A fixture sealed
#: under an older version cannot be trusted to decode into the same meaning.
SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Manifest:
    """What was sealed, and proof of exactly which bytes."""

    set_code: SetCode
    schema_version: int
    card_count: int
    modelled_count: int
    sha256: str

    @property
    def coverage(self) -> float:
        """Share of cards with no unmodelled ability."""
        if self.card_count == 0:
            return 0.0
        return self.modelled_count / self.card_count


def sha256_of(path: Path) -> str:
    """Checksum a file in chunks, so a large fixture needs no more memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write(path: Path, manifest: Manifest) -> None:
    """Write a manifest as JSON."""
    path.write_text(
        json.dumps(
            {
                "set_code": manifest.set_code,
                "schema_version": manifest.schema_version,
                "card_count": manifest.card_count,
                "modelled_count": manifest.modelled_count,
                "sha256": manifest.sha256,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def read(path: Path) -> Manifest:
    """Read a manifest.

    Raises:
        MalformedJsonError: If a field is missing or has the wrong type.
    """
    obj = require_object(json.loads(path.read_text(encoding="utf-8")), path.name)
    return Manifest(
        set_code=SetCode(require_str(obj, "set_code", path.name)),
        schema_version=_count(obj, "schema_version", path.name),
        card_count=_count(obj, "card_count", path.name),
        modelled_count=_count(obj, "modelled_count", path.name),
        sha256=require_str(obj, "sha256", path.name),
    )


def _count(obj: JsonObject, key: str, context: str) -> int:
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{context}: {key!r} must be a non-negative integer, got {value!r}"
        raise MalformedJsonError(msg)
    return value


def verify(effects_path: Path, manifest: Manifest) -> tuple[str, ...]:
    """Return the ways a fixture and its manifest disagree, empty when they do not."""
    problems: list[str] = []
    if not effects_path.exists():
        return (f"{effects_path.name} is missing",)
    actual = sha256_of(effects_path)
    if actual != manifest.sha256:
        problems.append(
            f"checksum mismatch: file is {actual[:12]}, manifest says {manifest.sha256[:12]}"
        )
    if manifest.schema_version != SCHEMA_VERSION:
        problems.append(
            f"sealed under schema version {manifest.schema_version}, "
            f"this build expects {SCHEMA_VERSION}"
        )
    obj = require_object(json.loads(effects_path.read_text(encoding="utf-8")), effects_path.name)
    cards = obj.get("cards")
    count = len(cards) if isinstance(cards, list) else 0
    if count != manifest.card_count:
        problems.append(f"file holds {count} cards, manifest says {manifest.card_count}")
    return tuple(problems)
