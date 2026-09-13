"""What cards you own.

Recognition, deck building and the effect fixtures are all scoped to this. It is
why a scan is a two-hundred-way choice rather than a hundred-thousand-way one,
so it is a first-class object rather than an implicit global.

Note what is *not* here: a function that filters ``Card`` objects by set. A
``Card`` is an oracle card and deliberately carries no set, because two printings
of one card behave identically and the engine must not be able to tell them
apart. Which sets a card was printed in is a property of the *store*, which
keeps printings alongside oracle cards, so scoping a collection is a store query
(``CardStore.oracle_ids_in``) rather than a predicate over cards in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.ids import OracleId, SetCode


@dataclass(frozen=True, slots=True)
class Collection:
    """The sets and singles a player owns.

    Growing a collection is a data operation. Nothing here knows which set came
    first, and no code path is allowed to special-case one.
    """

    sets: frozenset[SetCode] = frozenset()
    extra_cards: frozenset[OracleId] = frozenset()

    def with_set(self, set_code: SetCode) -> Collection:
        """Return a copy that also owns ``set_code``."""
        return replace(self, sets=self.sets | {set_code})

    def with_card(self, oracle_id: OracleId) -> Collection:
        """Return a copy that also owns one single."""
        return replace(self, extra_cards=self.extra_cards | {oracle_id})

    @property
    def is_empty(self) -> bool:
        """Whether nothing is owned yet, so recognition cannot be scoped."""
        return not self.sets and not self.extra_cards
