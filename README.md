# Magic Coach

A Magic: The Gathering turn coach for learning at the kitchen table. Point a phone at a card
or at the board and get a clear answer to *"what can I do this turn, and what should I do?"*

Built for the Foundations Beginner Box first, designed so that other sets are data rather than
a rewrite. See [`docs/PLAN.md`](docs/PLAN.md) for the full design.

## Status

**M0–M5 merged; M6 (the Claude layer) on `m6`.** The engine, the tracker, the two-seat server
and the Expo app all work. The turn coach and the rules question box are the newest parts:
Claude explains, and a checker refuses anything it says that the engine or the Comprehensive
Rules do not back up.

## Running it

```bash
uv run mtgcoach sets add FDN                     # import the cards (needs network)
uv run python -m mtgcoach.api.serve --set FDN    # the server, on the laptop in the room
cd apps/mobile && npm install && npm run web     # the app
```

Rules questions need the Comprehensive Rules on disk. They are not vendored here — Wizards
revise them with every set, and a stale copy is exactly the kind of confidently-wrong answer
this project exists to avoid:

```bash
mkdir -p data/rules
curl -L -o data/rules/comprehensive.txt \
  "https://media.wizards.com/2025/downloads/MagicCompRules%2020250207.txt"
```

Without it everything else works and the server says the question box is off.

Both Claude features shell out to the local `claude` command rather than the API, so they draw
on a Claude Code subscription and cost no credits.

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
| `packages/coach` | Turns the engine's solvers into one turn report, and checks what Claude says about it. |
| `packages/rules` | The Comprehensive Rules: parsed, searchable, and quotable. |
| `packages/vision` | Card detection and recognition. |
| `services/api` | FastAPI service, WebSocket sync, adapters for the core protocols. |
| `apps/mobile` | The Expo client: Android, tablet and the browser. |
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
