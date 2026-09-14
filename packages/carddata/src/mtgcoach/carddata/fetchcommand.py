"""Downloading one set's printings to a file.

Its own module because it is the one command that touches the network, and
keeping that in one place is what lets every other command be one a test can
run without asking anybody's permission.

A file rather than straight into the store, for three reasons. The effects
workflow reads the same cards again and re-downloading them is rude to a free
service; a failed import can be retried without another five requests; and the
file is what ``sets add`` already knew how to read.
"""

from __future__ import annotations

import json
import shlex
from typing import TYPE_CHECKING

from mtgcoach.carddata.commands import FAILED, OK, safe
from mtgcoach.carddata.scryfallapi import ScryfallError, printings_for

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

    from mtgcoach.carddata.scryfallapi import Pages
    from mtgcoach.core.ids import SetCode


def sets_fetch(pages: Pages, set_code: SetCode, destination: Path, out: TextIO) -> int:
    """Download one set's printings from Scryfall and write them to a file.

    A file rather than straight into the store, for three reasons. The effects
    workflow reads the same cards again and re-downloading them is rude to a
    free service; a failed import can be retried without another five requests;
    and keeping the network in one command means every other command is one a
    test can run.

    Returns:
        The process exit code -- ``OK``, or ``FAILED`` with a sentence saying
        what Scryfall said.
    """
    try:
        found = list(printings_for(set_code, pages))
    except ScryfallError as refused:
        print(f"could not fetch {set_code}: {safe(str(refused))}", file=out)
        return FAILED
    if not found:
        print(f"Scryfall has no printings for {set_code}", file=out)
        return FAILED
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(found, file)
    print(f"wrote {len(found)} {set_code} printings to {destination}", file=out)
    # Quoted, because `--to` takes any path and the line above is meant to be
    # copied into a shell. An unquoted path with a space in it either fails or,
    # worse, runs whatever the rest of it turns out to mean.
    where = shlex.quote(str(destination))
    print(f"now run: mtgcoach sets add {set_code} --from {where}", file=out)
    return OK
