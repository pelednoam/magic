# Magic Coach

A Magic: The Gathering turn coach for learning at the kitchen table. Point a phone at a card
or at the board and get a clear answer to *"what can I do this turn, and what should I do?"*

Built for the Foundations Beginner Box first, designed so that other sets are data rather than
a rewrite. See [`docs/PLAN.md`](docs/PLAN.md) for the full design.

## Status

**M0–M6 merged.** The engine, the tracker, the two-seat server
and the Expo app all work. The turn coach and the rules question box are the newest parts.

The checks are deliberately different strengths, and the wire says which you are getting.
A turn recommendation is `trusted`: it is a choice among options the engine enumerated, and
the engine agrees with it. A rules answer gets two weaker verdicts, and neither is `correct`.
`cited` means every rule it named was one the server retrieved for it. `grounded` means the
words a rules claim cannot be paraphrased around — the arithmetic, and the keyword abilities
it attributes to something — appear in the evidence the prompt carried: the retrieved
passages, and the printed text of the cards in play. "Trample doubles all damage [702.19b]"
is cited and not grounded, and is not shown.

Nothing reads the cited rule and decides that the answer *follows* from it; that needs a
second model, and two models agreeing is not a proof either. So every reply also carries
`unchecked`, which says that in the server's own words, and the retrieved rules are printed
under every answer — they are the part that is certainly true.

## Running it

```bash
uv run mtgcoach sets fetch FDN                        # download the cards from Scryfall
uv run mtgcoach sets add FDN --from data/scryfall/FDN.json
uv run python -m mtgcoach.api.serve --set FDN         # the server, on the laptop in the room
cd apps/mobile && npm install && npm run web          # the app
```

The server prints two things when it starts, and the app needs both:

```
Magic Coach on http://192.168.1.42:8000
  token: <43 characters>
  the app needs the address too: EXPO_PUBLIC_COACH_URL=http://192.168.1.42:8000
```

The **address** is the laptop's on the LAN, not `localhost` — the app defaults to `localhost`,
which on a phone is the phone. Set `EXPO_PUBLIC_COACH_URL` to what the server printed before
`npm run web`, since Metro serves the bundle to the phone and the value is baked into it.

The **token** is the whole of the access control, so every request needs it —
`Authorization: Bearer <token>`, and `?token=` on the WebSocket, which a browser will not let
a page put a header on. A phone asks for it once and you paste it in.
`EXPO_PUBLIC_COACH_TOKEN` works for a localhost-only session, but Expo bakes that into the
bundle Metro serves unauthenticated — so on a LAN, set the URL and paste the token.

What that closes is not a guest's phone. It is a web page the household visits, which could
make cross-origin requests to `http://<laptop>:8000` and previously needed to know nothing at
all to drive the game or spend the Claude subscription. What it does not close is *which
player* is asking: every snapshot still carries both hands, so "you cannot see your opponent's
hand" is still enforced by the room. A token per seat would fix that, and is the next step.

## Playing it against itself

```bash
uv run python -m mtgcoach.selfplay --games 300        # instant, a policy on both seats
uv run python -m mtgcoach.selfplay --games 1 --coach  # Claude on both seats, minutes
```

Two agents play whole games through the real engine, and every event is checked against the
things no play may ever break — cards conserved, no card in two places, one land drop a turn.
The point is not the play, which is foolish: it is that a season puts the engine through states
in an order nobody chose, and a seed replays any game exactly.

300 games is about 100,000 events and takes a few seconds. `--coach` makes Claude the agent, so
the coach's advice is *applied* and the next position is a consequence of the last piece of it —
which is the only way bad advice shows up, since it compounds. That run reports how many of its
answers survived the engine's checks.

A seed reproduces a deal exactly but not the coach, so a coached run writes a **journal** — every
briefing, every answer, every verdict, and the game itself as the events it applied. `--replay`
plays it back: the identical game in a second instead of twenty minutes, and a way to ask what a
change to the engine does to a game the coach already played.
[docs/SELFPLAY.md](docs/SELFPLAY.md) has the whole thing.

## Walking a game that was played

Start the server with a `--data` directory holding journals and the app grows a third screen:
pick a run, pick a game, and step through it one decision at a time — the board, what the coach
said, and the engine's objections beside it where it refused. "Ask about this" turns that moment
into a real game on the server, so the question box and the coach both answer about *that*
position rather than one like it.

Nothing is re-asked to build it. Each moment is the recorded events folded over the opening
board — `core` and nothing else — so what is on screen is what happened in the game, which is
what it has to be for somebody to learn the rules from it.

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

A question only finds a rule it shares words with, which is a problem when the rule is written
in a vocabulary a beginner does not have. *"Can a creature that came into play this turn
block?"* is answered by rule 302.6, and 302.6 says "under its controller's control continuously
since their most recent turn began" — so nothing matched and the answer was "the rules I was
given don't talk about how new a creature is". `rules/phrasing.py` maps a few such paraphrases
onto the rules' own wording; it is short on purpose, and a gate check keeps every phrase in it
one the current document actually uses (where the document is installed — see below).

The mirror problem: Magic names its abilities with ordinary words, so a question can contain one
without being about it. *"What happens when my hit points reach zero?"* used to return the rules
for **reach**, the keyword. `rules/keywords.py` sets such a word aside only on positive evidence
that it is a verb — a number after it, a subject pronoun before it — because a question *about* a
keyword is far commoner, and it reads the keyword list off the document rather than hardcoding it.

And the third: the rules state restrictions as requirements, a question states the thing being
restricted, so *"can a tapped creature block?"* and 509.1a's *"must be untapped"* share no word at
all. `rules/negation.py` bridges the two polarities — deliberately narrowly, since "not X" → "unX"
applied blindly turns "not less than" into a search for *unless*.

`tools/check_retrieval.py` keeps all three honest: it asks the **installed** rules 28 questions a
person would actually type and fails the gate if an answering rule stops coming back. On a machine
without the rules it prints `SKIPPED` and passes, because the document is Wizards' and is
deliberately not vendored — so it guards the laptop the coach runs on, and says so plainly
anywhere else. CI fetches the document itself and records which revision it got, because a missing
corpus must not quietly count as a rules-quality pass.

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

All gates at once:

```bash
uv run tools/gate.sh
```

CI runs every one of them. That was not true — the workflow omitted the CLI-flag check, both rules
checks, the TypeScript typecheck and the whole mobile test suite, so a change to the events the app
sends when you tap a card could go green with nothing having typechecked it. Nothing noticed,
because nothing was looking, so `tools/check_ci_covers_gate.py` now looks: it reads both
definitions and fails when the workflow runs less than the gate. The one-way comparison is
deliberate — CI may do more (it fetches the rules), and a workflow forbidden from adding a check
would be a worse workflow.

The app's checks need `node_modules`. `tools/gate.sh` says so and stops rather than reporting "all
gates passed" having silently checked no TypeScript; `SKIP_APP=1` accepts that trade explicitly.

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
