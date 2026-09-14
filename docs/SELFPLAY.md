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

## Adding a check

`watching.broken` takes the state on both sides of a transition and yields a sentence per problem.
Add one there, and a season immediately answers whether it has ever been false. That is the cheapest
way in this project to turn a suspicion into evidence — and the most valuable checks are
conservations, because a single state cannot express them and a harness that only looked at the end
of a game would learn which game broke and never which event.
