"""Reading untyped JSON safely.

This is the boundary where a third-party document becomes typed data, so its
rejection paths matter as much as its happy ones: everything downstream trusts
that a value which arrived here as a string really is one.
"""

from __future__ import annotations

import pytest

from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    as_object,
    nullable_str,
    object_list,
    optional_str,
    require_float,
    require_str,
    string_set,
)


def test_require_str_returns_the_value() -> None:
    assert require_str({"name": "Abrade"}, "name", "card") == "Abrade"


@pytest.mark.parametrize("value", [None, 3, 3.5, True, ["a"], {"a": 1}])
def test_require_str_rejects_every_other_type(value: object) -> None:
    with pytest.raises(MalformedJsonError, match="should be a string"):
        require_str({"name": value}, "name", "card")  # type: ignore[dict-item]


def test_require_str_rejects_a_missing_key() -> None:
    with pytest.raises(MalformedJsonError, match="'name'"):
        require_str({}, "name", "card")


def test_the_error_names_the_card_and_the_field() -> None:
    with pytest.raises(MalformedJsonError, match="Abrade: 'cmc'"):
        require_float({}, "cmc", "Abrade")


@pytest.mark.parametrize(("value", "expected"), [(3, 3.0), (3.5, 3.5), (0, 0.0)])
def test_require_float_accepts_numbers(value: float, expected: float) -> None:
    assert require_float({"cmc": value}, "cmc", "card") == expected


def test_require_float_rejects_a_boolean() -> None:
    """Python says bool is an int; a boolean where a number belongs is bad data."""
    with pytest.raises(MalformedJsonError, match="should be a number"):
        require_float({"cmc": True}, "cmc", "card")


@pytest.mark.parametrize("value", [None, "3", ["3"], {}])
def test_require_float_rejects_non_numbers(value: object) -> None:
    with pytest.raises(MalformedJsonError, match="should be a number"):
        require_float({"cmc": value}, "cmc", "card")  # type: ignore[dict-item]


def test_optional_str_falls_back() -> None:
    assert optional_str({}, "mana_cost") == ""
    assert optional_str({"mana_cost": None}, "mana_cost") == ""
    assert optional_str({}, "layout", "normal") == "normal"
    assert optional_str({"layout": "transform"}, "layout", "normal") == "transform"


def test_nullable_str_distinguishes_absent_from_empty() -> None:
    """A card with no power is not a card whose power is the empty string."""
    assert nullable_str({}, "power") is None
    assert nullable_str({"power": None}, "power") is None
    assert nullable_str({"power": ""}, "power") == ""
    assert nullable_str({"power": "*"}, "power") == "*"


def test_string_set_filters_non_strings() -> None:
    assert string_set({"keywords": ["Flying", 3, None, "Haste"]}, "keywords") == {
        "Flying",
        "Haste",
    }


def test_string_set_on_absent_or_wrong_type() -> None:
    assert string_set({}, "keywords") == frozenset()
    assert string_set({"keywords": None}, "keywords") == frozenset()
    assert string_set({"keywords": "Flying"}, "keywords") == frozenset()


def test_object_list_keeps_only_objects() -> None:
    assert object_list({"card_faces": [{"a": 1}, "x", None]}, "card_faces") == ({"a": 1},)


def test_object_list_on_absent_or_wrong_type() -> None:
    assert object_list({}, "card_faces") == ()
    assert object_list({"card_faces": {}}, "card_faces") == ()


def test_as_object_accepts_a_string_keyed_dict() -> None:
    assert as_object({"a": 1}) == {"a": 1}
    assert as_object({}) == {}


def test_as_object_rejects_non_dicts() -> None:
    assert as_object([1, 2]) is None
    assert as_object("x") is None
    assert as_object(None) is None


def test_as_object_rejects_non_string_keys() -> None:
    """JSON cannot produce these, but json.loads is not the only caller."""
    assert as_object({1: "a"}) is None


def test_as_array_accepts_lists() -> None:
    assert as_array([1, "a"]) == [1, "a"]
    assert as_array([]) == []


def test_as_array_rejects_non_lists() -> None:
    assert as_array({"a": 1}) is None
    assert as_array("abc") is None
    assert as_array(None) is None
