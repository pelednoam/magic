"""Reading a JSON response the way a client would, with the types checked.

``views.Json`` is a recursive union, which is the honest type for "a value that
came back as JSON" and completely unusable for walking a response: every index
has to prove the thing it indexed was a mapping, and written out in each test
that proof buries the assertion.

So this narrows once, loudly. Every accessor says what it expects and fails with
the path it was walking when the shape was wrong -- which makes it a check on
the wire format as much as a convenience, and means a route that starts
returning a list where a test expects an object says so in one line.

The casts are real narrowing, not shrugs: ``isinstance`` has just established
the container, and JSON guarantees its keys are strings. What it cannot
establish is the element type, which is exactly what each accessor then checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class WireError(AssertionError):
    """The response was not shaped the way the test expected."""


def _where(path: Sequence[str]) -> str:
    """The path walked so far, for an error a reader can act on."""
    return ".".join(path) or "<root>"


def at(body: Mapping[str, object], *path: str) -> object:
    """The value at a path of keys, or an error naming where it stopped."""
    here: object = body
    walked: list[str] = []
    for key in path:
        step = _object_at(here, walked)
        if key not in step:
            msg = f"{_where([*walked, key])} is missing"
            raise WireError(msg)
        here = step[key]
        walked.append(key)
    return here


def _object_at(value: object, walked: Sequence[str]) -> dict[str, object]:
    """``value`` as an object, or an error saying what was found instead."""
    if not isinstance(value, dict):
        msg = f"{_where(walked)} is {type(value).__name__}, not an object"
        raise WireError(msg)
    return cast("dict[str, object]", value)


def decoded(value: object) -> dict[str, object]:
    """One decoded response body, checked to be a JSON object.

    The entry point: every helper below takes a mapping, and this is what turns
    ``response.json()`` -- which is ``Any`` however it is annotated -- into one.
    """
    if not isinstance(value, dict):
        msg = f"the response is {type(value).__name__}, not an object"
        raise WireError(msg)
    return cast("dict[str, object]", value)


def obj(body: Mapping[str, object], *path: str) -> dict[str, object]:
    """The object at a path."""
    value = at(body, *path)
    if not isinstance(value, dict):
        msg = f"{_where(path)} is {type(value).__name__}, not an object"
        raise WireError(msg)
    return cast("dict[str, object]", value)


def items(body: Mapping[str, object], *path: str) -> list[object]:
    """The list at a path, without saying yet what is in it."""
    value = at(body, *path)
    if not isinstance(value, list):
        msg = f"{_where(path)} is {type(value).__name__}, not a list"
        raise WireError(msg)
    return cast("list[object]", value)


def rows(body: Mapping[str, object], *path: str) -> list[dict[str, object]]:
    """A list of objects at a path -- a zone, a hand, a list of plans."""
    found: list[dict[str, object]] = []
    for index, row in enumerate(items(body, *path)):
        if not isinstance(row, dict):
            msg = f"{_where(path)}[{index}] is {type(row).__name__}, not an object"
            raise WireError(msg)
        found.append(cast("dict[str, object]", row))
    return found


def words(body: Mapping[str, object], *path: str) -> list[str]:
    """A list of strings at a path -- reasons, names, attackers."""
    found: list[str] = []
    for index, item in enumerate(items(body, *path)):
        if not isinstance(item, str):
            msg = f"{_where(path)}[{index}] is {type(item).__name__}, not a string"
            raise WireError(msg)
        found.append(item)
    return found


def text(body: Mapping[str, object], *path: str) -> str:
    """A string at a path."""
    value = at(body, *path)
    if not isinstance(value, str):
        msg = f"{_where(path)} is {type(value).__name__}, not a string"
        raise WireError(msg)
    return value


def number(body: Mapping[str, object], *path: str) -> int:
    """A whole number at a path. ``bool`` is not one, here as anywhere."""
    value = at(body, *path)
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{_where(path)} is {type(value).__name__}, not a number"
        raise WireError(msg)
    return value


def flag(body: Mapping[str, object], *path: str) -> bool:
    """A boolean at a path."""
    value = at(body, *path)
    if not isinstance(value, bool):
        msg = f"{_where(path)} is {type(value).__name__}, not a boolean"
        raise WireError(msg)
    return value


def named(entries: Sequence[Mapping[str, object]], name: str) -> dict[str, object]:
    """The one entry with this name, or an error listing what was there."""
    for entry in entries:
        if entry.get("name") == name:
            return dict(entry)
    found = ", ".join(sorted({str(e.get("name")) for e in entries})) or "nothing"
    msg = f"no {name!r} here; found {found}"
    raise WireError(msg)


def by_name(entries: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """Entries keyed by their name, for the tests that want several at once."""
    return {str(entry["name"]): dict(entry) for entry in entries}
