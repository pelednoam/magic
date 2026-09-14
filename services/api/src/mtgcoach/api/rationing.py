"""How often the two slow routes may be asked, and by how many at once.

Neither is a security boundary. The token in ``access`` is the lock; this is
sized for the hand that slips, not for somebody who wants in. A rate limit is
not access control and would be a poor one.

What it is for is the failure that does not need an attacker. Both routes start
a ``claude`` process and spend the operator's subscription, and the client that
calls them is a phone with a button on it. A stuck finger, a reload loop, or a
page left open on a second device is enough to turn "a coach" into "the laptop
is on fire and the quota is gone". A semaphore bounds how many run at once; a
bucket bounds how many run at all.

Per server, not per module, and deliberately not per client: every request
carries the same token, so there is no identity here to key on. A token per
seat would give it one, and that is where this would become per player.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

#: How many may be in flight at once. Not sized against the threadpool -- anyio
#: gives it forty workers, which is plenty -- but against the machine: three
#: Node processes thinking at once is what a laptop in a kitchen can carry
#: while still answering the tracker's own routes instantly.
MAX_IN_FLIGHT = 3

#: How many may be started in a window, and how long that window is. Generous
#: for a kitchen table -- a whole game is about fifteen coach taps -- and
#: nowhere near enough to drain a subscription by accident.
BURST = 12
WINDOW_SECONDS = 60.0


@dataclass(slots=True)
class Rationed:
    """The two limits, for one server."""

    in_flight: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(MAX_IN_FLIGHT)
    )
    burst: int = BURST
    window: float = WINDOW_SECONDS
    _lock: threading.Lock = field(default_factory=threading.Lock)
    #: Tokens left, as a float because it refills continuously. `init=False`
    #: and set in `__post_init__`, because the default was `float(BURST)` --
    #: the module constant, so a `Rationed(burst=2)` was constructed holding
    #: twelve. Harmless as it happened, because `_afford` clamps to
    #: `self.burst` before looking, so the first call corrected it; but that
    #: made one field's correctness depend on an unrelated `min` elsewhere,
    #: and the next reader of either would have to find the other.
    _tokens: float = field(init=False)
    _refilled: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        """Start full, at the capacity this instance was actually given.

        Raises:
            ValueError: If ``burst`` or ``window`` is not positive. A window of
                zero divides by zero in the refill, and a burst of zero can
                never afford a call -- both are better said here than found in
                the arithmetic.
        """
        if self.burst <= 0:
            msg = f"burst must be positive, not {self.burst}"
            raise ValueError(msg)
        if self.window <= 0:
            msg = f"window must be positive, not {self.window}"
            raise ValueError(msg)
        self._tokens = float(self.burst)

    def take(self) -> str:
        """Take a slot, or say why there is none.

        Returns:
            The empty string when the caller may proceed, and a sentence for
            the player when it may not. A sentence rather than an exception
            because both callers turn it into the same 503, and the interesting
            part is which limit was hit.
        """
        if not self._afford():
            return "that is a lot of questions at once; give it a minute"
        if not self.in_flight.acquire(blocking=False):
            # Put the token back: nothing was spent, and a player who retries
            # in two seconds should not be paying for the attempt that never
            # started.
            self._refund()
            return "the coach is busy with another question; try again in a moment"
        return ""

    def release(self) -> None:
        """Give back a slot taken by ``take``."""
        self.in_flight.release()

    def _afford(self) -> bool:
        """Whether there is a token, refilling first."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                float(self.burst),
                self._tokens + (now - self._refilled) * self.burst / self.window,
            )
            self._refilled = now
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True

    def _refund(self) -> None:
        """Return a token taken for a call that never ran."""
        with self._lock:
            self._tokens = min(float(self.burst), self._tokens + 1.0)
