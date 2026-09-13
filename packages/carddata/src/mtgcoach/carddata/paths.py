"""On-disk layout for per-set data.

Every set contributes the same four artifacts, so adding a set is a data
operation. ``manifest.json`` is registered with the review agent's signed
manifest audit, which is what catches an ``effects.json`` drifting out of sync
with the set it claims to describe.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.ids import SetCode

#: Scryfall set codes are three to six uppercase alphanumerics. Validating
#: against this before joining a path is what stops a hostile or malformed set
#: code from escaping the data directory.
_SET_CODE_PATTERN: Final = re.compile(r"\A[A-Z0-9]{3,6}\Z")


def validate_set_code(set_code: SetCode) -> None:
    """Raise ``ValueError`` unless ``set_code`` is a well-formed set code.

    Args:
        set_code: The candidate code, e.g. ``FDN``.

    Raises:
        ValueError: If the code is not three to six uppercase alphanumerics.
    """
    if not _SET_CODE_PATTERN.match(set_code):
        msg = f"not a well-formed set code: {set_code!r}"
        raise ValueError(msg)


def set_dir(data_root: Path, set_code: SetCode) -> Path:
    """Return the directory holding every artifact for one set."""
    validate_set_code(set_code)
    return data_root / "sets" / set_code


def effects_path(data_root: Path, set_code: SetCode) -> Path:
    """Return the path of a set's reviewed, sealed effect fixture."""
    return set_dir(data_root, set_code) / "effects.json"


def manifest_path(data_root: Path, set_code: SetCode) -> Path:
    """Return the path of a set's signed manifest."""
    return set_dir(data_root, set_code) / "manifest.json"


def decks_dir(data_root: Path, set_code: SetCode) -> Path:
    """Return the directory holding a set's precon decklists."""
    return set_dir(data_root, set_code) / "decks"
