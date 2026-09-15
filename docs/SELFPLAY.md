# Self-play: two agents, whole games, every event watched

Playing a game with a nine-year-old takes an evening and produces one data point. This plays
hundreds of games in seconds, or a handful of coached ones overnight, and says what broke.

```bash
uv run python -m mtgcoach.selfplay --games 300                  # seconds, no model
uv run python -m mtgcoach.selfplay --games 1 --coach \
    --journal data/selfplay/tonight.jsonl                       # ~20 min/game
uv run python -m mtgcoach.selfplay --games 1 --replay data/selfplay/tonight.jsonl
```

## What it is actually testing

**Not the play.** The policy agent does not understand Magic — it plays a land if it has one,
casts the most expensive thing it can afford, and attacks with whatever the engine ranked first.
Grading that would be grading a stand-in.

What it tests is everything in `watching.py`: the things no play may ever break, checked after
**every single event**. Each one is a sentence from the engine's own documentation —
`PlayerState.cards` calls itself *"the basis of the conservation invariant"*, `InstanceId` exists
so one Mountain is distinguishable from another, the land drop is a limit the reducer enforces.
They are checked here because a season applies tens of thousands of events in an order nobody
chose, which is exactly when an invariant that holds in every fixture stops holding.

| Check | Why |
|---|---|
| Cards conserved, per player, per event | No event may change how many cards a player owns |
| No `InstanceId` in two zones at once | The identity that makes "the Mountain you tapped" meaningful |
| No card swapped for a copy of another | A count alone would miss it |
| Life inside ±1000 | Arithmetic that has run away, not game balance |
| One land drop a turn | Catches a path that went around the reducer |
| Turn ≥ 1, step is a real step | Cheap, and the only guard on a field nothing else checks |

## What it cannot test, and why

**The engine has no event for casting a spell.** `Playable`'s own docstring says so — the stack
arrives with it. So the harness does exactly what the app's user does: taps the lands the payment
names, then moves the card onto the battlefield. And combat applies the engine's own `Outcome`
(damage, then deaths, then lifelink) rather than a second rules implementation written to check
the first. **Where the engine is the authority, the engine is asked.** A harness that invented its
own rules would be testing itself.

The consequence: this exercises zones, mana, legality, the step walker, the trigger scanner and
the combat simulator. It does not exercise spell resolution, because there is none yet.

## Re-running a season

Three different questions, three different commands.

### 1. The same policy season, exactly

```bash
uv run python -m mtgcoach.selfplay --games 300 --seed 0
```

Deterministic, always. The engine generates no randomness — `start_game` says the caller
shuffles — so `dealing` seeds the shuffle and the policy, and a seed is a whole season. Same
numbers every time, on any machine.

### 2. A coached season, exactly — with `--replay`

A seed **does not** reproduce the coach. It is a language model; asking it the same question
tomorrow is a different experiment. So a coached run writes a **journal**: one JSON line per
decision, appended as it happens, holding

- the moment — `seed`, `turn`, `step`, `player`
- the **exact briefing** the model was given
- the answer's every field, or `error` when there was none
- `trusted`, and every `problems` entry the engine's checks produced

```bash
uv run python -m mtgcoach.selfplay --games 12 --coach --seed 100 \
    --journal data/selfplay/overnight.jsonl
uv run python -m mtgcoach.selfplay --games 12 --seed 100 \
    --replay data/selfplay/overnight.jsonl
```

The replay is the identical game in a second rather than twenty minutes. **The seed must match
the one the journal was written with** — it is part of every key.

Two things this is for:

- **Studying a bad decision.** The briefing is in the journal, so the board the model was actually
  shown can be read next to what it said. A decision becomes something to study rather than
  something that happened once.
- **Testing a change to the engine.** Replay an old journal against new code: the answer is checked
  again rather than trusted because it was trusted before, and the journal's own verdict is carried
  into the complaint — `"... (journal said trusted=True)"`. An answer that passed last week and
  fails today is the regression worth knowing about.

A moment the journal does not have raises `DivergedError` rather than being guessed. A replay whose
gaps are filled with "do nothing" is not a replay, and the divergence it hides is the most
interesting thing that could have happened.

### 3. The same seeds, asked again

```bash
uv run python -m mtgcoach.selfplay --games 12 --coach --seed 100 \
    --journal data/selfplay/second-opinion.jsonl
```

Same decks, same deals, the coach asked fresh. Comparing the two tallies measures how **stable**
the advice is, which no single run can.

## Variety, and why it is seeded rather than random

A season should cover different decks, different draws and different boards — but **reproducibly**.
Random and repeatable are not opposites: a seed gives both, as long as it varies the things that
matter. Unseeded randomness would find just as much and let you re-run none of it, which defeats
the journal.

What the seed varies:

- **the shuffle**, so every game is a different deal and a different opening hand
- **which matchups get played** — `dealing.pairings` shuffles all 90 ordered pairings with the seed
  and walks them, so every pairing is visited before any repeats. A short season is a spread; a long
  one still covers everything; a different seed gives a different spread
- **who is on the play**, which alternates with the seed's parity, because going first means
  skipping a draw and a season where one seat always went first tests half of it
- **the policy's own choices** — when it holds back an attack, when it plays nothing

This was got wrong first time round, which is why it is written down. The pairings were walked in
index order, so a twelve-game coached season — the *expensive* one — played `cats` nine times:
`permutations` in lexicographic order puts the alphabetically first deck on one side of every early
pairing. Three quarters of a four-hour budget on one deck, and nothing said so.

## What a season reached

Which is the other half of the same lesson. A clean season is only reassuring in proportion to how
much of a game of Magic happened in it — three hundred games in which nobody cast anything would be
three hundred clean games. So a season reports what it **reached**, not just what went wrong:

```
covered: 10 deck(s), 60 pairing(s) -- cats, elves, goblins, healing, ...
reached: 888 land drops, 1137 spells cast, 383 attacks, 0 turns with a trigger, biggest board 20
```

That last number is what this reporting was worth. `0 turns with a trigger` across 60 games is not
a harness bug: the Beginner Box has 31 triggered abilities and every one is event-driven (`enters`
21, `attacks` 3, `another_creature_enters` 3, `you_gain_life` 2, `dies` 2), while the scanner turns
only `beginning_of_upkeep` and `end_step` into reminders. **The TRIGGERS NOW panel can never fire
for Foundations** — see §7 of PLAN.md. No number of clean games would have shown that.

## Reading the output

```
12 games, 12 clean, 0 problem(s)
  turns: 11-19, median 14
  events applied: 2144
  endings: 12 life
  coach: 18 asked, 18 trusted, 0 failed checks, 0 no answer
  cards nothing can speak for (59): Uncharted Haven, Broken Wings, ...
```

- **clean** — games where nothing in `watching.py` fired. Anything else prints the seed, the decks
  and the turn, because *"card conservation broke"* is not a bug report and *"it broke on turn 7's
  declare-attackers step, elves v goblins, seed 103"* is.
- **coach: N asked, N trusted** — one line per coached seat. `trusted` means the answer survived
  `advice.verify`, the same check the server puts in front of a player. Anything that failed is
  listed under `disagreed:` in the engine's own words.
- **cards nothing can speak for** — the effect database's honest state, most common first. This is
  usually the most actionable number in the whole report.

## The runs on record

| Journal | Seeds | What it was |
|---|---|---|
| `data/selfplay/overnight.jsonl` | 100–111 | Twelve coached games, Claude on both seats |

Journals are not committed — they hold the full briefing for every decision and run to megabytes.
Keep the ones that found something; the command that produced each is in the table above, and the
`.log` beside it has the summary that run printed.

## What the journal is also for: stepping through a game

A coached journal is what the **step-through replay** reads. The app lists the journals a server
has, then the games in one, then walks a game a decision at a time — board, what the coach said,
and the engine's objections when it refused. See §10 of PLAN.md for the routes and the screens.

For that to work a journal has to hold the *game* as well as the decisions, and it does: at the
end of each game the harness appends one more line — the libraries it was dealt and every event it
applied, in order. Rebuilding a moment is then `start_game` plus `reduce.replay`, which is `core`
and nothing else. Nothing is re-asked, so the board shown is the board that was played.

```
{"seed": 100, "turn": 7, "step": "declare_attackers", ...}   ← a decision
{"seed": 100, "turn": 7, "step": "postcombat_main",  ...}    ← a decision
{"kind": "game", "seed": 100, "libraries": {...}, "events": [...]}  ← the game
```

**The recording is written last**, because the event log is not known until then. A run killed
mid-game therefore keeps its decisions and loses its recording, which is the right way round: the
decisions are what the coach said and cannot be produced again, and the recording can be, by
replaying them. It does mean such a journal cannot be *shown* — `GET /replays/{name}` answers 404
saying so, rather than showing an empty screen.

`data/selfplay/overnight.jsonl` is in exactly that state: it was launched before the harness
learned to record games, so it has games of advice and no boards to hang them on. Re-run it with
`--replay` to get a journal that can be walked:

```bash
uv run python -m mtgcoach.selfplay --games 12 --seed 100 \
  --replay data/selfplay/overnight.jsonl --journal data/selfplay/walkable.jsonl
```

That replays the recorded answers rather than asking Claude again, so it costs seconds rather than
hours, and it writes a full journal of its own: the same advice, a recording of each game, and
**today's verdict on each answer**. The verdict is the run's own rather than the old journal's on
purpose — the new journal describes the game that just happened, and if the engine has grown
stricter since, a move that was played the first time is refused this time and the game diverges.
That divergence is the finding; `--replay`'s summary carries the comparison
(`… (journal said trusted=True)`), and a moment the old journal cannot answer stops that game
rather than being guessed at.

Three games of `overnight` rebuilt this way produced 81, 56 and 71 walkable moments.

Which is a reason to keep the journals of games worth walking through, even though they are
gitignored by default.

## Adding a check

`watching.broken` takes the state on both sides of a transition and yields a sentence per problem.
Add one there, and a season immediately answers whether it has ever been false. That is the cheapest
way in this project to turn a suspicion into evidence — and the most valuable checks are
conservations, because a single state cannot express them and a harness that only looked at the end
of a game would learn which game broke and never which event.
