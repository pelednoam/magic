"""Reading untyped JSON without reaching for ``Any``.

``disallow_any_explicit`` is on, so there is no blanket escape from the shape of
a third-party document -- and that turns out to be the right constraint rather
than an obstacle. Each accessor states the type it needs and fails loudly when
the document disagrees, so a malformed bulk file is reported at the offending
card instead of surfacing later as an attribute error on something that should
have been a string.
"""

from __future__ import annotations

import math
from typing import cast

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type JsonObject = dict[str, JsonValue]


class MalformedJsonError(ValueError):
    """A JSON document that does not have the shape we need."""


def _fail(context: str, key: str, wanted: str, got: object) -> MalformedJsonError:
    return MalformedJsonError(f"{context}: {key!r} should be {wanted}, got {type(got).__name__}")


def require_str(obj: JsonObject, key: str, context: str) -> str:
    """Return a string field that must be present.

    Raises:
        MalformedJsonError: If the key is missing or is not a string.
    """
    value = obj.get(key)
    if not isinstance(value, str):
        raise _fail(context, key, "a string", value)
    return value


def require_float(obj: JsonObject, key: str, context: str) -> float:
    """Return a numeric field that must be present.

    Raises:
        MalformedJsonError: If the key is missing or is not a number. ``bool`` is
            rejected although Python counts it as an ``int``: a boolean where a
            number belongs is a malformed document, not a zero.
    """
    value = obj.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _fail(context, key, "a number", value)
    # json.loads accepts NaN and Infinity as bare literals, so a document really
    # can carry them. A non-finite converted mana cost would poison every
    # comparison it reaches, silently, the way NaN always does.
    if not math.isfinite(value):
        raise _fail(context, key, "a finite number", value)
    return float(value)


def optional_str(obj: JsonObject, key: str, default: str = "", context: str = "field") -> str:
    """Return a string field, or ``default`` when absent or null.

    Raises:
        MalformedJsonError: If present with the wrong type. Absent and wrong are
            different problems: absent is normal and has a sensible default,
            while a number where oracle text belongs means the document is not
            what we think it is, and quietly substituting "" would drop rules
            text that a coach would then reason without.
    """
    value = obj.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise _fail(context, key, "a string", value)
    return value


def nullable_str(obj: JsonObject, key: str, context: str = "field") -> str | None:
    """Return a string field, or None when absent or null.

    Distinct from ``optional_str`` because absence is meaningful: a card with no
    power is not a card with an empty power.

    Raises:
        MalformedJsonError: If present with the wrong type.
    """
    value = obj.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _fail(context, key, "a string", value)
    return value


def string_set(obj: JsonObject, key: str, context: str = "field") -> frozenset[str]:
    """Return a list-of-strings field as a set, empty when absent or null.

    Raises:
        MalformedJsonError: If present but not a list of strings. Dropping the
            odd element would mean a card quietly losing a keyword.
    """
    value = obj.get(key)
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise _fail(context, key, "a list of strings", value)
    items = cast("list[object]", value)
    if not all(isinstance(item, str) for item in items):
        raise _fail(context, key, "a list of strings", value)
    return frozenset(item for item in items if isinstance(item, str))


def object_list(obj: JsonObject, key: str, context: str = "field") -> tuple[JsonObject, ...]:
    """Return a list-of-objects field, empty when absent or null.

    Raises:
        MalformedJsonError: If present but not a list of objects. A dropped
            entry here would be a card silently losing a face.
    """
    value = obj.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _fail(context, key, "a list of objects", value)
    items = cast("list[object]", value)
    faces = tuple(as_object(item) for item in items)
    if any(face is None for face in faces):
        raise _fail(context, key, "a list of objects", value)
    return tuple(face for face in faces if face is not None)


def as_object(value: object) -> JsonObject | None:
    """Narrow a value decoded by ``json.loads`` to a JSON object, or None.

    ``json.loads`` is typed as returning ``Any``, which would silently spread
    through every caller. Assigning it to ``object`` and narrowing here confines
    the one unavoidable cast to a single checked place: the keys really are
    verified to be strings before the cast is made.
    """
    if not isinstance(value, dict):
        return None
    if not all(isinstance(key, str) for key in value):  # pyright: ignore[reportUnknownVariableType]
        return None
    return cast("JsonObject", value)


def as_array(value: object) -> list[object] | None:
    """Narrow a value decoded by ``json.loads`` to a list, or None.

    The companion to ``as_object``. Narrowing ``object`` with ``isinstance(...,
    list)`` yields ``list[Unknown]``, whose elements poison every downstream
    signature; every list really is a list of objects, so the cast is sound and
    made once here rather than at each call site.
    """
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def require_object(value: object, context: str) -> JsonObject:
    """Narrow a decoded value to a JSON object, or fail saying what it was."""
    obj = as_object(value)
    if obj is None:
        raise _fail(context, "document", "an object", value)
    return obj
