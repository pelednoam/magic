"""Which engine this is, as something a recorded game can be compared against.

``docs/DECISIONS.md`` item 5: a journal records its events and not the engine
that produced them, "which is exactly what made item 6 a question, and what
made a whole directory of journals unreadable when priority arrived with
nothing recording that they predated it."

So: a digest over this package's source. Three things it is not, and each was
considered:

- **Not the package version.** Every ``pyproject.toml`` here says ``0.0.0``
  and a number nobody bumps is a number that lies. This cannot be forgotten,
  because nothing has to remember it.
- **Not a git commit.** It would name the whole repository, change when a
  README does, and be absent from an installed wheel with no git around it.
- **Not a schema or a rule count.** Either would have to be maintained by hand
  in step with the code, which is the same failure as the version.

**What it means, exactly.** Two games with the same digest were played by
byte-identical engine source. Two with different ones were not -- and that is
all: a comment changed is a different digest, so a difference is a *reason to
check*, not a verdict. It is diagnostic and nothing gates on it. The gate is
the engine itself, which refuses an event it no longer considers legal and lets
``replays`` skip that game rather than show a board the events did not produce.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path
from typing import Final

#: How much of the digest to carry. Twelve hex characters is 48 bits, which is
#: the same length ``manifest`` prints a card-data checksum at and far more
#: than enough to tell two engines apart -- nobody is attacking this, and a
#: full 64 characters in every journal line is noise a person has to skip.
LENGTH: Final = 12

#: What counts as source. Not ``.pyc``, not ``__pycache__``, and not the tests
#: -- the digest is over the engine, and a test that exercises it differently
#: does not make it a different engine.
SUFFIX: Final = ".py"


@cache
def engine() -> str:
    """A digest over every source file of ``mtgcoach.core``.

    Cached, because it reads the whole package -- thirty small files -- and the
    answer cannot change while the process runs. A server asks once at startup
    and a self-play season asks once per game.
    """
    return digest_of(Path(__file__).parent)


def digest_of(package: Path) -> str:
    """A digest over the source files under one directory.

    Sorted by path so the answer does not depend on the order a filesystem
    hands its entries back, and each file's *relative path* goes into the hash
    as well as its bytes -- otherwise renaming a module, or moving code between
    two of them, leaves the digest unchanged.

    ``package`` is a parameter only so that a test can digest a directory it
    wrote itself rather than asserting things about this one.
    """
    running = hashlib.sha256()
    for path in sorted(package.rglob(f"*{SUFFIX}")):
        running.update(str(path.relative_to(package)).encode("utf-8"))
        running.update(path.read_bytes())
    return running.hexdigest()[:LENGTH]
