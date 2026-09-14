# Magic Coach

A Magic: The Gathering turn coach for learning at the kitchen table. Point a phone at a card
or at the board and get a clear answer to *"what can I do this turn, and what should I do?"*

Built for the Foundations Beginner Box first, designed so that other sets are data rather than
a rewrite. See [`docs/PLAN.md`](docs/PLAN.md) for the full design.

## Status

**M0–M6 merged.** The engine, the tracker, the two-seat server
and the Expo app all work. The turn coach and the rules question box are the newest parts.

The two checks are deliberately different strengths, and the wire says which you are getting.
A turn recommendation is `trusted`: it is a choice among options the engine enumerated, and
the engine agrees with it. A rules answer is only `cited`: every rule it named was one the
server retrieved for it. Nothing reads that rule and checks the claim against it — so the
retrieved rules are printed under every answer, and they are the part that is certainly true.

## Running it

```bash
uv run mtgcoach sets fetch FDN                        # download the cards from Scryfall
uv run mtgcoach sets add FDN --from data/scryfall/FDN.json
uv run python -m mtgcoach.api.serve --set FDN         # the server, on the laptop in the room
cd apps/mobile && npm install && npm run web          # the app
```

The server prints its address and a token when it starts. The token is its only access
control, so every request needs it — `Authorization: Bearer <token>`, and `?token=` on the
WebSocket, which a browser will not let a page put a header on. A phone asks for it once and
you paste it in. `EXPO_PUBLIC_COACH_TOKEN` works for a localhost-only session, but Expo bakes
it into the bundle Metro serves unauthenticated — so on a LAN, paste it.

What that closes is not a guest's phone. It is a web page the household visits, which could
make cross-origin requests to `http://<laptop>:8000` and previously needed to know nothing at
all to drive the game or spend the Claude subscription. What it does not close is *which
player* is asking: every snapshot still carries both hands, so "you cannot see your opponent's
hand" is still enforced by the room. A token per seat would fix that, and is the next step.

`sets fetch` is the only command that touches the network. It asks Scryfall for one set —
771 printings for Foundations, five requests — and writes them to a file, so re-importing
and the effects workflow do not ask again. `mtgcoach decks verify FDN` then checks all ten
Beginner Box decklists against what was imported.

Rules questions need the Comprehensive Rules on disk. They are not vendored here — Wizards
revise them with every set, and a stale copy is exactly the kind of confidently-wrong answer
this project exists to avoid:

```bash
mkdir -p data/rules
curl -L -o data/rules/comprehensive.txt -- "$URL"
```

where `$URL` is the plain-text link on <https://magic.wizards.com/en/rules>. Not a fixed
address on purpose: Wizards publish a new document with every set, and an eighteen-month-old
copy answers questions about errataed cards with complete confidence.

Without it everything else works, the server says so at startup, and the app shows the
question box as switched off rather than letting you type into it.

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
