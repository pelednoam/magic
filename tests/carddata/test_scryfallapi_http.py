"""The HTTP client itself: what it sends, and what it refuses to fetch.

``urlopen`` is replaced throughout, so nothing here reaches the network. The
refusals are the interesting half -- ``next_page`` comes out of a response body,
so following it blindly is following a redirect somebody else chose.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Self, cast

if TYPE_CHECKING:
    import urllib.request
    from collections.abc import Callable
    from typing import IO

import pytest

from mtgcoach.carddata.scryfallapi import HOST, ScryfallError
from mtgcoach.carddata.scryfallhttp import AGENT, READ_TIMEOUT, HttpPages


@pytest.mark.parametrize(
    "url",
    [
        "http://api.scryfall.com/cards/search",
        "https://evil.example.com/cards/search",
        "file:///etc/passwd",
        "https://api.scryfall.com.evil.example.com/x",
    ],
)
def test_a_url_that_is_not_scryfall_over_tls_is_refused(url: str) -> None:
    """`next_page` comes out of a response body.

    Following it blindly is following a redirect somebody else chose -- to
    another host, or to a `file://` path, which `urlopen` will happily read.
    """
    with pytest.raises(ScryfallError, match="refusing to fetch"):
        HttpPages().fetch(url)


def test_a_page_that_is_not_json_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(HttpPages, "_read", _reading("<html>502</html>"))
    with pytest.raises(ScryfallError, match="not readable"):
        HttpPages().fetch(f"https://{HOST}/cards/search")


def test_a_page_that_is_json_but_not_an_object_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(HttpPages, "_read", _reading(json.dumps([1, 2])))
    with pytest.raises(ScryfallError, match="not readable"):
        HttpPages().fetch(f"https://{HOST}/cards/search")


def test_a_request_that_fails_is_refused_without_quoting_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The class, not the text: a URLError's message carries the whole URL."""

    def refuse(_self: HttpPages, _url: str) -> str:
        msg = "connection refused to https://api.scryfall.com/secret"
        raise OSError(msg)

    monkeypatch.setattr(HttpPages, "_read", refuse)
    with pytest.raises(ScryfallError, match="could not reach Scryfall: OSError") as refused:
        HttpPages().fetch(f"https://{HOST}/cards/search")
    assert "secret" not in str(refused.value)


def test_the_polite_pause_happens_between_requests_and_not_before_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scryfall is a free service run for players and nobody enforces this."""
    slept: list[float] = []
    monkeypatch.setattr("mtgcoach.carddata.scryfallhttp.time.sleep", slept.append)
    monkeypatch.setattr(HttpPages, "_read", _reading(json.dumps({"object": "list"})))
    pages = HttpPages(pause=0.25)
    pages.fetch(f"https://{HOST}/a")
    assert slept == []
    pages.fetch(f"https://{HOST}/b")
    assert slept == [0.25]


class Response:
    """Enough of an HTTP response for `_read`, as a context manager."""

    def __init__(self, body: bytes) -> None:
        """Answer with these bytes."""
        self._body = body

    def __enter__(self) -> Self:
        """Enter the block."""
        return self

    def __exit__(self, *_exit: object) -> None:
        """Leave it."""

    def read(self) -> bytes:
        """The body."""
        return self._body


def test_the_request_says_who_is_calling() -> None:
    """Scryfall's documentation asks for it.

    An anonymous scraper is how a free service ends up behind a login.
    """
    seen: list[urllib.request.Request] = []

    def opened(request: urllib.request.Request, timeout: float) -> Response:
        seen.append(request)
        assert timeout == READ_TIMEOUT
        return Response(json.dumps({"object": "list"}).encode())

    assert HttpPages(opener=_Opening(opened)).fetch(f"https://{HOST}/cards/search") == {
        "object": "list"
    }
    (request,) = seen
    assert request.get_header("User-agent") == AGENT
    assert request.get_header("Accept") == "application/json"


def test_a_body_that_is_not_utf8_does_not_stop_the_import() -> None:
    """A card name is not going to be, but a truncated response might."""
    body = json.dumps({"object": "list", "name": "x"}).encode()[:-1] + b"\xff}"
    pages = HttpPages(opener=_Opening(_opening(Response(body))))
    with pytest.raises(ScryfallError, match="not readable"):
        pages.fetch(f"https://{HOST}/cards/search")


def _reading(body: str) -> Callable[[HttpPages, str], str]:
    """A `_read` that answers with this, whatever it was asked for."""

    def read(_self: HttpPages, _url: str) -> str:
        return body

    return read


def _opening(response: Response) -> Callable[[urllib.request.Request, float], Response]:
    """An `open` that answers with this, whatever it was asked for."""

    def opened(_request: urllib.request.Request, _timeout: float) -> Response:
        return response

    return opened


class _Opening:
    """An opener that hands back whatever it was built with."""

    def __init__(self, answer: Callable[[urllib.request.Request, float], Response]) -> None:
        """Answer every call with this."""
        self._answer = answer

    def open(self, request: urllib.request.Request, timeout: float) -> IO[bytes]:
        """The response, typed as the protocol wants it."""
        return cast("IO[bytes]", self._answer(request, timeout))
