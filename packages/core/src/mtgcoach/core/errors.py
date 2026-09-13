"""Errors raised by the engine."""

from __future__ import annotations


class IllegalEventError(Exception):
    """An event that cannot be applied to the current state.

    Raised rather than returned because an illegal event is a bug in the caller,
    not a branch the caller is expected to handle: the UI asks the engine what
    is legal before offering it. Callers that genuinely want to probe legality
    use the predicates in ``legality`` (M4) instead of catching this.
    """
