# Magic Coach — design & implementation plan

An assistant for learning Magic: The Gathering at the kitchen table. Point a phone at a card
or at the board, and get a clear answer to *"what can I do this turn, and what should I do?"*

**Status:** M0 complete — scaffolding, toolchain and gates, on branch `m0-scaffolding`.
M1 next; see §10.

---

## 1. The central design decision

The obvious framing — *photograph the table, get advice* — is the wrong one, and getting this
right up front saves months.

A camera can never see the whole game. It can't see your opponent's hand (and must not try —
that's cheating). It can't see what's left in a library, or that a creature already dealt
damage this turn. And a photo of a real table has overlapping cards, glare on foils, cards
rotated 90° because they're tapped, and a kid's elbow in frame.

So:

> **The app is a game-state tracker. The camera is a fast input method for that tracker,
> not an oracle.**

Three consequences that shape everything below:

1. **State is authoritative; scans are proposals.** Every scan produces a *diff* against the
   current state ("+2 permanents, 1 now tapped") that you accept or correct with one tap.
   Every piece of state is also editable by hand, always. The app is never stuck because the
   camera misread something.

2. **Constrain recognition to the cards you own.** Matching against a few hundred known cards
   is a different problem from matching against 110,000. This is the difference between "works
   in good light" and "works reliably at a dim table at an angle" — see §2 and §9.

3. **Identity is cheap; behaviour is expensive.** Knowing *which* card it is takes a week.
   Knowing what it *does*, well enough to enumerate legal plays, is the real work — and it's
   where an LLM earns its place, mostly at build time rather than at runtime (§8).

---

## 2. Card pool: Foundations first, any set later

We start with the **Foundations Beginner Box** (FDN) because it's what's on the table, but
*nothing in the engine is allowed to know that*. Sets are data; the engine is not.

### The Beginner Box

200 cards as **10 themed 20-card Jumpstart half-decks** — shuffle any two for a 40-card deck:
Cats (W), Healing (W), Vampires (B), Undead (B), Pirates (U), Wizards (U), Goblins (R),
Inferno (R), Elves (G), Primal (G). Cats and Vampires are pre-ordered for the tutorial and
aren't shuffled. Also: 2 reference cards, a reference guide, 2 how-to-play guides, 2 playmats,
2 spindown counters.

It's an ideal first target: a closed pool, one set, mechanically simple cards, and deck
registration is two taps from bundled decklists rather than a scanning problem.

### The collection model

Everything is keyed on **`oracle_id`, never on set + collector number.** A printing is
presentation; the *oracle card* is behaviour. Two printings of the same card are the same card
to the engine and must be, or every reprint becomes a bug.

```python
@dataclass(frozen=True, slots=True)
class Collection:
    sets: frozenset[SetCode]  # whole products you own
    extra_cards: frozenset[OracleId]  # singles from anywhere
```

The `Collection` scopes recognition, deck building, and the effect fixtures. Growing it is a
data operation, not a code change — with one bounded exception, below.

### What is set-specific, and what is not

| Layer | Set-specific? | Where it lives |
|---|---|---|
| State model, events, reduce, turn structure | **No** | `core/` |
| Mana solver, legality, combat, triggers | **No** | `core/` |
| The `Effect` union itself | **No** | `core/effects.py` |
| Card rows (name, cost, text, P/T) | Data | SQLite, from Scryfall |
| Precon decklists | Data | `data/sets/<code>/decks/` |
| Extracted effects + art hashes | Data | `data/sets/<code>/` |
| **New `Effect` variants, keywords, trigger conditions** | **Yes — code** | `core/`, rarely |

That last row is the true cost of adding a set, and it's the one people underestimate. A new
set may introduce a mechanic the engine has never seen (landfall, prowess, saga counters). So
we make that cost **measurable before you commit to it**:

```
mtgcoach sets add BLB              # ingest from Scryfall bulk
mtgcoach sets audit BLB            # → "312 cards. 9 mechanics, 3 unsupported:
                                   #    Offspring, Valiant, Forage. 27 cards affected."
mtgcoach effects extract --set BLB --only-owned   # Claude pass → proposals
mtgcoach effects review  --set BLB                # accept / edit / reject, one card at a time
mtgcoach effects seal    --set BLB                # write effects.json + signed manifest
mtgcoach pool enable BLB
```

`audit` answers "how much work is this set?" before you spend an evening on it. `extract
--only-owned` keeps the human review bounded to cards you actually have, not the whole set —
that's what makes this scale past the first box.

### Degrade per-card, never per-set

An unsupported mechanic must not disqualify a set. `Unmodeled` is **permanent infrastructure**,
not a temporary hatch: a card whose effect can't be modelled is still tracked, still recognised,
still countable in a library, still shown in hand — the coach just says "I don't fully
understand this one" and shows the card text instead of claiming a line. The test is
per-enabled-set and threshold-based ("zero `Unmodeled` in FDN", "≤ 5% in BLB"), not global.

---

## 3. Feature set

Ordered by value, not build order. Build order is §10.

### Tier 0 — Card knowledge (no game state needed)

- **Scan one card → plain-English explanation.** Cost, type, what every keyword means, *when*
  you're allowed to play it (sorcery vs. instant speed is the #1 beginner confusion), what it
  can target, common gotchas.
- **Two reading levels.** "Kid mode" and "precise rules wording." One toggle.
- **Official rulings** per card from Scryfall (WotC's own clarifications — far more useful than
  generic rules text).
- **Tappable keyword glossary** from anywhere.

### Tier 1 — Turn coach (the core product)

- **Phase/step walker.** Untap → Upkeep → Draw → Main 1 → Combat (Beginning / Declare Attackers
  / Declare Blockers / Damage / End) → Main 2 → End → Cleanup. Tap to advance; advancing
  auto-untaps, auto-draws, and fires reminders.
- **"What can I do right now?"**, recomputed at every step:
  - Cards in hand you can cast now — and for each one you can't, **why not** ("you need one
    more Forest", "that's a sorcery, only in your main phase").
  - Activatable abilities on the battlefield.
  - Which lands to tap — and, more usefully, **which to leave untapped** to keep an instant live.
- **Trigger reminders.** Forgetting triggers is the most common beginner mistake and this is
  nearly free once §7's effect model exists.
- **Attack advisor.** Which creatures *can* attack, and per candidate attack: what blocks, what
  trades, what gets through, whether it's lethal. Ranked, with the math shown.
- **Block advisor** when defending.
- **Warnings.** "If you tap out you can't respond." "Your only blocker dies here." "They have
  two burn spells left in their deck."

### Tier 2 — Scanning

- **Single card scan** — fast, high accuracy.
- **Board scan** — multi-card from one photo, tapped/untapped from orientation.
- **Hand scan** — one card at a time, or spread out. A fanned hand is genuinely hard; don't
  promise it.
- **Decklist import** — for sets beyond a precon: paste a text list, Arena export, or scan the
  deck once.

### Tier 3 — Teaching (the reason to build this at all)

- **"Why?" on every recommendation**, in language your son can read himself.
- **Quiz mode.** "Here's a board and a hand — what would you do?" Then compare and discuss.
- **Rules Q&A.** "Can he block my flying guy with that?" — grounded in the Comprehensive Rules
  and the actual cards on the board.
- **End-of-game review.** State is event-sourced, so replay is free: "here are three moments
  where a different play was stronger."

### Tier 4 — Table conveniences

Life counters with history, dice, turn timer, and **second-screen mode** — your son's tablet
shows his own coach without revealing your hand.

### Explicit non-goals

Not a full rules engine for all of Magic (that's XMage / Forge, ~20 years each). Not
tournament-legal. Not a replacement for reading the card. Not a thing that ever states a rule
to a kid with false confidence — see §8.

---

## 4. Architecture

**Python for everything correctness-critical; TypeScript only for rendering.**

The rules engine, the computer vision, and the API are Python — one strictly-checked language
for all the logic that can be wrong in a way that matters. The Android app and the web app are
deliberately dumb views: layout, gestures, and a WebSocket. No rules logic crosses into TS.

```
magic/
├─ packages/
│  ├─ core/          pure Python, stdlib-only — game state, rules engine, mana solver,
│  │                 combat simulator, effect model. No I/O, no network, no framework.
│  ├─ carddata/      Scryfall ingestion, set/collection management, SQLite, rules FTS
│  └─ vision/        card detection and recognition (OpenCV)
├─ services/
│  └─ api/           FastAPI — card DB, recognition endpoint, Claude adapter,
│                    authoritative game session, WebSocket sync
├─ apps/
│  ├─ mobile/        Expo (Android + tablet) — camera, at-the-table UI
│  └─ web/           Vite + React — big-screen board view on the laptop
├─ data/sets/<code>/ decklists, effects.json, manifest.json, art hashes  (per set)
├─ tests/            all Python tests, mirroring the package tree  (see §6)
├─ tools/            our own dev scripts  (scripts/ belongs to the review agent)
└─ docs/
```

`core` is the crown jewel: **no dependencies, no I/O, no framework, no knowledge of any set**.
It takes a state and an event and returns a new state. Everything that touches the outside
world — the card database, the camera, Claude — enters through a `Protocol`. That's what makes
100% coverage and property testing achievable rather than aspirational.

**Why a server:** it keeps the API key off devices, holds the authoritative `GameState` so
phone / tablet / laptop are views of one game, and lets the CV run in Python/OpenCV instead of
fighting the native Android vision toolchain. Run it on the laptop over LAN, or a Pi/small VPS
so opening the app is the only setup step.

**Sync:** clients send *events* (`{"type": "play_land", "instance_id": "..."}`); the server
reduces them into the authoritative state and broadcasts. No CRDT — there's one game and two
people sitting next to each other.

---

## 5. Engineering standards

These are gates, not aspirations. CI fails on any of them.

### Toolchain

| Concern | Tool | Setting |
|---|---|---|
| Packaging | `uv` | workspace, Python 3.12+ |
| Type check | `mypy` | `--strict`, plus `disallow_any_explicit`, `warn_unreachable` |
| Type check | `pyright` | `--strict` — run **both**; they catch different things |
| Lint + format | `ruff` | near-all rules on, `C901` complexity ≤ 8, `PLR0913` args ≤ 5 |
| Tests | `pytest` | with `hypothesis`, `pytest-cov` |
| Coverage | `pytest-cov` | branch coverage, per-package targets (below) |
| Mutation | `mutmut` | on `core` only, nightly not per-commit |
| Review | **multi-model-code-review-agent** | §6 — the outer loop |
| Hooks | `pre-commit` | ruff, mypy, file-length, pragma-allowlist |

### Small files, enforced

**≤ 200 lines per module, one concept per module.** Ruff has no file-length rule, so a ~20-line
`tools/check_file_length.py` in pre-commit and CI does it. The rule isn't aesthetic: small
modules keep `mypy --strict` errors local, make 100% branch coverage reachable per file, keep
mutation testing finite, and keep review-agent diffs small enough for four models to reason
about in one pass.

`core` looks like:

```
packages/core/src/mtgcoach/core/
├─ ids.py           NewType: OracleId, InstanceId, PlayerId, SetCode  (~20 lines)
├─ mana.py          ManaSymbol, ManaCost, cost parsing
├─ mana_solver.py   payment search
├─ cards.py         Card / CardFace — static data, set-agnostic
├─ effects.py       the Effect discriminated union
├─ keywords.py      Keyword registry + which are engine-supported
├─ permanents.py    Permanent
├─ zones.py         Hand / Library / Graveyard / Exile
├─ player.py        PlayerState
├─ state.py         GameState (frozen)
├─ steps.py         Step enum + turn order
├─ events.py        the Event discriminated union
├─ reduce.py        apply(state, event) -> state
├─ legality.py      can_cast / can_activate / can_attack
├─ triggers.py      trigger matching per step transition
├─ combat/
│  ├─ model.py      Attack / Block assignments
│  ├─ damage.py     damage assignment and ordering rules
│  └─ search.py     enumerate and rank attack plans
└─ options.py       TurnOptions — the engine's output contract
```

### Typing discipline

Beyond `--strict`, the things that actually buy correctness here:

- **`NewType` for every identifier.** `OracleId`, `InstanceId`, `PlayerId`, `SetCode` are not
  interchangeable strings, and the type checker will say so.
- **Discriminated unions + `assert_never` everywhere.** `Effect`, `Event` and `Step` are closed
  unions matched with `match`/`case` and closed out by `assert_never(x)`. Adding an effect kind
  for a new set then **fails the type check at every site that must handle it** — which is
  precisely the property that makes "support another set" a safe operation rather than a
  guessing game.
- **Frozen and immutable.** `GameState` and everything reachable from it are frozen dataclasses;
  transitions return a new state. Makes event sourcing trivial, property tests clean, and
  eliminates a whole category of aliasing bug.
- **`Protocol` for every boundary.** `CardRepository`, `Coach` (the LLM), `Recognizer`. `core`
  depends on protocols; adapters live in `services/api`.
- **Pydantic only at the edges.** The HTTP/WebSocket boundary uses Pydantic; `core` stays
  stdlib dataclasses. Generate TS client types from the OpenAPI schema rather than hand-writing
  them, so the views can't drift from the Python contract.

### Testing strategy and an honest coverage policy

Blanket "100% everywhere" is a lie you'd write `# pragma: no cover` to achieve. Per package:

| Package | Gate | Rationale |
|---|---|---|
| `core` | **100% line + branch**, no pragmas | Pure, deterministic, no I/O. No excuse for an uncovered branch. |
| `carddata` | **100%**, pragmas only for `if TYPE_CHECKING:` | I/O behind a protocol; network mocked. |
| `services/api` | **100%**, pragmas only for `if TYPE_CHECKING:` | Thin. Claude is behind `Coach` and always mocked. |
| `vision` | **100% on pure functions**; the OpenCV pipeline modules are pragma'd out | You cannot unit-test glare. Gated on accuracy instead (§9). |
| `apps/*` | strict TS, no coverage gate | Logic-free by design; a few Playwright/Detox smoke tests. |

`# pragma: no cover` is confined to an **allowlist of paths** checked in CI by
`tools/check_pragma_allowlist.py`. This is also exactly how the review agent's preflight audit
expects opt-outs to be expressed (§6), so the two tools agree rather than fight.

**Property tests (Hypothesis) — where the real bugs are:**

- *Mana solver:* if it returns a payment, applying it pays the cost exactly; if it returns
  `None`, a deliberately slow brute-force reference finds nothing either (metamorphic test); no
  returned payment taps a source it didn't need.
- *Combat:* damage is conserved; nothing dies with marked damage below its toughness unless
  deathtouch was involved; first-strike ordering respected; trample never assigns more than
  lethal before spilling over.
- *State machine:* **replaying the event log from the initial state always reproduces the
  current state** — the event-sourcing invariant, and the best property test in the suite. Plus
  card conservation: total cards across all zones is constant.
- *Effects:* every card in every enabled set round-trips text → `Effect` → text.

**Golden fixtures, per set.** `data/sets/<code>/effects.json` plus a `manifest.json` carrying
the card count and a SHA-256. Tests assert it parses, is exhaustively handled by every `match`,
and matches its manifest. Regenerating is a deliberate, reviewable diff — and the manifest is
registered with the review agent's deterministic audit (§6), which is the mechanism that
catches *set data drifting away from engine code*.

**Mutation testing on `core`.** 100% coverage proves lines ran, not that anything was asserted.
`mutmut` nightly is the gate that catches vacuous tests. Expect real holes the first run.

**The LLM is never in a correctness test.** It sits behind the `Coach` protocol, mocked
everywhere. Prompt quality is measured by a separate `evals/` suite — a dozen fixed board
states with expected recommendations — run by hand when the prompt changes, never in CI.

---

## 6. The review loop — multi-model-code-review-agent

[`pelednoam/multi-model-code-review-agent`](https://github.com/pelednoam/multi-model-code-review-agent)
runs four reviewers in parallel with clean context — security (Opus), correctness (GPT-5.5 via
Codex CLI), readability (Gemini), and spec-contract (Opus) — preceded by a deterministic
preflight audit, and optionally loops applying fixes until no blocking findings remain.

### Why it fits this project specifically

This isn't a bolt-on. Three of its mechanisms line up with decisions already made above:

1. **Its preflight runs `pytest --cov-branch` on changed files and feeds coverage gaps to the
   correctness reviewer, which converts them into runnable tests.** Our 100% policy stops being
   something I have to remember and becomes something the loop closes automatically:
   detect gap → write test → verify → gate → commit.
2. **Its spec-contract reviewer performs a deterministic audit of signed JSON manifests** —
   counts and SHAs. That is exactly the failure mode of a multi-set design: `effects.json` says
   312 cards, the set has 318, nobody notices. Registering each set's manifest makes set-data
   drift a blocking finding rather than a silent wrong answer at the table.
3. **Its mandatory gate is `ruff check` → `ruff format --check` → `mypy` → `pytest`** — the
   same four gates §5 already specifies. No reconciliation needed.

I review my own code with the same blind spots I wrote it with. A second Anthropic model plus
GPT-5.5 plus Gemini, each with no memory of the conversation that produced the code, is a
genuinely different signal.

### Installation — this step is yours, not mine

The agent's installer writes to `.claude/agents/`, which Claude Code is not permitted to modify.
**You run this from a terminal:**

```bash
git clone https://github.com/pelednoam/multi-model-code-review-agent.git
cd multi-model-code-review-agent
./install.sh /home/mmvt/projects/magic
```

Full mode wants the `claude`, `codex` and `gemini` CLIs installed; with all three it's free
across three provider families. Quick mode needs only Claude Code.

### Two layout constraints it imposes — accepted, and folded in above

- Its gate runs **`pytest tests/ -x -q`**, a literal path. So **all Python tests live in one
  root `tests/` tree mirroring the package structure** (`tests/core/…`, `tests/vision/…`)
  rather than per-package `tests/` directories. That's a fine layout with `src/` packages and
  it keeps coverage config central. Already reflected in §4.
- It installs its own helpers into **`scripts/`**, so our dev scripts live in **`tools/`** to
  avoid collision. Also already reflected in §4.

### Configuration

`scripts/preflight/config.py`, after install:

```python
SOURCE_DIRS = [
    "packages/core/src/",
    "packages/carddata/src/",
    "packages/vision/src/",
    "services/api/src/",
    "tools/",
]
TEST_DIRS = ["tests/"]
ARTIFACT_DIRS = ["data/sets/"]
COVERAGE_TARGET = 100

# A dict, not a list, and no glob support: one explicit entry per sealed set,
# added by `mtgcoach effects seal`. A configured-but-missing manifest counts as
# a warning, so this stays empty until M3 seals FDN.
SIGNED_MANIFESTS: dict[str, str] = {}   # "effects_FDN": "data/sets/FDN/manifest.json"
```

Three things the agent's source says that its README does not, each of which changed a
decision here:

- **`SIGNED_MANIFESTS` is a `dict[str, str]` of explicit paths**, not a glob list. Every set
  needs its own entry — a small chore per set, and the reason drift gets caught at all.
- **The preflight resolves changed files against `origin/main` with no fallback.** A branch
  whose base is not on the remote reports zero changed files and the coverage gate silently
  does nothing. (The reviewers' own diff collection *does* fall back to `HEAD~1`; the audit
  does not.) So: push the base branch before reviewing.
- **Its suspicious-pattern scanner flags `except Exception`, bare `except:`, and hardcoded
  `/home/` paths.** Worth knowing before writing them.

The gate's `mypy scripts/` needs repointing at our targets. `COVERAGE_TARGET` is global at 100,
which is why `vision`'s OpenCV pipeline uses the pragma allowlist from §5 — the agent's
per-file opt-out and our allowlist check are the same mechanism viewed from two directions.

### Cadence

| When | Mode | Command |
|---|---|---|
| Every commit | Quick (2 subagents, ~30 s) | "review this" in Claude Code |
| End of each milestone | Full ensemble (4 reviewers, 3–5 min) | "full review" |
| Anything touching `core`, the mana solver, or combat | Convergence loop | `python scripts/review_until_converged.py --repo . --max-rounds 5 --auto-commit` |
| Every push | CI, single round | `--max-rounds 1` |

Relevant exit codes for CI: `0` converged, `2` stuck (identical blocking findings twice), `4`
mandatory gate failed, `6` max rounds, `7` no reviewer results (auth/network), `8` secrets found
in the diff. The diff scrubber blocks on credential patterns before anything reaches a model.

Evidence lands in `data/reviews/<timestamp>_<branch>/round-N/` — keep it out of git via
`.gitignore` but keep it on disk; the audit trail is useful when a reviewer and I disagree.

### Honest limits

It reviews **git diffs of code**. Two consequences worth knowing:

- **It is not a document reviewer.** `docs/PLAN.md` changes do appear in a diff and the
  spec-contract reviewer consumes specs as context — so the plan functions as *the contract the
  code is reviewed against*, which is arguably more valuable than having it critiqued. But
  "review the plan" isn't a first-class mode; don't expect a design critique from it.
- **It won't re-review unchanged code.** A design flaw that shipped in M1 stays invisible in M5.
  Mitigation: the end-of-milestone full review runs against the whole milestone's accumulated
  diff, not just the last commit.

Full mode costs 3–5 minutes of wall clock. That's cheap at milestone boundaries and too slow
per-commit, hence the cadence split.

---

## 7. The rules engine (`packages/core`)

The full Comprehensive Rules are ~250 pages; nobody should implement them. The way through:
model the mechanics your enabled sets actually use, exactly, and degrade honestly on the rest.
The Beginner Box uses maybe 25 distinct mechanics — a realistic target for genuine 100%
coverage of what's in the box, and a foundation each later set extends rather than replaces.

### State model

Frozen dataclasses, one per module:

```python
@dataclass(frozen=True, slots=True)
class GameState:
    turn: int
    active_player: PlayerId
    step: Step
    players: Mapping[PlayerId, PlayerState]
    stack: tuple[StackObject, ...]


@dataclass(frozen=True, slots=True)
class PlayerState:
    life: int
    hand: tuple[CardInstance, ...]  # opponent: count + what's known from their decklist
    battlefield: tuple[Permanent, ...]
    graveyard: tuple[CardInstance, ...]
    library: Library  # count + known remaining
    lands_played_this_turn: int
```

**Event-sourced.** Store the event log, derive state via `reduce.apply`. Free undo, free replay,
free end-of-game review, and the strongest property test in the suite. Costs nothing now,
painful to retrofit.

### Four solvers

**1. Mana solver.** Given untapped sources and a cost like `{2}{G}{G}`, can you pay — and *how*?
Bipartite matching (sources → pips), complicated by dual lands, hybrid, and "any colour"
producers. With ≤ 12 sources, backtracking is instant. Return **all** valid tappings, ranked to
preserve future flexibility — "tap these three, keep the Island up" is coaching, not legality.

**2. Timing & legality.** Sorcery speed (your main phase, empty stack) vs. instant speed; one
land per turn; summoning sickness for attacking and for `{T}` abilities; whether a legal target
exists right now.

**3. Combat simulator.** The highest-value component, and what humans get wrong most. With ≤ 8
creatures, brute-force every attack subset (256) and the opponent's best blocking assignment
for each. Handle first strike, double strike, deathtouch, trample, flying/reach, menace,
indestructible, lifelink, vigilance, ward. Output per plan: damage through, creatures lost each
side, life swing, lethal or not.

**4. Trigger scanner.** At each step boundary, walk the battlefield for triggers matching the
transition. Falls out of the effect model.

### The effect model — and the best use of an LLM in this project

What cards *do*, as a closed discriminated union — not free text:

```python
type Effect = (
    DealDamage | Destroy | Draw | GainLife | PumpUntilEOT | CreateToken | Counter | Unmodeled
)
```

**Populated by a build-time Claude pass, reviewed by a human, committed as data.** `claude-opus-5`
reads each owned card's oracle text once and proposes structured JSON; `mtgcoach effects review`
walks you through accepting, editing or rejecting each one; `seal` writes the fixture and its
signed manifest. Exactly the right division of labour: the LLM does the hard
natural-language→structure conversion *once*, offline, where it's cheap and reviewable; runtime
stays deterministic, fast, offline, free, and testable.

This is a **repeatable pipeline, not a one-off** — that's what makes set #2 an evening rather
than a rewrite. Bound the human pass with `--only-owned` so you review the cards in your
decks, not all 300 in the set.

---

## 8. The Claude layer

**The engine decides what's *legal*; Claude decides what's *wise* and explains it in words a
kid understands.** Claude is never the source of truth for rules, and never appears in a
correctness test.

It enters `core` as a protocol:

```python
class Coach(Protocol):
    async def advise(self, state: GameState, options: TurnOptions) -> Advice: ...
```

### Call shapes

**Turn coach** — `claude-opus-5`, `thinking={"type": "adaptive"}`,
`output_config={"effort": "medium"}`, structured output. Input: compact state JSON + the
engine's enumerated options + oracle text for cards in play. Output: recommendation, reasoning,
alternatives, warnings, kid-language explanation.

**Rules Q&A** — `claude-opus-5` with tool use: `lookup_card`, `search_rules` (FTS over the
Comprehensive Rules), `get_state`, `simulate_combat`. Make it *call* the simulator rather than
do arithmetic in its head.

### Cost, and how to keep it near zero

Opus 5 is $5/$25 per MTok in/out; cache reads are ~10% of input.

- **Prompt-cache the stable prefix.** System prompt + both registered decklists is ~12k tokens
  and identical all game — an ideal caching shape. Volatile state goes after the last
  breakpoint.
- Per-turn coach call ≈ $0.03. A 15-turn game ≈ $0.45.
- **Default to engine-only.** The deterministic panel is always on, instant, offline and free.
  Claude fires on an explicit "Coach me" / "Why?" tap.
- **Precompute everything not about the live board.** Card explanations, kid-mode text and the
  effect fixtures are generated once per card and cached forever, keyed by `oracle_id` — so a
  reprint in a later set costs nothing.
- Stream the coach response.

### The honesty requirement

This is teaching a child; a confidently wrong rule is worse than no answer. If the engine hits
an `Unmodeled` effect, say so and show the card text. If a suggestion depends on an interaction
the engine can't verify, label it "check this one" and cite the rule number. Never present a
probabilistic recognition result as certain — show the alternatives.

---

## 9. Card data and recognition

### Data

[Scryfall](https://scryfall.com/docs/api), free and no key. Download the `default-cards`
[bulk file](https://scryfall.com/docs/api/bulk-data), filter to enabled sets, build SQLite with
FTS5 on names. FDN alone is ~2 MB including art hashes — bundle the enabled pool, lazy-fetch
strays from the live API and cache them forever by `oracle_id`. Respect the
[rate limits](https://scryfall.com/docs/api/rate-limits) (50–100 ms between calls, 500 ms for
`/cards/collection`) and send a descriptive `User-Agent`. **Never construct image URLs** — read
them from `image_uris`; those hosts have changed before.

Fields that matter: `oracle_id`, `name`, `mana_cost`, `cmc`, `type_line`, `oracle_text`,
`power`, `toughness`, `keywords`, `colors`, `produced_mana`, `layout`, `card_faces`,
`image_uris.art_crop`, `rulings_uri`.

**Handle `layout` and `card_faces` from day one.** Foundations has few double-faced cards,
adventures or split cards; other sets are full of them. Modelling a card as
"one face" is the retrofit that hurts most when set #2 arrives.

Also ingest WotC's Comprehensive Rules `.txt`, chunked by rule number into the same SQLite with
FTS5. No vector DB needed at this scale.

### Recognition

**Stage A — find the cards.** Grayscale → adaptive threshold → `findContours` →
`approxPolyDP` keeping 4-corner polygons → filter by area and aspect ratio (a Magic card is
63 × 88 mm = **0.716**, or 1.397 tapped) → perspective-warp to a canonical 488 × 680.
Tapped/untapped falls out of quad orientation for free. Entirely set-agnostic.

**Stage B — identify**, always scoped to the `Collection` first, global index second:

1. **Art perceptual hash** — crop the art box (≈ x 7.5–92.5%, y 11.5–62% of a modern frame;
   calibrate against Scryfall's `art_crop`, which is exactly that region), dHash-64 + pHash-256,
   Hamming-match. The path that works on whole-board photos where text is too small.
2. **Title OCR** — crop the top ~9%, Tesseract, fuzzy-match with `rapidfuzz` against the name
   index. Best for single-card scans, and better for foils where glare kills the art but the
   title still reads.
3. **Claude vision fallback** — below a confidence threshold, send the crop plus candidate
   names. Fractions of a cent, rescues bad lighting. Safety net, never primary.

**Scaling past one set is a real design constraint, not an afterthought:**

- A few hundred cards: linear Hamming scan is fine.
- A few thousand (several sets): **BK-tree over Hamming distance**, built at pool-enable time.
- Whole-Scryfall fallback (~110k arts): same BK-tree, but **the match threshold must tighten as
  the pool grows** — a distance that's decisive among 200 candidates is a coin flip among
  100,000. Make the threshold a function of pool size and *measure* it rather than guessing.
- Reprints share art across sets. That's fine and actually helpful: we resolve to the **oracle
  card**, and behaviour is identical regardless of printing.

Every identification carries a confidence. Below threshold, the UI shows the **top three
candidates as tappable chips** rather than guessing — one tap to fix beats a wrong answer. Cards
recognised from outside the `Collection` are flagged visibly with reduced confidence.

**Accuracy suite, not line coverage.** A fixture corpus of real photos from your table (good
light, dim, angled, tapped, overlapping, foil) with expected outputs. CI gates on top-1 accuracy
≥ 95%. Every recognition bug you hit in a real game becomes a new fixture. Re-run the suite when
a new set is enabled — that's how you find out the threshold needs retuning.

**Capture UX beats algorithms.** An on-screen frame, "hold the phone flat above the board", one
row at a time — worth more than any amount of tuning.

---

## 10. Build order

Each milestone independently useful. The camera is not first. Every milestone ends with a full
ensemble review (§6) before the next begins.

| # | Milestone | Why |
|---|---|---|
| **M0** | `git init`; `uv` workspace; the full §5 toolchain failing-on-violation from commit one; review agent installed and configured. | Standards and the review loop are free on day one, expensive to retrofit. |
| **M1** | `core`: state model, events, `reduce`, step walker. 100% + property tests. | The spine. No UI needed to test it. |
| **M2** | `carddata`: Scryfall ingestion, `Collection`, the `sets add / audit` commands, FDN decklists as data. | Establishes the set-agnostic data layer before any set-specific work exists to bias it. |
| **M3** | Effect extraction pipeline + review CLI + FDN golden fixture and signed manifest. Card explainer CLI. | Useful immediately; proves the build-time Claude pattern *and* the multi-set pipeline in one go. |
| **M4** | Mana solver, legality, trigger scanner, combat simulator. Hypothesis suites. Convergence-loop review. | The engine. This is what makes it a coach rather than a notepad. |
| **M5** | FastAPI + WebSocket; Expo app as a **manual** tracker (tap cards in from your decklist). | **Probably 70% of the total value.** Ship before touching the camera. |
| **M6** | Claude coach + rules Q&A over M4's output. | Turns correct answers into understandable ones. |
| **M7** | Single-card scan, then board scan → state diff → one-tap accept. Accuracy corpus. | The original ask, now with a tracker behind it to correct mistakes. |
| **M8** | Web view on the laptop; teaching features — quiz mode, end-of-game review, son's tablet view. | The reason to build this instead of buying a rules app. |
| **M9** | Enable a second set end-to-end as a **test of the abstraction**, not a feature. | If set #2 takes an evening, the design held. If it takes a week, we learn exactly where. |

M0–M5 is a genuinely useful tool. Everything after is upside.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Whole-board recognition is hard — overlap, glare, angle | Collection-scoped pool, guided row-by-row capture, editable diff, confidence chips. M7 is late so nothing is blocked on it. |
| Hidden information — you can't know their hand | Model as uncertainty. You know their decklist, so "two burn spells left" is computable. |
| Set #2 turns out to be a rewrite | `sets audit` quantifies the cost before you start; `assert_never` makes the compiler list every site a new effect kind must touch; M9 tests the abstraction deliberately. |
| Set data drifts from engine code | Signed per-set manifests audited deterministically by the review agent's preflight (§6). |
| 100% coverage becomes theatre | Mutation testing on `core`; pragma allowlist; `vision` gated on accuracy instead of lines; the review agent turns coverage gaps into real tests. |
| Recognition accuracy silently degrades as the pool grows | Pool-size-dependent threshold, re-run the accuracy corpus on every `pool enable`. |
| Scope creep toward building XMage | The non-goals in §3. Revisit when tempted. |
| Server must be running to play | Pi or small VPS with a systemd unit, so opening the app is the only step. |

---

## 12. Legal / etiquette

- **WotC [Fan Content Policy](https://company.wizards.com/en/legal/fancontentpolicy):**
  noncommercial only, must state it's unofficial and not endorsed by Wizards, no WotC logos or
  trademarks in the branding. Free and personal is fine.
- **Scryfall:** stay under the rate limits, use the bulk files, send a real `User-Agent`, don't
  redistribute a card-image archive. Art is WotC's copyright.
- **No opponent-hand features, ever.** Not because it's hard — because it's cheating, and the
  point of this is teaching your son to play well.

---

*Unofficial Fan Content. Not approved or endorsed by Wizards of the Coast.*
