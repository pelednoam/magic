/**
 * What the stack panel says, and the distinctions it must not blur.
 *
 * Every one of these was a way the app could have misstated the rules. The
 * order the stack is shown in *is* which spell resolves first (CR 405.5). The
 * difference between "nobody may act" and "we do not know where this goes" is
 * the difference between a rule and a gap. And a spell somebody else controls
 * is not this device's to resolve, however much both devices can see it.
 */

import { describe, expect, it } from "vitest";

import { resolving, waiting, whoseMove } from "../src/moment";
import type { GameState, Waiting } from "../src/wire";

const BEAR: Waiting = {
  instance_id: "b1",
  oracle_id: "bear",
  name: "Grizzly Bears",
  controller: "you",
  resolves_to: "battlefield",
};

const GROWTH: Waiting = {
  instance_id: "g1",
  oracle_id: "growth",
  name: "Giant Growth",
  controller: "them",
  resolves_to: "graveyard",
};

function board(over: Partial<GameState> = {}): GameState {
  return {
    turn: 3,
    step: "precombat_main",
    active_player: "you",
    players: {},
    stack: [],
    priority: "you",
    passed: [],
    yet_to_pass: ["you", "them"],
    over: null,
    ...over,
  };
}

describe("the order the stack is shown in", () => {
  it("puts the spell that resolves first at the top", () => {
    // Cast Bears, then Growth in answer to it (CR 117.7). The wire sends the
    // stack bottom first because that is how it was built (CR 405.2); Growth
    // resolves first, so Growth is what a person reads first.
    const shown = waiting(board({ stack: [BEAR, GROWTH] }));
    expect(shown.map((one) => one.name)).toEqual(["Giant Growth", "Grizzly Bears"]);
  });

  it("leaves an empty stack empty", () => {
    expect(waiting(board())).toEqual([]);
  });
});

describe("whose moment it is", () => {
  it("says so when it is this device's", () => {
    expect(whoseMove(board({ priority: "you" }), "you")).toBe("Your move");
  });

  it("says who it is waiting for when it is the other seat's", () => {
    expect(whoseMove(board({ priority: "them" }), "you")).toBe("Waiting for them");
  });

  it("distinguishes both-passed from nobody-can-act", () => {
    // Two different reasons nobody holds priority, and a player needs to know
    // which: one means a spell is about to resolve (CR 117.4), the other means
    // the untap or cleanup step (CR 502.4, CR 514.3). A single blank line for
    // both would say neither.
    const resolvingNow = board({ priority: null, passed: ["you", "them"], stack: [BEAR] });
    expect(whoseMove(resolvingNow, "you")).toBe("Both passed — the top spell resolves");
    const untapping = board({ priority: null, step: "untap" });
    expect(whoseMove(untapping, "you")).toBe("Nobody can act right now");
  });
});

describe("what resolves next", () => {
  it("offers nothing while somebody may still act", () => {
    // CR 117.4: the top of the stack resolves when all players pass in
    // succession. One of them still holding priority is not that.
    expect(resolving(board({ stack: [BEAR], priority: "them" }), "you")).toBeUndefined();
  });

  it("offers nothing when nobody may act and the stack is empty", () => {
    expect(resolving(board({ priority: null }), "you")).toBeUndefined();
  });

  it("names the top spell, its seat and its zone once everybody has passed", () => {
    const next = resolving(board({ stack: [BEAR], priority: null, passed: ["you", "them"] }), "you");
    expect(next).toEqual({ card: BEAR, yours: true, to: "battlefield" });
  });

  it("marks a spell the other seat controls as not this one's to resolve", () => {
    const next = resolving(
      board({ stack: [GROWTH], priority: null, passed: ["you", "them"] }),
      "you",
    );
    expect(next?.yours).toBe(false);
  });

  it("does not invent a zone for a card the coach cannot identify", () => {
    // The app must not guess where a spell resolves: the engine holds no card
    // data, `guard` refuses the resolution for the same reason, and a guess
    // would be how an Opt ends up on the battlefield for the rest of a game.
    const mystery = { ...BEAR, resolves_to: null };
    const next = resolving(
      board({ stack: [mystery], priority: null, passed: ["you", "them"] }),
      "you",
    );
    expect(next?.to).toBe("");
  });
});
