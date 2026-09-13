"""Reading untyped JSON safely.

This is the boundary where a third-party document becomes typed data, so its
rejection paths matter as much as its happy ones: everything downstream trusts
that a value which arrived here as a string really is one.
"""

from __future__ import annotations

import json

import pytest

from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    as_object,
    nullable_str,
    object_list,
    optional_str,
    require_float,
    require_object,
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


def test_string_set_reads_a_list_of_strings() -> None:
    assert string_set({"keywords": ["Flying", "Haste"]}, "keywords") == {
        "Flying",
        "Haste",
    }


def test_string_set_treats_absent_and_null_as_empty() -> None:
    assert string_set({}, "keywords") == frozenset()
    assert string_set({"keywords": None}, "keywords") == frozenset()


def test_string_set_rejects_a_mixed_list() -> None:
    """Dropping the odd element would mean a card quietly losing a keyword."""
    with pytest.raises(MalformedJsonError, match="a list of strings"):
        string_set({"keywords": ["Flying", 3]}, "keywords")


def test_string_set_rejects_a_non_list() -> None:
    with pytest.raises(MalformedJsonError, match="a list of strings"):
        string_set({"keywords": "Flying"}, "keywords")


def test_object_list_reads_a_list_of_objects() -> None:
    assert object_list({"card_faces": [{"a": 1}, {"b": 2}]}, "card_faces") == (
        {"a": 1},
        {"b": 2},
    )


def test_object_list_treats_absent_and_null_as_empty() -> None:
    assert object_list({}, "card_faces") == ()
    assert object_list({"card_faces": None}, "card_faces") == ()


def test_object_list_rejects_a_list_containing_a_non_object() -> None:
    """A dropped entry here would be a card silently losing a face."""
    with pytest.raises(MalformedJsonError, match="a list of objects"):
        object_list({"card_faces": [{"a": 1}, "x"]}, "card_faces")


def test_object_list_rejects_a_non_list() -> None:
    with pytest.raises(MalformedJsonError, match="a list of objects"):
        object_list({"card_faces": {}}, "card_faces")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_require_float_rejects_non_finite_numbers(bad: str) -> None:
    """json.loads accepts these as bare literals, so a document can carry them."""
    with pytest.raises(MalformedJsonError, match="a finite number"):
        require_float({"cmc": json.loads(bad)}, "cmc", "Card")


@pytest.mark.parametrize("value", [3, None, ["x"]])
def test_optional_and_nullable_reject_wrong_types(value: object) -> None:
    if value is not None:
        with pytest.raises(MalformedJsonError, match="a string"):
            optional_str({"oracle_text": value}, "oracle_text")  # type: ignore[dict-item]
        with pytest.raises(MalformedJsonError, match="a string"):
            nullable_str({"power": value}, "power")  # type: ignore[dict-item]


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


def test_require_object_narrows_a_dict() -> None:
    assert require_object({"a": 1}, "doc") == {"a": 1}


@pytest.mark.parametrize("value", [[1], "x", 3, None])
def test_require_object_rejects_everything_else(value: object) -> None:
    with pytest.raises(MalformedJsonError, match="should be an object"):
        require_object(value, "doc")
