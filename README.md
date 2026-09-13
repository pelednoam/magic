# Magic Coach

A Magic: The Gathering turn coach for learning at the kitchen table. Point a phone at a card
or at the board and get a clear answer to *"what can I do this turn, and what should I do?"*

Built for the Foundations Beginner Box first, designed so that other sets are data rather than
a rewrite. See [`docs/PLAN.md`](docs/PLAN.md) for the full design.

## Status

**M0** — scaffolding, toolchain and gates. Not yet usable.

## Development

```bash
uv sync                 # create .venv and install the workspace
uv run pytest           # tests
uv run ruff check .     # lint
uv run mypy             # type check (config in pyproject.toml)
uv run pyright          # second type check
uv run pre-commit install
```

All gates at once, exactly as CI runs them:

```bash
uv run tools/gate.sh
```

## Layout

| Path | What |
|---|---|
| `packages/core` | Pure game logic. No I/O, no framework, no knowledge of any set. |
| `packages/carddata` | Scryfall ingestion, collection management, on-disk set layout. |
| `packages/vision` | Card detection and recognition. |
| `services/api` | FastAPI service, WebSocket sync, adapters for the core protocols. |
| `tests/` | All Python tests, mirroring the package tree. |
| `tools/` | Gate enforcement and dev scripts. (`scripts/` belongs to the review agent.) |
| `data/sets/` | Per-set decklists, effect fixtures and signed manifests. |

## Code review

Reviews run through
[multi-model-code-review-agent](https://github.com/pelednoam/multi-model-code-review-agent):
"review this" per commit, "full review" at each milestone, and the convergence loop for
anything touching `core`. Configuration lives in `scripts/preflight/config.py`.

---

*Unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy.
Not approved or endorsed by Wizards. Portions of the materials used are property of
Wizards of the Coast LLC.*
