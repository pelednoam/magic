"""Reading untyped JSON without reaching for ``Any``.

``disallow_any_explicit`` is on, so there is no blanket escape from the shape of
a third-party document -- and that turns out to be the right constraint rather
than an obstacle. Each accessor states the type it needs and fails loudly when
the document disagrees, so a malformed bulk file is reported at the offending
card instead of surfacing later as an attribute error on something that should
have been a string.
"""

from __future__ import annotations

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
    return float(value)


def optional_str(obj: JsonObject, key: str, default: str = "") -> str:
    """Return a string field, or ``default`` when absent or null."""
    value = obj.get(key)
    return value if isinstance(value, str) else default


def nullable_str(obj: JsonObject, key: str) -> str | None:
    """Return a string field, or None when absent or null.

    Distinct from ``optional_str`` because absence is meaningful: a card with no
    power is not a card with an empty power.
    """
    value = obj.get(key)
    return value if isinstance(value, str) else None


def string_set(obj: JsonObject, key: str) -> frozenset[str]:
    """Return a list-of-strings field as a set, empty when absent or null."""
    value = obj.get(key)
    if not isinstance(value, list):
        return frozenset()
    return frozenset(item for item in value if isinstance(item, str))


def object_list(obj: JsonObject, key: str) -> tuple[JsonObject, ...]:
    """Return a list-of-objects field, empty when absent or null."""
    value = obj.get(key)
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


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
