"""Streaming objects out of a large JSON file."""

from __future__ import annotations

import json
from pathlib import Path

from mtgcoach.carddata.jsondata import as_array
from mtgcoach.carddata.jsonstream import CHUNK, stream_objects

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"


def _sample() -> list[object]:
    parsed: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = as_array(parsed)
    assert items is not None
    return items


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "doc.json"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_pretty_printed_array(tmp_path: Path) -> None:
    """The shape Scryfall's bulk download actually ships."""
    path = _write(tmp_path, json.dumps(_sample(), indent=2))
    assert len(list(stream_objects(path))) == len(_sample())


def test_one_object_per_line(tmp_path: Path) -> None:
    path = _write(tmp_path, "\n".join(json.dumps(o) for o in _sample()))
    assert len(list(stream_objects(path))) == len(_sample())


def test_an_array_with_one_object_per_line(tmp_path: Path) -> None:
    body = ",\n".join(json.dumps(o) for o in _sample())
    path = _write(tmp_path, f"[\n{body}\n]\n")
    assert len(list(stream_objects(path))) == len(_sample())


def test_a_bare_object(tmp_path: Path) -> None:
    path = _write(tmp_path, json.dumps(_sample()[0]))
    assert len(list(stream_objects(path))) == 1


def test_a_byte_order_mark_is_consumed(tmp_path: Path) -> None:
    path = _write(tmp_path, "﻿" + json.dumps(_sample()))
    assert len(list(stream_objects(path))) == len(_sample())


def test_an_empty_file(tmp_path: Path) -> None:
    assert list(stream_objects(_write(tmp_path, "  \n\n"))) == []


def test_top_level_scalars_are_skipped(tmp_path: Path) -> None:
    path = _write(tmp_path, '42\n"a string"\nnull\n' + json.dumps(_sample()[0]))
    assert len(list(stream_objects(path))) == 1


def test_braces_inside_strings_do_not_end_an_object(tmp_path: Path) -> None:
    """Every mana symbol is a brace, and oracle text is full of them."""
    card = {"name": "X", "oracle_text": "Add {1}{B}. {T}: draw a card. }{{"}
    path = _write(tmp_path, json.dumps([card]))
    objects = list(stream_objects(path))
    assert len(objects) == 1
    assert objects[0]["oracle_text"] == card["oracle_text"]


def test_escaped_quotes_inside_strings(tmp_path: Path) -> None:
    card = {"name": 'He said "{G}" and \\ left'}
    path = _write(tmp_path, json.dumps([card]))
    objects = list(stream_objects(path))
    assert len(objects) == 1
    assert objects[0]["name"] == card["name"]


def test_nested_objects_do_not_end_early(tmp_path: Path) -> None:
    card = {"name": "X", "image_uris": {"small": "a", "nested": {"deep": "b"}}}
    path = _write(tmp_path, json.dumps([card]))
    assert list(stream_objects(path)) == [card]


def test_objects_spanning_a_chunk_boundary(tmp_path: Path) -> None:
    """The scanner is fed in 64 KiB chunks; objects must survive the seam."""
    padding = "x" * (CHUNK * 2)
    cards = [{"name": f"card-{i}", "text": padding} for i in range(4)]
    path = _write(tmp_path, json.dumps(cards))
    streamed = list(stream_objects(path))
    assert [o["name"] for o in streamed] == [c["name"] for c in cards]


def test_a_truncated_final_object_is_not_yielded(tmp_path: Path) -> None:
    """A half-written file must not produce a half-parsed card."""
    text = json.dumps(_sample()[:2])
    path = _write(tmp_path, text[: len(text) // 2])
    assert len(list(stream_objects(path))) <= 1
