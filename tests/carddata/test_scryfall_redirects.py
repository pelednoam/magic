"""Where a redirect is allowed to lead.

``_check`` guarded only the first hop. ``urlopen`` installs a redirect handler
by default, so a 302 from an allowed Scryfall URL was followed anywhere --
which is precisely the "redirect somebody else chose" the module says it
refuses, and its own docstring was wrong about it.
"""

from __future__ import annotations

from urllib.request import Request

import pytest

from mtgcoach.carddata.scryfallapi import HOST, ScryfallError
from mtgcoach.carddata.scryfallhttp import CheckedRedirects


def test_a_redirect_off_scryfall_is_refused() -> None:
    """`_check` guarded only the first hop.

    `urlopen` installs a redirect handler by default, so a 302 from an allowed
    Scryfall URL was followed anywhere -- which is precisely the "a redirect
    somebody else chose" this module says it refuses. Its own docstring was
    wrong about it.
    """
    handler = CheckedRedirects()
    with pytest.raises(ScryfallError, match="refusing to fetch"):
        handler.redirect_request(
            _request(f"https://{HOST}/cards/search"),
            None,
            302,
            "Found",
            {},
            "https://evil.example.com/cards",
        )


def test_a_redirect_that_drops_tls_is_refused() -> None:
    handler = CheckedRedirects()
    with pytest.raises(ScryfallError, match="refusing to fetch"):
        handler.redirect_request(
            _request(f"https://{HOST}/cards/search"),
            None,
            302,
            "Found",
            {},
            f"http://{HOST}/cards",
        )


def test_a_redirect_within_scryfall_is_followed() -> None:
    """Scryfall's own pagination has used them."""
    handler = CheckedRedirects()
    followed = handler.redirect_request(
        _request(f"https://{HOST}/cards/search"),
        None,
        302,
        "Found",
        {},
        f"https://{HOST}/cards/search?page=2",
    )
    assert followed is not None
    assert followed.full_url == f"https://{HOST}/cards/search?page=2"


def _request(url: str) -> Request:
    """A request, for handing to the redirect handler."""
    return Request(url, headers={"Host": HOST})  # noqa: S310 - literal https URL
