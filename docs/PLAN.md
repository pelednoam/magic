# Magic Coach — design & implementation plan

An assistant for learning Magic: The Gathering at the kitchen table. Point a phone at a card
or at the board, and get a clear answer to *"what can I do this turn, and what should I do?"*

**Status:** M0–M6 merged to `main`.

The engine is done — **52% of the Beginner Box fully modelled**, eleven keywords — and the
tracker works end to end: `packages/coach` turns the four solvers into a turn report,
`services/api` holds the authoritative game over HTTP and a WebSocket, and `apps/mobile` is a
two-seat Expo client for Android, tablet and the browser. M4 took four rounds of ensemble
review and M5 two, with every finding fixed by hand.

M6 is built, on `m6`, and both halves check themselves:

- The **turn coach**. `coach/advice.py` says what an explanation may be and checks every one
  against the engine; `coach/briefing.py` builds the prompt out of the engine's own report.
- **Rules Q&A**. `packages/rules` parses the Comprehensive Rules into a few thousand quotable passages
  and indexes them in SQLite FTS5. A question is searched *first*, the passages go into the
  prompt verbatim, and an answer citing anything else is refused.

Both ask Claude through the local CLI, so neither spends API credits. Both are buttons, never
automatic. The app shows a refusal as a refusal, and shows the retrieved rules whatever the
model said. 1173 Python tests at 100% line and branch, 74 TypeScript tests; the file-length
gate now covers the TypeScript too.

One round of ensemble review, four models, eight blocking findings, all fixed by hand. The two
that mattered most were both about the same thing — the rules question box is unauthenticated
text that ends up inside a prompt:

- The subprocess was given a *deny-list* naming the write tools, so Read, WebFetch and Task
  stayed enabled. Verified exploitable before fixing: the same prompt with tools on read
  `/etc/hostname` and returned it. It is now `--tools ""`, an allow-list of nothing.
- The QUESTION fence was a fixed marker, so a question containing that marker closed it.
  It now carries a per-request random tag, and marker-shaped text is broken up first.

Two more were about honesty rather than security, and both were the checker claiming more
than it had checked: `unsure` used to excuse an answer from citing anything, and the wire
called the result `trusted` when all that had been verified was that the citations were real.
The rules route now reports `cited`, and the app says the rules below are the source.

A second round found five more, and one of them was the worst bug in M6:

- **The rules parser dropped every unnumbered line.** Rules carry continuation paragraphs and
  211 of them carry an `Example:`, which for a beginner is often the only usable part. A
  passage labelled verbatim was quietly incomplete — the single worst thing to be wrong about
  in a design that rests on quoting the rules rather than remembering them.
- `start_new_session=True` does *not* make `subprocess.run` kill a process tree: `run` signals
  the direct child and never the group. The comment claimed otherwise. It is `Popen` and an
  explicit `killpg` now.
- The parse-failure message quoted 160 bytes of raw stdout back to any origin, undoing the
  stderr scrubbing two lines above it.
- The subprocess ran in the shared temp directory, where any local user could leave a
  `CLAUDE.md` for the CLI to read as instructions. It gets a private 0700 directory.
- Nothing checked that the CLI still *accepts* the flags — the tests stub the subprocess, so a
  renamed flag would 503 every request in production with the suite green. `tools/check_cli_flags.py`
  reads `claude --help` on every gate run.

And the client half of the safety story now has tests: `tests/hooks.test.tsx` renders the two
hooks into a real DOM and pins the rule that an answer arriving after the board moved is
dropped rather than displayed.

A third round found one critical — and it was the same bug wearing a different hat. Stopping
the no-decision *shortcut* passing over a firing trigger left the other path open: the model
was asked, said "pass the turn", and nothing in `verify` required it to mention the trigger
either. `checks.triggers` closes it. The rest of that round was smaller but the same flavour
of honest: "attack with nobody" was exempt from the options check (the one piece of combat
advice a beginner hears most often, and nothing checked it), a slow answer was not bound to
the revision it described, and a card with rules text was described to the model as though it
were vanilla.

A fourth round caught the other half of that same fix, and it would have broken the feature
outright: `checks.triggers` demanded that every firing trigger be named, and the prompt never
asked for it. A requirement nobody is told about is not a requirement, it is a trap — every
turn with a trigger on the table would have come back as a refusal. Alongside it: the
no-decision shortcut said "pass the turn" at an *upkeep*, which for a beginner means skipping
their main phase; the silence checks matched card names as substrings, so a card called "Rat"
counted as mentioned by the word "strategy"; and the process-group kill asked a reaped child
for its group id, which is both too late and a pid-reuse race.

The two Claude routes are also rationed — twelve a minute, three at once. Not a security
boundary even now that there is a token: it is about the failure that needs no attacker, which
is a stuck finger on a button that starts a Node process and spends a subscription.

A fifth round found the one that could have taken the server down. `os.getpgid` was asked for
the child's process group immediately after `Popen` returned — but `setsid` runs *in the
child*, after the fork the parent has already returned from, so a call that won that race read
the group the child **inherited**: the server's own. The `finally` then `SIGKILL`ed it, on an
ordinary coach request. There is no need to ask at all — a process that calls `setsid` leads a
group numbered after its own pid — and `kill_group` now refuses to signal this process's group
whatever it is handed.

Also from that round: the prose beside a checked choice was itself unchecked, so
`play=""` with "cast the Dragon" in `in_short` passed and displayed; a truncated rules
download that happened to carry the four markers was indexed and advertised as the
Comprehensive Rules; and the client's staleness was keyed on a version number that restarts at
zero for every game.

A sixth round found a bug introduced by the fifth round's own fix — two reviewers
independently — and that is the clearest argument for running the loop at all. The no-match
answer was labelled `version: 0`, so the client compared it against the real board version and
silently dropped it; the app also rendered it as *"the answer did not stay inside the rules"*
over an answer that had never left them. The wire carries `matched` now.

Two more from that round were about not doing harm on the way out: a reaped process group must
never be signalled, because its pid is free to belong to somebody else by then, and no test may
signal a group at all — the stand-in processes carry pid 4242, which on any real machine is
very likely somebody's.

Round seven reviewed the two gap fixes and found eight more; round eight reviewed *those* and
found nine, three of which were the same one — **a live server token committed to the
repository**. `data/token` was added in the commit that introduced the token, before the
`.gitignore` entry existed, so the ignore rule never applied. The scrubber missed it too: it
matches credential *patterns*, and a bare 43-character base64url blob in a file called `token`
matches nothing at all — there is no `token =` for a keyword pattern to see and no vendor
prefix for a shape pattern to see. It exited 0 and called the diff clean, so the value went to
four model providers. The reviewers finding it is the only reason anybody knew.

Fixed three ways: the value was rotated (the file is gone, and the next start makes a new one),
the ignore rule now applies because nothing is tracked, and the scrubber redacts a file that is
*entirely* a credential by path rather than by content — [PR #12] upstream, with the leak
itself as a test. **The commit is still in local history** and wants a rewrite before any push;
that is the one thing here left undone.

The other five from that round: a reply missing `play` or `attack` became an explicit "do
nothing", which the engine agrees with whenever holding back is right — so the server put
`trusted` on a choice the model never made; `Rationed`'s `_tokens` defaulted to the module
constant rather than the instance's `burst`, correct only because `_afford` clamps elsewhere;
`has_more` being absent or non-boolean read as "that was the last page", which is a short
download that imports cleanly; and the startup line printed `0.0.0.0` as `localhost`, which on
a phone is the phone.

Eight rounds, ninety-odd findings fixed by hand. The critical count went 8, 5, 1, 5, 5, 8, 8,
9 — not monotonic, because each round's fixes are the next round's subject. What changed is the
kind: round one found a live file-read exploit, and round eight found the secret the review
itself had leaked.

[PR #12]: https://github.com/pelednoam/multi-model-code-review-agent/pull/12

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
understand this one" and shows the card text instead of claiming a line.

**Coverage is measured, not promised.** An earlier draft of this plan said the target for
Foundations was zero `Unmodeled`, asserted by a test. Having extracted all 124 cards, that was
wrong and should not have been written: **52% of the box is fully modelled** (65 of 124), and
the rest are replacement effects, intervening-if triggers, modal spells and granted abilities —
real Magic complexity, not a shortfall in effort. The manifest records the number and `effects
check` audits it, so the claim is a fact about the sealed data rather than a line in a
document. It first read 73%, because the check looked only for unmodelled *abilities* and
missed unmodelled *effects* nested inside modelled ones; that is exactly why the number is
audited now.

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
│  ├─ coach/         the turn report: the four solvers assembled into one answer.
│  │                 Takes card data through a Protocol, so it holds none either.
│  ├─ carddata/      Scryfall ingestion, set/collection management, SQLite, rules FTS
│  └─ vision/        card detection and recognition (OpenCV)
├─ services/
│  └─ api/           FastAPI — card DB, recognition endpoint, Claude adapter,
│                    authoritative game session, WebSocket sync
├─ apps/
│  ├─ mobile/        Expo (Android + tablet + web) — camera, at-the-table UI
│  └─ web/           M8: a big-screen laptop view, if Expo's web target is not enough
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

Built in M5, and four things about it are worth writing down:

- **The log is the game.** A session holds its event log and carries the derived state as a
  *cache*; `Session.consistent` replays from the start and asserts the two agree. Undo replays
  the log minus one event rather than inverting the last one — an undo that computes the
  opposite of an event is a second implementation of the rules, and the second one is always
  the one that is wrong.
- **The wire shape is written by hand** (`api/views.py`), not serialised from the engine's
  types. A `Creature` carries a `Permanent` carrying a `CardInstance`; dumping that would put
  the engine's shape on the wire and make every refactor a client change. Every library is a
  *count*, never a list — a tracker that shows you the top of a deck is a cheating tool.
- **The API closes a hole `core` documented.** `PlayLand`'s docstring says the reducer cannot
  tell whether the card is a land, because `core` holds no card data, and that the check
  "arrives with the card database". `api/guard.py` is that check. An *unmodelled* card is
  still allowed through, because at 52% coverage refusing what we cannot identify would make
  the tracker unusable — and the player can see their own card.
- **Advice goes to both players in every payload.** One screen at a kitchen table: the person
  defending needs the block advice as much as the attacker needs the attack advice.

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
| Hooks | `pre-commit` | ruff, file-length, pragma-allowlist — **not** mypy/pyright/coverage; a slow hook is a disabled hook, and CI runs the full set |

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
├─ cards.py         CardInstance — one physical card in one game
├─ errors.py        IllegalEventError
├─ movement.py      remove / add / move a card between zones
├─ turn.py          step advancement and turn-based actions
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
| `coach` | **100%**, pragmas only for `if TYPE_CHECKING:` | Pure too: card data arrives through a Protocol. |
| `carddata` | **100%**, pragmas only for `if TYPE_CHECKING:` | I/O behind a protocol; network mocked. |
| `services/api` | **100%**, pragmas only for `if TYPE_CHECKING:` | Thin. Claude is behind `Coach` and always mocked. |
| `vision` | **100% on pure functions**; the OpenCV pipeline modules are pragma'd out | You cannot unit-test glare. Gated on accuracy instead (§9). |
| `apps/*` | strict TS, no coverage gate | Logic-free by design. Unit tests for the two modules that *are* logic — the client and the display formatting — and nothing for the components, which are layout. |

`# pragma: no cover` is confined to an **allowlist of paths** checked in CI by
`tools/check_pragma_allowlist.py`. This is also exactly how the review agent's preflight audit
expects opt-outs to be expressed (§6), so the two tools agree rather than fight.

**End-to-end, added in M5** (`tests/e2e/`). Nothing fake below the HTTP client: cards come out
of the real Scryfall reader into a real SQLite store, their behaviour out of the signed FDN
fixture, the rules out of `core`, the advice out of `coach`, reached over real HTTP and a real
WebSocket. The unit tests say each piece is right; these say they are the *same* pieces — that
an oracle id the extractor wrote is the one the store hands back, and that a `{T}: Add {G}` a
model proposed and a person accepted becomes a Forest the mana solver will tap.

The cost is one fixture (`tests/fixtures/scryfall_fdn_playable.json`): Scryfall-shaped records
for seven cards whose oracle ids are taken from the sealed file, so both halves line up. The
committed `scryfall_fdn_sample.json` does not overlap the sealed set at all, which is worth
knowing — the two fixtures exist for different jobs.

Reading a response under `mypy --strict` and `pyright --strict` needs help, because the honest
type of decoded JSON is a recursive union and every index has to prove what it indexed was a
mapping. `tests/wire.py` narrows once, loudly, with the path it was walking in the error — so
it checks the wire format as much as it reads it. Starlette's `TestClient` is not typed well
enough for strict pyright, and every module that touches it says so in a file-level
suppression with a reason, rather than the gate being weakened everywhere.

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

**Nothing may be invisible to the gate.** coverage.py finds unexecuted files by walking the
source directories, but it will not descend into a directory without an `__init__.py` — and a
PEP 420 namespace package has none. A module no test imported was therefore not reported as 0%
but not reported *at all*, and the run still passed at "100%". `tests/test_imports.py` imports
every module so that an unimported file becomes a traced file and its uncovered lines count.

**Mutation testing on `core`.** 100% coverage proves lines ran, not that anything was asserted.
`mutmut` nightly is the gate that catches vacuous tests. Note that `mutmut run` exits 0 with
survivors and `mutmut results` only prints, so `tools/check_mutation_survivors.py` turns the
report into something that can actually fail.

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
   four of the seven gates §5 specifies, in the same order. The three it does not run —
   pyright, the module-length limit and the coverage opt-out allowlist — are CI's job, so a
   clean convergence round is necessary but not sufficient for a green build.

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
SIGNED_MANIFESTS: dict[str, str] = {}  # "effects_FDN": "data/sets/FDN/manifest.json"
```

Three things the agent's source says that its README does not, each of which changed a
decision here:

- **`SIGNED_MANIFESTS` is a `dict[str, str]` of explicit paths**, not a glob list. Every set
  needs its own entry — a small chore per set, and the reason drift gets caught at all.
- **The preflight used to resolve changed files against `origin/main` with no fallback**, so a
  branch whose base was not on the remote reported zero changed files and the coverage gate
  silently did nothing. Fixed upstream in
  [#4](https://github.com/pelednoam/multi-model-code-review-agent/pull/4); the audit now falls
  back to `HEAD~1` like the reviewers' own diff collection always did.
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

Evidence lands in `data/reviews/loop_<timestamp>/round-N/` — keep it out of git via
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


@dataclass(frozen=True, slots=True)
class PlayerState:
    library: tuple[CardInstance, ...]
    hand: tuple[CardInstance, ...]
    battlefield: tuple[Permanent, ...]
    graveyard: tuple[CardInstance, ...]
    exile: tuple[CardInstance, ...]
    life: int = STARTING_LIFE
    lands_played_this_turn: int = 0
```

Two decisions in that shape are worth stating, because an earlier draft of this plan assumed
otherwise:

- **The engine holds the true state, hidden zones included** — not "a count plus what is known
  of the opponent's decklist". Redacting a library or a hand is a *view* concern: a thin layer
  redacts the state on its way to a given player's screen. Keeping the engine fully informed is
  what makes card conservation checkable and avoids a "we do not know" special case in every
  legality question. The opponent-knowledge reasoning the coach needs (§3's "two burn spells
  left in their deck") is computed from their registered decklist, not from a deliberately
  impoverished state.
- **There is no `stack` field yet.** Nothing can put an object on one until spells can be cast,
  and a field no event can change is a field no test can cover. M4's legality layer already
  marks the one check this costs (the empty-stack half of CR 117.1a) at the site that will need
  it. It arrives with spell casting, alongside `counters` and attachments on `Permanent`.

**Event-sourced.** Store the event log, derive state via `reduce.apply`. Free undo, free replay,
free end-of-game review, and the strongest property test in the suite. Costs nothing now,
painful to retrofit.

### Four solvers

All four are built (M4), and each one turned out to have a lesson in it.

**1. Mana solver** — `manacost.py`, `manasolver.py`. Given untapped sources and a cost like
`{2}{G}{G}`, can you pay — and *how*? Returns **all** valid tappings, ranked
fewest-lands-tapped then most-colours-spare, because "tap these three, keep the Island up" is
coaching and a boolean is not.

The search enumerates *sets* of sources and tests each for a perfect matching (Kuhn's
algorithm), rather than enumerating assignments of sources to pips. The first version did the
latter and was factorial: five coloured pips across sixteen sources is 525K ordered assignments
against 4,368 sets, and the answers are identical because a payment is a set of lands to tap —
which land paid for which pip is not something a player can act on. `can_pay` stops at the
first payment, so a *castable* spell is cheap to confirm. The expensive case is the failing one
— nothing to stop at, and the whole space scanned — and that is exactly what `legality` asks
about for every card in hand, so the bound is `MAX_SOURCES` rather than a bound on payments
found. Two sources sharing an identifier are refused outright: one permanent cannot be tapped
twice, and letting it pay twice over offered a spell that could not be cast.

`parse` refuses what it cannot model rather than approximating: `{2/W}` and `{W/P}` raise
`UnsupportedCostError`, and so does a split card's joined `{3} // {1}{B}` — that card has two
costs, and silently picking one would misprice whichever half you didn't cast. A hybrid cost
read as generic would do the same, and the whole point of this layer is that its answers can
be trusted.

Neither hybrid form appears on the 124 box cards; that was checked at extraction time against
the imported set. There is a standing test over the eight-card Scryfall sample — every
per-face cost in it parses, and the symbols come back out — but **not over the other 116**,
because no committed fixture carries their costs: `effects.json` holds abilities and the
decklists hold names. Committing the box's costs would close the gap, and is worth doing when
the bulk data is next downloaded.

**2. Timing & legality** — `legality.py`. Built the other way round from the usual: the
primitives are `why_not_cast`, `why_not_play_land`, `why_not_declare_attackers` and
`why_not_attack`, each returning *reasons*, and the booleans are the empty-reasons case.
"You can't cast that" teaches nothing; "you need
one more Forest" and "that's a sorcery, so only in your main phase" are the two sentences a
beginner needs most, and a rules engine usually throws them away on the way to a boolean.

Attacking is two questions, not one. `why_not_declare_attackers(state, player)` is about the
clock (CR 508.1a) and is asked once; `why_not_attack(permanent, card)` is about a creature and
is asked once per creature. Folded together they answered a confident "yes, Grizzly Bears can
attack" during its controller's upkeep. A card with no printed mana cost is refused too
(CR 202.1a) — a different thing from a cost of `{0}`, though both parsed identically until
they were split.

Two refusals here are exceptions rather than reasons, deliberately: more untapped sources than
the solver will search, and two sources sharing an identity. A reason is something the player
can act on; these say the *question* was malformed or too large, which is the caller's problem,
and answering "you can't cast that" would be a lie.

Mana failures are diagnosed rather than reported: a `{C}` pip nothing can make, too few
sources, no source of a colour, or — the awkward one — enough sources of the right colours
that still cannot be assigned. "No source of a colour" counts only single-colour pips: a
hybrid `{W/U}` demands neither in particular, and naming one as missing is the wrong lesson.

Untap and cleanup are refused outright (CR 502.4, 514.3): no player gets priority there, so an
instant that reads as castable during untap is not a harmless approximation, it is the one
moment when "hold your Giant Growth" is wrong.

One check is deliberately missing. CR 117.1a also requires an empty stack for sorcery speed,
and `GameState` has no stack, because nothing before casting can put an object on one and a
field no event can change is a field no test can cover. `_sorcery_timing` is the site that will
need it, and says so.

**3. Combat simulator** — `combat/`. Brute-force every attack subset against the defender's
best blocks, and within each of those the attacker's best assignment of damage. This is the
component that produced the most bugs, every one of them found by a test written for behaviour
that looked obviously right:

- damage within a step was applied as it was computed, so a blocker killed by an earlier
  attacker never struck back. A 5/5 survived a 1/1 with deathtouch. Damage in a step is
  simultaneous (CR 510.2); the fix collects every hit before applying any.
- the blockers' damage loop was nested inside the attackers' loop, so an attacker that skipped
  the regular step (first strike) skipped its blockers' damage too. A 2/2 first striker
  survived a 5/5. The two directions are now independent loops.
- a blocked attacker whose blockers all died in the first-strike step looked *unblocked* in the
  regular step and hit the player. CR 509.1h: blocked is blocked. This turned a double striker
  into an unblockable one.
- without trample the attacker assigned its whole power to the first blocker, so a 4/4 blocked
  by two 1/1s killed one of them. Lethal is owed to each blocker it wants to kill (CR 510.1c).
- which blocker took the damage was the caller's list order rather than the attacking player's
  choice, so the same board coached differently depending on how it was passed in.
- lifelink was modelled for attackers only, though `SUPPORTED_KEYWORDS` claimed it flatly. A
  blocking lifelinker gains the *defender* life, which can make a lethal attack survivable.
  `Outcome` now tracks both sides.
- a defender reduced to zero by first strike came *back* if a lifelink blocker dealt damage in
  the regular step. State-based actions are checked between them (CR 704.3), so `resolve` needs
  the life total and stops when it reaches zero.
- a blocker whose attacker died in the first step went on dealing damage to it — and, with
  lifelink, on gaining life for hitting a creature that was no longer there.
- a negative power dealt *negative* damage, healing the defender and draining its own
  controller. CR 107.1b: it is zero.
- a deathtouch attacker spent a second point on a blocker it had already assigned lethal damage
  to, because "lethal assigned" and "died" were one set — and an indestructible blocker never
  joins the second. A double-striking deathtouch trampler lost a point every combat.
- without trample, damage that could not be assigned anywhere simply vanished, taking a
  lifelinker's life gain with it. An attacker divides all of it among its blockers whether or
  not any of it matters.
- the damage division enumerated *orderings*, which is the pre-Foundations rule. The 2024
  update removed damage assignment order: the attacker divides its damage as it likes, owing
  lethal to each blocker it wants to kill. So the choice is which blockers to kill, and the
  enumeration is over subsets — which covers assignments orderings could not express (a 4/4
  ignoring the 1/1 to kill the 3/3) and is *cheaper*: six blockers is 64 subsets against 720.
- `plans` searched attacks that could not legally be made. It filters by `can_attack`, so the
  coach no longer recommends swinging with a tapped or summoning-sick creature.

The defender is assumed to block *well*, and "well" is ordered: survive, then don't lose
creatures for nothing, then take less damage, then lose the cheaper creature. That second term
has to outrank damage or the model chump-blocks everything at twenty life and every attack
looks bad. The attacker's ordering is the mirror image. Both end in a total order over the
creatures involved, because every other term can tie — two 0/1 chump blockers are worth exactly
the same — and when they did, the winner was whichever the caller listed first, so one board
produced two different pieces of advice. A property test found that within a hundred examples.

Refusals rather than guesses, and every public entry point makes them: a creature whose power
is `*` (Consuming Aberration would otherwise look harmless), two creatures sharing an
`InstanceId` (one permanent cannot fight itself), and a board too large to search exactly.
`check_stats` guards `resolve`, `best_defence` and `plans` alike — the first two were reached
directly and were not asking, which is how a guard that exists still lets the thing through.

Bounding the board took three attempts, because the first two counted a dimension and told a
story about it: first `MAX_ATTACKERS` alone, though the block assignments are (A+1)^B and the
**blockers** are the exponent; then (A+1)^B, though that is one `best_defence` and `plans` runs
2^A of them. Both stories admitted eight attackers against six blockers, which takes **five
minutes**.

`budget.py` now counts what the search actually does — every block assignment times every
division of damage — and that number tracks measured wall time to within a few percent across
every board shape tried. `MAX_RESOLUTIONS` is that count at about three seconds, and is the
source of truth; what it admits is roughly eight attackers against three blockers, six against
four, or three against six, and it refuses five against five. The refusal is deliberate: a
coach that silently switches to a heuristic on a big board is worse than one that says it
cannot be sure, because the player cannot tell which answer they got.

`Outcome` and `Plan` carry the creatures themselves, not their printed names. Two Grizzly Bears
reported as `("Grizzly Bears", "Grizzly Bears")` cannot be mapped back to a permanent, which is
the identity collapse the engine uses `InstanceId` to avoid, arriving at the output boundary
instead.

**Feeding it real cards.** `carddata.enginefacts.facts_for(card, face)` builds a `CardFacts`
from a stored card — per *face*, because a transform card has no top-level mana cost and an
adventure card's is the joined `{3} // {1}{B}`. This was missing until the fourth review round
pointed out that every `CardFacts` in the repository was built by `tests/helpers.py`: the
engine was correct about cards that nothing in the system could actually hand it.

**4. Trigger scanner** — `triggerscan.py`. At each step boundary, walk the battlefield for
triggers matching the transition. Only triggers the *clock alone* decides can be found this
way, and that list is shorter than it first looks: "at the beginning of your upkeep" fires for
every permanent you control, so the step is the whole condition, but "whenever this creature
attacks" needs to know who attacked — and this function is handed the battlefield, not the
attackers. Reporting it would remind you about every creature you own including the ones that
stayed home, which is noise dressed as help. Attacking, blocking and dealing combat damage are
therefore event-driven, reported by the module that observes the event.
`every_event_is_classified()` is checked by a test so a new `TriggerEvent` has to be filed as
one or the other rather than silently never firing.

`triggers_at` also takes whose turn it is, and requires it. The step is only half the condition
for "at the beginning of **your** upkeep"; without the other half these reminders fired twice a
round. One gap stays open and is written down in the module: the schema's `TriggerEvent` does
not distinguish "your upkeep" from "each upkeep", so a card with the latter is not reported on
the opponent's turn. None is in the Beginner Box, and closing it needs a re-extraction.

**Keywords.** `SUPPORTED_KEYWORDS` was empty through M3 and now holds eleven: flying, reach,
first strike, double strike, deathtouch, trample, lifelink, menace, indestructible, defender,
haste. Each is there because a specific rule reads it and a test pins the behaviour — a test
greps `core` for every claimed keyword. A weak guarantee -- it proves the string appears,
not that a rule reads it -- but it catches the failure that matters, which is adding a
keyword to the registry and nothing else.
Vigilance is deliberately absent: it governs whether attacking *taps* the creature, and nothing
taps attackers yet. Ward is not in the box's vocabulary yet either.

### The effect model — and the best use of an LLM in this project

What cards *do*, as a closed discriminated union — not free text:

Two layers, because the first extraction run proved one was not enough. An **Ability** says
*when* — a spell resolving, a trigger firing, a cost being paid, a continuous truth — and the
**Effects** inside it say *what*:

```python
type Ability = (
    SpellAbility
    | TriggeredAbility
    | ActivatedAbility
    | StaticModifier
    | StaticRestriction
    | UnmodeledAbility
)

type Effect = (
    DealDamage
    | Destroy
    | ExileTarget
    | MoveTo
    | CounterSpell
    | Draw
    | Discard
    | ChangeLife
    | Scry
    | ModifyStats
    | GrantKeywords
    | PutCounters
    | SetTappedEffect
    | CreateTokens
    | ProduceMana
    | Unmodeled
)
```

With effects alone, coverage was 43%: "whenever you gain life, put a +1/+1 counter on this
creature" was discarded whole even though `PutCounters` expressed its effect perfectly, because
nothing could say *when*. Worse, `{T}: Add {G}` — the most ordinary ability in the game — was
unmodellable, which would have left the M4 mana solver with nothing to read. The ability layer
took coverage from 43% to 52% and produced 22 activated abilities for the solver.

**Populated by a build-time Claude pass, reviewed by a human, committed as data.** The
extractor reads each owned card's oracle text once and proposes structured JSON;
`mtgcoach effects review` reports the unmodelled and the low-confidence cards; `seal --accept`
writes the fixture and its signed manifest, refusing without that flag so the human step is
taken rather than assumed.

Two details differ from an earlier draft of this paragraph. Review **reports**; it does not walk
you through accepting or editing each card, which is a screen and arrives with the UI. And the
extractor runs through the Claude Code CLI on the `opus` alias rather than a pinned
`claude-opus-5`, so the manifest records the model string that produced a fixture — without it a
sealed file cannot say what made it. Exactly the right division of labour: the LLM does the hard
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

It enters as a protocol, in `packages/coach` rather than `core` — `core` has no business
knowing a model exists:

```python
class Explainer(Protocol):
    def explain(self, report: TurnReport, briefing: str) -> Explanation: ...
```

### Call shapes

**Turn coach** — Opus through the local CLI (as the alias `opus`, which is what the CLI takes;
naming a dated model id here and passing an alias there was a contradiction waiting to age), which is why it costs nothing per
call and why there is no `thinking` or `output_config` to set. Input: the engine's own
`TurnReport`, rendered as text by `coach/briefing.py` — every fact in it already checked.
Output: `play`, `attack`, `because`, `in_short`, `watch_out`, `check_yourself`.

*No `alternatives` field, which this section originally promised.* It was dropped on
purpose: the alternatives are the numbered attacks and the PLAYABLE cards, already on
screen, already exact, and already ranked by the engine. Asking a model to re-list them
in prose would put a second, unchecked copy of the options next to the checked one.

**Rules Q&A** — retrieval first, then one call. FTS5 over the Comprehensive Rules picks the
passages, they go into the prompt verbatim with their references, and the answer's citations
are checked against exactly that list.

*This replaces the tool-use design sketched here originally, and the reason is the safety
property.* With tool use the model chooses what to look up and can still answer from memory
afterwards; there is nothing to check the answer against. With mandatory retrieval there is:
every citation must be one of the passages supplied, compared exactly. It also costs one call
rather than a loop, and it works through the CLI, which is what makes it free.

Two things the original design had that this does not, and should get: `get_state` is covered
(the board goes into the prompt) but `simulate_combat` is not, so a question about a specific
combat is answered from the rules rather than from the engine's numbers. A question box that
could hand the combat solver a hypothetical is the obvious next step.

The first live run refused *every* answer: the model cited `702.19b (Trample)` because that is
how the passage was labelled, and the checker wanted `702.19b`. The prompt now puts the citable
reference in brackets and nothing else, and citations are resolved before they are checked —
decoration comes off, digits do not.

**Retrieval only finds a rule the question shares words with, and one question does not.**
Found live, and it is close to the most common beginner question about combat: *"can a creature
that came into play this turn block?"* The answer is rule 302.6 — and 302.6 contains none of
those words. It says a creature cannot attack "unless it has been under its controller's control
continuously since their most recent turn began", then adds that this is informally the
"summoning sickness" rule. So eight passages about blocking came back, none of them 302.6, and
the answer was *"the rules I was given don't talk about how new a creature is"*: honest,
correctly refusing to invent, and useless.

Mostly the document bridges its own vocabulary — 403.5 says the battlefield used to be called
"in play", 404.1 says a graveyard is a discard pile — so asking in the old words finds the rule
that explains the old words. What it cannot bridge is a *paraphrase*, because there is no word
to look up. `rules/phrasing.py` is a deliberately tiny map from how a beginner says a thing to
how the rules say it, appended to the query so the passage can rank at all. It must stay tiny:
every entry decides what a question is about before seeing the question, which is exactly the
cleverness that makes retrieval worse. `tools/check_rules_phrasing.py` checks every target is
still wording the installed document uses, because a reworded one matches nothing and the only
symptom is the answer quietly going back to "I can't say".

Now: *"Yes! A creature that just showed up can still block. It only has to wait a turn before it
can attack"* — cited to 302.6.

**Magic names its abilities with ordinary words, and a question can contain one without being
about it.** From the same investigation: *"what happens when my hit points reach zero?"* returned
the four passages titled **Reach**. "Reach" appears seventeen times in the whole document, nearly
all of them the ability — which makes it *rare*, so bm25 weighted it heavily — and the rule the
question wanted was nowhere. There are 160 one-word keywords: haste, flying, trample, menace,
shadow, fear, defender, storm, ward.

Which way to be wrong decides the design. A question *about* a keyword is far commoner than one
that merely contains one, and dropping the wrong word is much worse than keeping it — "what about
deathtouch?" with the word dropped retrieves nothing at all. So the keyword reading stays the
default, and `rules/keywords.py` sets a word aside only on positive evidence that it is a verb:
something countable straight after it ("reach zero", "reach 20"), or a subject pronoun straight
before it ("I reach"). Measured, that fires on exactly the questions it should and no others.

The list of keywords is read off the document's own 702.x headings, never written out here.
There are 160 of them, Wizards add several a year, and this has to work on sets nobody has
printed.

Two questions later, the same investigation found the *other* half of that one: the rules say a
player at **"0 or less life"** loses, in digits, and a question says "zero". Adding the bare digit
made things worse — it pulls in every rule mentioning the `{0}` mana symbol — so the phrasebook
maps the paraphrase onto the whole phrase instead.

**Retrieval is now measured rather than asserted.** `tools/check_retrieval.py` asks the installed
rules 22 questions a person would actually type and checks an answering rule comes back in the top
eight; the questions and their acceptable references are data, in `tools/retrieval_questions.json`.
It went 18/22 → 21/22 across these two fixes with no regressions, and it is in the gate, so a
change that drops a question fails the build instead of quietly making the coach worse.

That 22nd question is why the gap list exists, and it is what got fixed next.

**The rules state restrictions as requirements; a question states the thing being restricted.** So
the two describe one fact with opposite signs and share no word: *"can a tapped creature block?"*
against 509.1a's *"the chosen creatures must be untapped"*. Stemming does not help and must not —
`tapped` and `untapped` are opposites, and an engine that conflated them would answer that question
*yes*. What is missing is a bridge, and a bridge is a fact about English rather than about ranking.

`rules/negation.py` carries two, each measured. "Tapped" together with an attacking or blocking
word adds **"must be untapped"** — a phrase that occurs exactly twice in the whole document, in
508.1a and 509.1a, which are the answer. "Nobody blocked it", "isn't blocked", "not blocked" add
**"unblocked creature"**. Both halves are required for the first: *"what does tapped mean?"* wants
the glossary, and adding the combat restriction would push it out of a list that holds eight.

The second entry taught something the eval had missed. It first added the bare word "unblocked",
retrieval looked right, and the eval passed — because the ground truth accepted the *glossary entry
defining* the term. Live, the answer was refused: "unblocked" is the title of two glossary entries,
a title match is weighted four times a body one, and 510.1b — the rule that says what actually
happens — was not in the top eight, so there was nothing to cite. The fix is the whole phrase plus
**"combat damage"**, because a question asking "what happens" never says the word for what happens.
The ground truth now demands 510.1b and refuses the definition.

That is the lesson worth keeping: *an eval is only as good as its idea of a right answer*, and a
definition of a term is not an answer to a question about it. The live run is what caught it.

The question set is 28 now, and **28/28** with no known gaps.

Kept apart from `phrasing` on purpose. That module is for a beginner having no word for a concept;
this one is for a beginner having exactly the right word and the rules having written its opposite.
A wider rule is easy to write and hard to keep honest — "not X" → "unX" applied blindly turns "not
less than" into a search for *unless*, which the rules use eighty-seven times and never as a
negation of "less".

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
| **M0** ✅ | `git init`; `uv` workspace; the full §5 toolchain failing-on-violation from commit one; review agent installed and configured. | Standards and the review loop are free on day one, expensive to retrofit. |
| **M1** ✅ | `core`: state model, events, `reduce`, step walker. 100% + property tests. | The spine. No UI needed to test it. |
| **M2** ✅ | `carddata`: Scryfall ingestion, `Collection`, the `sets add / audit` commands, FDN decklists as data. | Establishes the set-agnostic data layer before any set-specific work exists to bias it. |
| **M3** ✅ | Effect extraction pipeline + review CLI + FDN golden fixture and signed manifest. Card explainer CLI. | Useful immediately; proves the build-time Claude pattern *and* the multi-set pipeline in one go. |
| **M4** ✅ | Mana solver, legality, trigger scanner, combat simulator. Hypothesis suites. Convergence-loop review. | The engine. This is what makes it a coach rather than a notepad. |
| **M5** ✅ | FastAPI + WebSocket; Expo app as a **manual** tracker (tap cards in from your decklist). | **Probably 70% of the total value.** Ship before touching the camera. |
| **M6** | Claude coach + rules Q&A over M4's output. **Done.** | Turns correct answers into understandable ones. |
| **M7** | Single-card scan, then board scan → state diff → one-tap accept. Accuracy corpus. | The original ask, now with a tracker behind it to correct mistakes. |
| **M8** | Web view on the laptop; teaching features — quiz mode, end-of-game review, son's tablet view. | The reason to build this instead of buying a rules app. |
| **M9** | Enable a second set end-to-end as a **test of the abstraction**, not a feature. | If set #2 takes an evening, the design held. If it takes a week, we learn exactly where. |

M0–M5 is a genuinely useful tool. Everything after is upside.

**One app, not two.** The tree above listed `apps/mobile` and `apps/web` separately. Expo's web
target builds the same source to a browser bundle (370 kB, one page), so M5 shipped one app that
runs on Android, the tablet and the laptop. `apps/web` stays in the plan for M8, to be built
only if the big-screen view wants a genuinely different layout rather than a wider one.

**How the app stays dumb.** §4 says no rules logic crosses into TypeScript, and that is easy to
say and easy to erode. Three things hold it:

- The app renders `reasons` **verbatim**. It has no idea what a land is. When the engine says
  "you need 1 more untapped source", those words go on screen unaltered — which is also why the
  engine's sentences are written to be read by a nine-year-old rather than parsed by a client.
- Nothing is applied optimistically. Every action is an event sent to the server, and the board
  that comes back is the board. A tracker that guessed ahead of the server would be a second
  rules engine, written in the language chosen for not having one.
- `Attacks.unavailable` is rendered as its own state. An empty attack list would read as "do not
  attack", which is advice the engine did not give.

The one module with logic in it is `src/format.ts`, and the test for whether something belongs
there is: *could it ever disagree with the engine?* Pluralising a list cannot. Deciding whether
a land is tapped can, so it does not live there.

**Two hand-written contracts, checked against each other.** `services/api/views.py` builds the
JSON by hand and `apps/mobile/src/wire.ts` declares it by hand — the right call on both sides,
and a silent drift risk between them. `tests/api/test_wire_contract.py` plays a whole turn,
unions every field the server ever sends, and compares both directions against the TypeScript.
A field the app has never heard of is a blank space in the UI; a field the app expects and no
longer gets is the same bug mirrored. Neither raises anything at runtime, which is exactly why
it needs a test.

**Static abilities, and what the combat numbers are worth.** Seven cards in the box change
combat from the battlefield, and they split three ways. A restriction on the card *itself*
(Vampire Interloper's "can't block") is applied: such a creature is left out of the side it
cannot join. A restriction that needs an attachment (Pacifism) and a modifier (Goblin
Oriflamme's anthem, an Equipment's +2/+1) cannot be — `Permanent` has no attachments and the
combat model has no "affects other creatures" — so they are **disclosed**, by name, next to the
numbers. "Four damage, lethal" has to be readable as "unless the Pacifism says otherwise", and
a confident wrong number is the worst thing this project can produce.

**Two things this cannot do yet, which the app has to say out loud.** `core` has no event for
*casting a spell* — the `Event` union is untap/draw/land/tap/move/life — so the coach can tell
you a spell is affordable and the tracker cannot record you casting it. `Playable.is_land` is on
the wire for exactly this reason: the app only offers to play what the engine can record, and
says so on the cards it cannot. Casting arrives with the stack, alongside `counters` and
attachments.

The other is identity, and it is now half closed. The API is **not** unauthenticated: the
server makes a token on first run, prints it at startup, and `api/gatekeeper.py` refuses every
request and every socket without it — as ASGI middleware rather than a per-route dependency, so
a route added later is behind it whether or not anybody remembered. The threat that closes is
not a guest's phone but a web page the household visits, which could reach
`http://<laptop>:8000` cross-origin and needed to know nothing to drive the game or spend the
subscription.

What is still open is *which player* is asking. One shared secret does not say, so every
snapshot still carries both players' hands and `move_card` will still move any card from any
zone — §3's "can't see your opponent's hand" is enforced by the room, not the code. A token per
*seat* closes that, issued when a game starts, and is the obvious next step from here: the
gatekeeper already knows how to read a token off a request, and would then put a `PlayerId` on
the scope instead of a boolean.

**The server may not contradict its own coach.** `guard.py` asks `legality.why_not_play_land`
rather than re-deciding. It used to check only that the card was a land, and the reducer checks
only hand membership and the land drop — so nothing checked *timing*, and the API accepted a
land played during the untap step while the advice in the very same response read "you can only
play lands in a main phase".

**Every refusal is a sentence, never an exception.** The solver refuses a board it cannot answer
for exactly; the coach turns that into a reason on a card. Letting one escape made the whole
snapshot a 500 — and because the API records an event *before* building the advice, a single
accepted event could leave a game that could never be read again.

**Snapshots are versioned.** An HTTP reply and a socket broadcast race, and without an ordering
the older of the two silently won: an undo could appear to un-happen, and the next event would
be sent against a board the server had already moved past. Every snapshot carries a revision and
the client takes an update only if it is not older than the one on screen.

The revision counts *changes*, not events, and the difference is the whole point: undo removes
an event and is itself a change, so counting events made the number go **backwards** on undo —
and the client, doing exactly what it was told, discarded every undo. Two reviewers found that
independently, and a test of mine had pinned the broken behaviour.

**Both devices are seats.** The app takes the seat it is given rather than assuming it is
`you`: the first device starts a game, a second opens the same session id and takes the other
side. Without that the WebSocket and the both-players advice had nothing to be for — a second
device could only start a second game, and neither could ever act as the other player.

**A package the original tree did not have.** `packages/coach` was added in M5. The four
solvers each answer a narrow question; something has to assemble them into the one a player
asks, and putting that in `services/api` would have made it untestable without HTTP. It takes
card data through a `CardLookup` Protocol, so like `core` it has no dependencies and no set
knowledge, and the 100% gate applies to it in full.

Two things it will not do, both of which are the point:

- It will not answer for a card the sealed fixture does not model. Those are named in
  `TurnReport.unknown`, so the player is told where the coach stops. Silence would read as
  "there is nothing to do", which is a lie, and at 52% coverage it would be a frequent one.
- It will not swallow the engine's refusals. A board too large to search exactly, or a
  creature with `*` power, comes back as `Attacks.unavailable` — a sentence, not an empty
  list. An empty attack list *is* advice, and it would be the wrong advice.

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
