"""The `mtgcoach effects` subcommands: extract, review, seal.

Three steps rather than one because the middle one is a person. Extraction
proposes, review accepts, and only sealing produces data the engine will read --
so nothing a model invented can reach a player without someone having looked at
it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata import manifest as manifest_mod
from mtgcoach.carddata.commands import FAILED, OK, safe
from mtgcoach.carddata.paths import effects_path, manifest_path, set_dir
from mtgcoach.carddata.sealed import CardAbilities, dump, load
from mtgcoach.core.abilities import UnmodeledAbility

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

    from mtgcoach.carddata.extraction import EffectExtractor
    from mtgcoach.carddata.store import CardStore
    from mtgcoach.core.ids import SetCode

#: Where a run's unreviewed output waits. Deliberately not under data/sets --
#: a proposal is not data, and only `seal` promotes it.
PROPOSALS = "proposals.json"


def extract(
    store: CardStore,
    extractor: EffectExtractor,
    data_root: Path,
    set_code: SetCode,
    out: TextIO,
) -> int:
    """Propose abilities for every card in a set, and write them for review."""
    cards = store.cards_in_set(set_code)
    if not cards:
        print(f"no {set_code} cards imported; run `mtgcoach sets add` first", file=out)
        return FAILED

    result = extractor.extract(cards)
    for problem in result.failures:
        print(f"  problem: {safe(problem)}", file=out)

    target = set_dir(data_root, set_code)
    target.mkdir(parents=True, exist_ok=True)
    path = target / PROPOSALS
    dump(
        path,
        [CardAbilities(p.oracle_id, p.name, p.abilities, p.notes) for p in result.proposals],
    )
    attention = sum(1 for p in result.proposals if p.needs_attention)
    print(
        f"{len(result.proposals)} proposals written to {path.name}; "
        f"{attention} need attention, {len(result.failures)} problems",
        file=out,
    )
    return FAILED if result.failures else OK


def review(data_root: Path, set_code: SetCode, out: TextIO) -> int:
    """Show what is waiting to be sealed, worst first."""
    path = set_dir(data_root, set_code) / PROPOSALS
    if not path.exists():
        print(f"nothing to review; run `mtgcoach effects extract {set_code}`", file=out)
        return FAILED

    cards = load(path)
    unmodelled = [c for c in cards if not c.is_modelled]
    for card in unmodelled:
        print(f"  unmodelled  {safe(card.name)}", file=out)
        for ability in card.abilities:
            if isinstance(ability, UnmodeledAbility):
                print(f"                {safe(ability.reason)[:90]}", file=out)
    modelled = len(cards) - len(unmodelled)
    share = 100 * modelled / len(cards) if cards else 0
    print(f"{modelled}/{len(cards)} cards fully modelled ({share:.0f}%)", file=out)
    return OK


def seal(data_root: Path, set_code: SetCode, out: TextIO) -> int:
    """Promote reviewed proposals to the fixture the engine reads."""
    source = set_dir(data_root, set_code) / PROPOSALS
    if not source.exists():
        print(f"nothing to seal; run `mtgcoach effects extract {set_code}`", file=out)
        return FAILED

    cards = load(source)
    destination = effects_path(data_root, set_code)
    dump(destination, list(cards))

    record = manifest_mod.Manifest(
        set_code=set_code,
        schema_version=manifest_mod.SCHEMA_VERSION,
        card_count=len(cards),
        modelled_count=sum(1 for c in cards if c.is_modelled),
        sha256=manifest_mod.sha256_of(destination),
    )
    manifest_mod.write(manifest_path(data_root, set_code), record)
    print(
        f"sealed {record.card_count} cards for {set_code} "
        f"({record.coverage:.0%} modelled), sha {record.sha256[:12]}",
        file=out,
    )
    return OK


def check(data_root: Path, set_code: SetCode, out: TextIO) -> int:
    """Verify a sealed fixture still matches its manifest."""
    path = manifest_path(data_root, set_code)
    if not path.exists():
        print(f"{set_code} has no manifest; it has never been sealed", file=out)
        return FAILED
    problems = manifest_mod.verify(effects_path(data_root, set_code), manifest_mod.read(path))
    for problem in problems:
        print(f"  {safe(problem)}", file=out)
    if problems:
        print(f"{set_code} fixture does not match its manifest", file=out)
        return FAILED
    print(f"{set_code} fixture matches its manifest", file=out)
    return OK
