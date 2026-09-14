"""The bucket and the semaphore themselves, without a route in front.

``test_app_ask_limits`` covers what a player sees when one of these refuses.
These are about the arithmetic: that the capacity is the one it was given, that
a refusal is not charged for, and that a token comes back.
"""

from __future__ import annotations

import time

import pytest

from mtgcoach.api import rationing


def test_a_refused_busy_request_does_not_spend_a_token() -> None:
    """A refusal is not a request.

    A player retrying two seconds later should not be paying for the attempt
    that never started.
    """
    rations = rationing.Rationed()
    held = [rations.take() for _ in range(rationing.MAX_IN_FLIGHT)]
    assert held == [""] * rationing.MAX_IN_FLIGHT

    assert "busy" in rations.take(), "the concurrency cap, not the rate limit"
    for _ in held:
        rations.release()

    # Only the ones that actually ran were charged, so the rest of the minute's
    # allowance is still there.
    for _ in range(rationing.BURST - rationing.MAX_IN_FLIGHT):
        assert rations.take() == ""
        rations.release()
    assert "a lot of questions" in rations.take()


def test_the_bucket_starts_at_the_capacity_it_was_given() -> None:
    """Not at the module's.

    The default was `float(BURST)`, so a `Rationed` built with a smaller burst
    was constructed holding twelve tokens. `_afford` clamps before it looks, so
    the first call put it right and nothing misbehaved -- which is exactly why
    this is worth a test: the field was only correct because of a `min`
    somewhere else.
    """
    small = rationing.Rationed(burst=1, window=600.0)
    assert small.take() == ""
    small.release()
    assert "a lot of questions" in small.take(), "one token means one call"


@pytest.mark.parametrize(
    ("burst", "window"),
    [(0, 60.0), (-1, 60.0), (12, 0.0), (12, -1.0)],
)
def test_a_limit_that_is_not_positive_is_refused(burst: int, window: float) -> None:
    """Neither limit means anything at zero or below.

    A window of zero divides by zero in the refill, and a burst of zero can
    never afford a call. Both are better said at construction than found in
    the arithmetic.
    """
    with pytest.raises(ValueError, match="must be positive"):
        rationing.Rationed(burst=burst, window=window)


def test_tokens_come_back_over_time() -> None:
    """Otherwise a long game would run out halfway through."""
    rations = rationing.Rationed(burst=2, window=0.05)
    assert rations.take() == ""
    rations.release()
    assert rations.take() == ""
    rations.release()
    assert "a lot of questions" in rations.take()
    time.sleep(0.08)
    assert rations.take() == ""
