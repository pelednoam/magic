"""Taking the fields out of a model's reply, at two different strictnesses.

The difference is what happens to the field afterwards, and it is the whole
point of having two:

- **Prose** is read leniently. Nothing is checked against ``because`` or
  ``watch_out``, so a malformed one costs a sentence, and dropping it is better
  than turning a usable answer into an error.
- **Identifiers** are read strictly, all or nothing. ``play``, ``attack`` and
  ``citations`` are compared against the engine or against the retrieved rules,
  so trimming a bad element out of one does not lose information -- it changes
  the claim, and changes it towards passing. ``["bear-1", 7]`` trimmed to
  ``["bear-1"]`` is a *different attack*, one the engine did cost, and the
  checker then agrees with a recommendation nobody made.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from collections.abc import Mapping


def prose(payload: Mapping[str, object], field: str) -> str:
    """A string of prose, empty when it is missing, the wrong type, or blank.

    For fields nothing is checked against: ``because``, ``in_short``,
    ``answer``, ``unsure``. Use ``one`` for anything a checker will compare
    against the engine.

    Stripped, so that a field holding a space is empty rather than substantive.
    The "did it say anything at all" checks downstream are truthiness tests,
    and ``" "`` passed them while putting a blank line on the screen.
    """
    value = payload.get(field)
    return value.strip() if isinstance(value, str) else ""


def one(payload: Mapping[str, object], field: str) -> str:
    """A single identifier, or empty when the field is absent.

    ``play`` is the only one, and it needs the same treatment as ``attack``:
    empty means "play nothing", which is a real recommendation, so quietly
    turning a malformed value into empty does not lose information -- it
    substitutes a different recommendation, and one that always passes.

    An explicit ``null`` is off-schema: the schema asks for a string, and the
    two were indistinguishable through ``.get``, which turned a malformed reply
    into a do-nothing recommendation that passes.

    A *missing* key is refused outright -- ``play`` is the only caller and the
    prompt demands it. See ``_missing``.

    Raises:
        MalformedFieldError: If the field is absent, or is not a string.
    """
    if field not in payload:
        raise _missing(field, "an identifier")
    value = payload[field]
    if not isinstance(value, str):
        raise MalformedFieldError(field, value, "an identifier")
    return value


def words(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    """A list of prose, keeping only the strings.

    For fields nothing is checked against: ``watch_out``, ``check_yourself``. A
    missing or malformed one is empty rather than an error, because a dropped
    sentence costs a sentence. Use ``exactly`` for anything a checker will then
    compare against the engine.
    """
    value = payload.get(field)
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", value)
    return tuple(item for item in items if isinstance(item, str) and item)


def exactly(
    payload: Mapping[str, object], field: str, *, required: bool = False
) -> tuple[str, ...]:
    """A list of identifiers, all of them or none.

    For the fields a checker compares against the engine: ``attack``,
    ``citations``. Dropping a bad element from one of those does not lose a
    sentence, it changes the claim -- and changes it towards passing. An
    ``attack`` of ``["bear-1", 7]`` trimmed to ``["bear-1"]`` becomes a
    *different attack*, one the engine did cost, and the checker then agrees
    with a recommendation nobody made. Citations behave the same way in
    reverse: drop the invented one and what is left is all real.

    So a malformed element fails the whole field. The caller turns that into an
    ``ExplainerError`` and the player gets the engine's own panel, which is
    what they would have got from a refused answer anyway.

    An explicit ``null`` is off-schema, for the same reason as ``one``.
    ``required`` is for ``attack``, which the prompt demands; ``citations`` is
    absent-tolerant. See ``_missing``.

    Raises:
        MalformedFieldError: If the field is present and is not a list of
            non-empty strings, or is absent and ``required``.
    """
    if field not in payload:
        if required:
            raise _missing(field, "a list of identifiers")
        return ()
    value = payload[field]
    if not isinstance(value, list):
        raise MalformedFieldError(field, value, "a list of identifiers")
    items = cast("list[object]", value)
    if not all(isinstance(item, str) and item for item in items):
        raise MalformedFieldError(field, items, "a list of identifiers")
    return tuple(cast("list[str]", items))


def _missing(field: str, wanted: str) -> MalformedFieldError:
    """The error for a field the prompt demanded and the reply did not carry.

    Absent is not the same as "do nothing", and reading it that way put the
    server's own word behind a choice the model never made. ``{"because":
    "Wait."}`` in combat became an explicit empty ``attack``, which matches the
    engine whenever holding back is the right play -- so it came out
    ``trusted``, and the screen said "do not attack this turn" in the coach's
    voice. The prompt asks for both keys, so a reply without one is malformed
    in shape rather than modest in content.

    Only for ``play`` and ``attack``. ``citations`` is absent-tolerant on
    purpose: an answer with none is refused downstream for being uncited, which
    is already the safe direction.

    Returned rather than raised so the two call sites read as refusals of their
    own, and so ``exactly`` can decide whether this is one.
    """
    return MalformedFieldError(field, "<no such key>", wanted)


class MalformedFieldError(ExplainerError):
    """A field a checker would have compared against the engine is not usable."""

    def __init__(self, field: str, value: object, wanted: str) -> None:
        """Name the field, what it should have been, and what arrived."""
        super().__init__(f"the coach's {field!r} was not {wanted}: {value!r:.80}")
