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
    as_object,
    optional_str,
    require_object,
    require_str,
)
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.carddata.jsondata import JsonObject, JsonValue

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
    model: str = ""

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
                "model": manifest.model,
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
        model=optional_str(obj, "model"),
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
    try:
        parsed = json.loads(effects_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # A corrupt fixture is exactly what `check` exists to find, so it is a
        # problem to report, not an exception to escape through it.
        problems.append(f"{effects_path.name} is not readable JSON: {exc}")
        return tuple(problems)

    obj = require_object(parsed, effects_path.name)
    cards = obj.get("cards")
    if not isinstance(cards, list):
        problems.append(f"{effects_path.name} has no 'cards' list")
        return tuple(problems)
    if len(cards) != manifest.card_count:
        problems.append(f"file holds {len(cards)} cards, manifest says {manifest.card_count}")
    problems.extend(_modelled_problems(cards, manifest))
    return tuple(problems)


def _modelled_problems(cards: list[JsonValue], manifest: Manifest) -> list[str]:
    """Audit the coverage claim, not just the card count.

    ``modelled_count`` is signed like every other field, and an unaudited signed
    field is decoration: a manifest claiming 91 of 124 passed `check` while the
    fixture actually held 65.
    """
    modelled = sum(
        1
        for card in cards
        if (obj := as_object(card)) is not None
        and not any(_is_unmodelled(row) for row in _rows(obj, "abilities"))
    )
    if modelled != manifest.modelled_count:
        return [f"file holds {modelled} modelled cards, manifest says {manifest.modelled_count}"]
    return []


def _rows(obj: JsonObject, key: str) -> list[JsonValue]:
    value = obj.get(key)
    return value if isinstance(value, list) else []


def _is_unmodelled(row: JsonValue) -> bool:
    """Whether an ability is unmodelled, at its own level or inside its effects."""
    obj = as_object(row)
    if obj is None:
        return False
    if obj.get("kind") == "unmodeled":
        return True
    return any(
        (inner := as_object(e)) is not None and inner.get("kind") == "unmodeled"
        for e in _rows(obj, "effects")
    )
