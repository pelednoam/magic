"""Asking Scryfall, without asking Scryfall.

``Pages`` is a protocol precisely so that these run offline. What is tested is
the pagination, the refusals, and the one thing a network client must not do:
follow a URL out of a response body to wherever it says.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.scryfallapi import (
    HOST,
    MAX_PAGES,
    ScryfallError,
    printings_for,
)
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from mtgcoach.carddata.jsondata import JsonObject, JsonValue

FDN = SetCode("FDN")


class Answers:
    """A ``Pages`` that replies from a list, and records what it was asked."""

    def __init__(self, *replies: JsonObject) -> None:
        """Reply with these, in order."""
        self.replies = list(replies)
        self.asked: list[str] = []

    def fetch(self, url: str) -> JsonObject:
        """The next reply.

        Raises:
            ScryfallError: If asked more times than it has replies.
        """
        self.asked.append(url)
        if not self.replies:
            msg = "asked for more pages than the test prepared"
            raise ScryfallError(msg)
        return self.replies.pop(0)


def _page(*names: str, more: str = "") -> JsonObject:
    """One page of search results."""
    page: JsonObject = {
        "object": "list",
        "has_more": bool(more),
        "data": [{"name": name} for name in names],
    }
    if more:
        page["next_page"] = more
    return page


def test_one_page_is_read() -> None:
    pages = Answers(_page("Forest", "Llanowar Elves"))
    assert [c["name"] for c in printings_for(FDN, pages)] == ["Forest", "Llanowar Elves"]


def test_the_set_is_asked_for_by_code() -> None:
    pages = Answers(_page("Forest"))
    list(printings_for(FDN, pages))
    assert "set%3AFDN" in pages.asked[0]
    assert "unique=prints" in pages.asked[0], "variants are printings, and we want them"


def test_every_page_is_followed() -> None:
    """771 printings for the Beginner Box is five requests, not one."""
    following = f"https://{HOST}/cards/search?page=2"
    pages = Answers(_page("Forest", more=following), _page("Mountain"))
    assert [c["name"] for c in printings_for(FDN, pages)] == ["Forest", "Mountain"]
    assert pages.asked[1] == following


def test_a_page_that_says_it_is_the_last_ends_it() -> None:
    """Even if it carries a `next_page`, which Scryfall's last page does not."""
    pages = Answers({**_page("Forest", more="https://x/2"), "has_more": False})
    assert len(list(printings_for(FDN, pages))) == 1
    assert len(pages.asked) == 1


def test_a_set_nobody_has_heard_of_says_so() -> None:
    """A 404 body, not an empty list.

    Reporting "0 cards" for that would send somebody looking for a bug in the
    importer.
    """
    pages = Answers({"object": "error", "details": "Your query didn't match anything."})
    with pytest.raises(ScryfallError, match="no printings for ZZZ"):
        list(printings_for(SetCode("ZZZ"), pages))


def test_an_error_with_no_details_still_says_something() -> None:
    pages = Answers({"object": "error"})
    with pytest.raises(ScryfallError, match="no such set"):
        list(printings_for(FDN, pages))


def test_a_page_with_no_card_list_is_refused() -> None:
    pages = Answers({"object": "list", "has_more": False})
    with pytest.raises(ScryfallError, match="no card list"):
        list(printings_for(FDN, pages))


def test_something_that_is_not_a_card_object_fails_the_import() -> None:
    """Skipping it was a quiet way to lose a card.

    This is an import, not a search: a page that is not what it should be is
    worth failing over, because the alternative is a database that is wrong in
    a way nobody finds until a game.
    """
    pages = Answers({"object": "list", "has_more": False, "data": [{"name": "Forest"}, 7]})
    with pytest.raises(ScryfallError, match="not a card"):
        list(printings_for(FDN, pages))


@pytest.mark.parametrize("envelope", [{}, {"object": "card"}, {"object": 7}])
def test_a_page_that_is_not_a_list_of_cards_is_refused(envelope: JsonObject) -> None:
    """One shape was still getting through.

    `_cards_in` refuses an `object: "error"` page and a page with no card list,
    which leaves something that is neither -- a proxy's own JSON, a single card
    object -- whose `has_more` is absent. Absent read as "that was the last
    page".
    """
    pages = Answers({**envelope, "data": [{"name": "Forest"}]})
    with pytest.raises(ScryfallError, match="not a list of cards"):
        list(printings_for(FDN, pages))


@pytest.mark.parametrize("more", [None, 0, "false", "true", []])
def test_a_page_that_does_not_say_whether_there_are_more_is_refused(more: JsonValue) -> None:
    """Absent is not false.

    `is not True` read a missing or corrupted `has_more` as the last page, so a
    truncated or rewritten envelope ended the download and wrote a short file
    that imported cleanly. Only Scryfall saying `false` ends this.
    """
    pages = Answers({"object": "list", "has_more": more, "data": [{"name": "Forest"}]})
    with pytest.raises(ScryfallError, match="did not say whether"):
        list(printings_for(FDN, pages))


def test_a_page_with_no_has_more_at_all_is_refused() -> None:
    """Absent is not false."""
    pages = Answers({"object": "list", "data": [{"name": "Forest"}]})
    with pytest.raises(ScryfallError, match="did not say whether"):
        list(printings_for(FDN, pages))


def test_more_pages_with_nowhere_to_go_fails_the_import() -> None:
    """It said there was more and did not say where.

    Returning there looked like a finished download and wrote a short file that
    imported cleanly -- a set quietly missing four hundred printings, which
    nothing downstream could notice.
    """
    pages = Answers({"object": "list", "has_more": True, "data": [{"name": "Forest"}]})
    with pytest.raises(ScryfallError, match="not where"):
        list(printings_for(FDN, pages))


def test_pages_that_never_end_are_refused() -> None:
    """A `next_page` that loops would otherwise fetch until the heat death."""
    loop = f"https://{HOST}/cards/search?page=1"
    pages = Answers(*[_page("Forest", more=loop) for _ in range(MAX_PAGES + 1)])
    with pytest.raises(ScryfallError, match="past 60"):
        list(printings_for(FDN, pages))
