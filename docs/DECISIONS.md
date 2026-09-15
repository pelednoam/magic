# Decisions

§12 of [the advisor's review](PROJECT_REVIEW_2026-09-15.md) lists ten decisions
to record before further implementation. Several of them had already been made
by the time it was written, or were made while fixing its findings -- by
default, in a commit message, or not at all. An implicit decision is still a
decision, and the point of this file is that it stops being implicit.

Each entry says what was decided, what it rules out, and who decided. **Open**
means nobody has, and it is not for this file to guess.

---

## 1. Release sequence — **open**

Which rule families come first, and how unfinished coverage is reported.

The second half is settled (see §7 below); the first is not. `docs/PLAN.md` has
milestones, and they were written before the requirement became "all
applicable rules", so they order features rather than rule families.

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

## 3. State capture — **open**

Which facts come from the app, from manual correction, and from recognition
later; how an uncertain observation is represented. `packages/vision` exists
and nothing downstream of it expresses doubt.

## 4. Command semantics — **partly decided**

Decided: a command is one event, applied through one reducer, recorded in a
log; `CastSpell` carries its payment because CR 601.2 is one action and a
half-cast spell is not a state the game can be in; `PassPriority` is a command
rather than an inference; undo is replay of the log minus its tail.

Not decided: actor identity (the token is per *server*, not per seat, so
nothing distinguishes which player sent an event), retries, cancellation, and
commit boundaries for a multi-event action that fails part-way.

## 5. Source versions — **partly decided**

Decided: card data is sealed with a sha256 manifest (`mtgcoach effects check`);
CI records the Comprehensive Rules URL it fetched, so a run says which revision
it was judged against.

Not decided: pinning a *game* to the versions it was played under. A journal
records its events and not the engine, card data or rules revision that
produced them, which is exactly what makes item 6 below a question.

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

## 8. Test authority — **open**

Who reviews expected outcomes for complicated scenarios, and how a
disagreement is settled against the source. Today the answer is "whoever wrote
the test", with the Comprehensive Rules as the tie-breaker and no record of who
looked. `mtgcoach effects seal --accepted` is the only place a human review is
made explicit.

## 9. Privacy and visibility — **partly decided**

Decided: what reaches a prompt is public information plus the asking player's
own hand -- both battlefields, the stack, that hand, and no other hidden zone
(CR 400.2). `printed.py` enforces it.

Not decided: the snapshot still carries *both* hands to *both* devices, so "you
cannot see your opponent's hand" is enforced by the room and not by the server.
A token per seat is the known fix and is not built. Nor is there a policy on
what game data is kept for evaluation; journals hold every briefing verbatim.

## 10. Release evidence — **partly decided**

Decided: `tools/gate.sh` is the bar, CI runs all of it, and
`tools/check_ci_covers_gate.py` fails the build if CI ever runs less than the
gate -- which it did, silently, while the README called it the full gate.

Not decided: what evidence a *claimed capability* requires. The gate proves the
code does what its tests say; it says nothing about whether a family can use
the app, and §14's last checkbox is the one nothing here addresses.

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
