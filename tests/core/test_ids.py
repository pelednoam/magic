"""The identifier NewTypes must stay mutually incompatible."""

from __future__ import annotations

from mtgcoach.core.ids import InstanceId, OracleId, PlayerId, SetCode


def _takes_oracle_id(value: OracleId) -> str:
    return value


def test_newtypes_are_distinct_to_the_type_checker() -> None:
    """Passing a PlayerId where an OracleId is expected must be a type error.

    This is a type-level regression test, not a runtime one. ``warn_unused_ignores``
    (implied by ``mypy --strict``) is what gives it teeth: if these ever degrade
    into plain ``str`` aliases, the ignore below becomes unnecessary and the type
    check fails. At runtime a NewType is the identity function, so the assertion
    only documents that.
    """
    player = PlayerId("me")
    assert _takes_oracle_id(player) == "me"  # type: ignore[arg-type]


def test_constructors_are_the_identity_at_runtime() -> None:
    assert OracleId("a") == "a"
    assert InstanceId("b") == "b"
    assert PlayerId("c") == "c"
    assert SetCode("FDN") == "FDN"
