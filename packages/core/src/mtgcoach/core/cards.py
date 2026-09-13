"""A single physical card in a single game."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.ids import InstanceId, OracleId


@dataclass(frozen=True, slots=True)
class CardInstance:
    """One physical card on the table.

    Two copies of the same card in a deck share an ``oracle_id`` -- the engine
    treats them as identical in behaviour -- but never an ``instance_id``, which
    is what lets the state distinguish "the Mountain you tapped" from "the other
    Mountain". Nothing here knows which set the card was printed in; a printing
    is presentation, and the engine works on oracle behaviour only.
    """

    instance_id: InstanceId
    oracle_id: OracleId
