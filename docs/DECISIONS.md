# Decisions

§12 of [the advisor's review](PROJECT_REVIEW_2026-09-15.md) lists ten decisions
to record before further implementation. Several of them had already been made
by the time it was written, or were made while fixing its findings -- by
default, in a commit message, or not at all. An implicit decision is still a
decision, and the point of this file is that it stops being implicit.

Each entry says what was decided, what it rules out, and who decided. **Open**
means nobody has, and it is not for this file to guess.

---

## 1. Release sequence — **decided: all applicable rules is the objective**

The goal is every rule of Magic that applies to the formats played. The
advisor agrees and is precise about the distinction that matters: *"'All rules'
is the objective; the release notes should state exactly what became supported
and what remains"*, and *"shipping one family does not silently mark unrelated
mechanics complete"*.

So the objective is broad and **no release may claim it**. What a release says
is which rule families became supported. Not a percentage: 52% schema coverage
of one fixture was read as "half the cards work", and it meant neither that nor
anything about interactions between them.

The inventory to sequence against is §6.2 of the review -- 24 capability rows,
each with the work it needs -- and the phases are §10. Where the work stands
against those phases:

| Phase | | |
|---|---|---|
| **A** correct contradictions, define support honestly | done | R01, R03, R08, and the modelled-vs-verified split |
| **B** shared action, priority, stack | mostly | stack, priority, passing and one validated runtime done; **state revision and retry semantics not** |
| **C** execute effects and state processing | begun | outcomes and state-based actions done; effects still only *described* |
| **D** broaden interactions and formats | not begun | the rest of §6.2 |
| **E** rules assistant and teaching flow | begun early | retrieval and card-aware evidence done; answer evaluation not |
| **F** release evidence | see item 10 | |

Phase E ran ahead of C because retrieval work does not depend on runtime work,
which the review says explicitly.

## 2. Runtime sourcing — **decided by default, and worth revisiting**

This engine was extended: a stack, priority, pass tracking, state-based
actions, casting as one action. No external implementation was evaluated
against it, and the review says plainly that it did not evaluate any either.

That is a decision made by momentum rather than comparison, and it is the
largest one here. What argues for it: `core` holds no card data, every
transition is a pure function, and the whole engine is checkable by a self-play
season -- properties an integration would have to match. What argues against
it: full rules coverage is an enormous amount of rule-by-rule work, and
somebody else may have done it.

## 3. State capture — **open; the advisor's shape recorded**

Three provenance classes rather than two, per §7.2 and §7.10:

- a **validated action**, accepted by the runtime;
- a **manual correction**, for syncing with a physical table -- *"record them
  as corrections, distinguish them from validated actions, and reevaluate which
  downstream conclusions remain established"*;
- an **uncertain observation**, from a camera or a typed guess -- and *"that
  uncertainty must travel into the answer rather than disappearing once a
  guessed ID enters the game state"*.

The third is the one that bites: `packages/vision` exists and nothing
downstream of it expresses doubt, so a misread card becomes a fact the coach
reasons from confidently. Still open -- the classes are the advisor's
recommendation, not a decision anybody has taken.

## 4. Command semantics — **partly decided; per-seat identity now required**

Decided: a command is one event, applied through one reducer, recorded in a
log; `CastSpell` carries its payment because CR 601.2 is one action and a
half-cast spell is not a state the game can be in; `PassPriority` is a command
rather than an inference; undo is replay of the log minus its tail.

**Decided: an event must say which player sent it.** The token is per *server*
today, so the seat in an event's payload is a claim the sender makes about
itself and nothing checks it -- either device can send either seat's actions.
That is the same hole as item 9 and has the same fix, so they are one piece of
work.

Still not decided: retries, cancellation, and commit boundaries for a
multi-event action that fails part-way. The review asks for "state revision and
retry semantics" as a Phase B deliverable, and it is the part of Phase B that
is missing.

## 5. Source versions — **partly decided**

Decided: card data is sealed with a sha256 manifest (`mtgcoach effects check`);
CI records the Comprehensive Rules URL it fetched, so a run says which revision
it was judged against.

**Decided: a game is pinned to the versions it was played under.** A journal
records its events and not the engine, card data or rules revision that
produced them -- which is exactly what made item 6 a question, and what made a
whole directory of journals unreadable when priority arrived with nothing
recording that they predated it.

Per-scenario too: the review asks that each rules scenario record the document
version it was derived from, which is where this meets item 8.

## 6. Replay policy — **decided, and this is where it is written down**

**Historical reconstruction, not reevaluation.** A moment of a replayed game is
the recorded events folded over the recorded deal, through `core` alone. The
model is never re-asked: asking it again produces a different game and a board
that never existed.

**A journal from an older engine is refused, never approximated.** When the
engine grows stricter -- priority arriving is the case that happened -- events
recorded before it are no longer legal, and `replays._replay` skips that game
so the route answers 404. It does not apply what it can and show a partial
board, because a board the events did not produce is the one thing this
project must never show a child.

**Migration is re-running, not converting.** `--replay` plays the recorded
*answers* under today's engine, needs no model, and writes a journal that
walks. Expect it to report disagreements the first run did not: advice that
passed before the disclosure checks existed does not pass now, and finding that
out is the point.

Decided by whoever held the keyboard, which was me; it is recorded here because
it is a policy and not an implementation detail.

## 7. Support claims — **decided, and this is the vocabulary**

Five separate words, none of them "correct":

| Claim | Means | Where |
|---|---|---|
| `modelled` | the card's behaviour is *described* in the sealed fixture | `api/cards` |
| `not_carried_out` | ...and the engine will not *do* it, in words, per card | `core/carrying` |
| `not_modelled` | a rule the engine has no representation for at all | `core/disclosure` |
| `cited` | every rule number came from the passages we supplied | `rules/answer` |
| `grounded` | the answer's load-bearing words appear in that evidence | `rules/grounding` |

Every rules answer also carries `unchecked`: the server's own sentence saying
nothing has read the cited rule and decided the answer follows.

The rule behind all five: **an unsupported interaction may never inherit a
verified result, and a gap must be visible where a player looks.** "Described"
was being read as "handled" -- Giant Growth resolved and no toughness changed
-- and that is what the split exists to prevent.

## 8. Test authority — **decided: the Comprehensive Rules**

The rulebook is the authority, and a disagreement is settled by reading it. The
advisor says the same and adds two things:

- **Derive the expected outcome from the rules, not from the implementation.**
  He asks for *"independently reviewed expected outcomes"* and *"better tests
  with independent expected outcomes, not simply a higher test count"*. A test
  written by reading the code cannot catch the code being wrong -- which is
  precisely how the Pacifism test passed while the shipped card did not work.
- **Record the document version per scenario.** CR 101 and 108 for rule and
  card authority, 117 for priority, 601-608 for casting and resolution, 613-616
  for continuous/replacement/prevention, 508-510 for combat, 514 for cleanup,
  704 for state-based actions.

The convention already in use is a CR citation in the docstring. What is
missing is the revision, which item 5 now requires anyway.

## 9. Privacy and visibility — **partly decided**

Decided: what reaches a prompt is public information plus the asking player's
own hand -- both battlefields, the stack, that hand, and no other hidden zone
(CR 400.2). `printed.py` enforces it.

**Decided: a token per seat.** The snapshot carries *both* hands to *both*
devices today, so "you cannot see your opponent's hand" is enforced by the room
rather than by the server -- and the same gap means nothing verifies which
player sent an event (item 4). One piece of work, two decisions.

Still not decided: what game data is kept for evaluation. Journals hold every
briefing verbatim, which is what makes a bad answer diagnosable and also means
they hold the full contents of both hands, every turn.

## 10. Release evidence — **partly decided; a per-capability bar now required**

Decided: `tools/gate.sh` is the bar, CI runs all of it, and
`tools/check_ci_covers_gate.py` fails the build if CI ever runs less than the
gate -- which it did, silently, while the README called it the full gate.

**Decided: every claimed capability needs stated evidence.** The gate proves
the code does what its tests say and nothing more. Phase F's shape, from the
review: positive, negative, interaction and replay evidence per family, and
evaluations that keep executable correctness, source retrieval, answer quality
and usability apart rather than reporting one number.

Still open: what the bar actually is for each, and family testing -- §14's last
checkbox, which no amount of green gate addresses.

---

## Where §14's checklist actually stands

Evidenced, with the work that did it:

- **Confirmed findings have regression tests and verified resolutions** —
  R01–R10, each reproduced before being fixed.
- **One validated runtime across live play and self-play** — self-play applies
  its actions through `api.guard`, the same checks a tap goes through. It did
  not, and that is why a casting defect survived three thousand casts.
- **Unsupported interactions cannot silently inherit a verified result** — the
  five claims in §7.
- **CI executes the checks the documentation claims** — and is checked.
- **Historical replay and reevaluation are distinguished** — §6, and
  `docs/SELFPLAY.md`.
- **Rules answers include the relevant evidence** — the cards in play now
  arrive in the prompt with their printed text.

Partly:

- **Priority, stack ordering, payment, triggers, combat, automatic
  consequences** have interaction scenarios; **effects** do not, because
  nothing executes them.
- **Card representations tested as executable behaviour** — tested as
  *described* behaviour. There is nothing executable to test yet.

Not addressed:

- The rule-family inventory (item 1).
- The runtime representing every choice affecting a supported result — targets,
  modes and pending choices are absent.
- The short explanation preserving the long one's conditions: nothing compares
  `in_short` against `answer`.
- Family testing.

The review left its boxes unchecked deliberately. So does this.

---

## What the decisions ask for next

In dependency order, not priority order:

1. **A token per seat** (items 4 and 9, one piece of work). The server cannot
   tell the two devices apart, so it cannot withhold a hand from one of them
   and cannot verify that an event came from the seat it claims. Both halves
   go away together, and it is the only open item with a way to go wrong at a
   real table: the second device is the one the child holds.
2. **Versions on a game** (item 5) -- engine, card data and rules revision in
   the journal, and the rules revision on each scenario (item 8). Cheap, and it
   is what would have made a directory of unreadable journals diagnosable
   instead of puzzling.
3. **State revision and retry semantics** (item 4) -- the remaining Phase B
   deliverable, and the thing a flaky LAN will find first.
4. **Executing effects** (Phase C) -- the largest, and what turns
   `not_carried_out` from a disclosure into a shrinking list.

Items 2 and 3 are the two nobody should decide in passing: whether to keep
extending this engine, and how an uncertain observation reaches an answer.
