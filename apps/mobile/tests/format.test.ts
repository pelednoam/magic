/** Turning what the server said into what goes on screen. */

import { describe, expect, it } from "vitest";

import {
  listed,
  nameOf,
  paymentLine,
  permanentNote,
  planLine,
  planTitle,
  stepName,
  turnLine,
} from "../src/format";
import { isSnapshot } from "../src/wire";
import type { Permanent, Plan, Player } from "../src/wire";

const board: Player = {
  life: 20,
  library: 30,
  lands_played_this_turn: 0,
  hand: [{ instance_id: "h1", oracle_id: "bear", name: "Grizzly Bears" }],
  battlefield: [
    { instance_id: "f1", oracle_id: "forest", name: "Forest", tapped: false, summoning_sick: false },
    { instance_id: "f2", oracle_id: "forest", name: "Forest", tapped: true, summoning_sick: false },
    { instance_id: "i1", oracle_id: "island", name: "Island", tapped: false, summoning_sick: true },
  ],
  stack: [],
  graveyard: [],
  exile: [],
};

const plan: Plan = {
  attackers: ["Grizzly Bears"],
  attacker_ids: ["b1"],
  damage: 2,
  defender_life_after: 18,
  lethal: false,
  you_lose: [],
  they_lose: [],
  you_gain: 0,
  they_gain: 0,
};

describe("step names", () => {
  it("spells a step the way a person says it", () => {
    expect(stepName("precombat_main")).toBe("Precombat main");
    expect(stepName("upkeep")).toBe("Upkeep");
  });

  it("says whose turn it is when it is not yours", () => {
    expect(turnLine(3, "upkeep", true)).toBe("Turn 3 · Upkeep");
    expect(turnLine(3, "upkeep", false)).toBe("Turn 3 · Upkeep · their turn");
  });
});

describe("naming a card by its identifier", () => {
  it("finds it on the battlefield", () => {
    expect(nameOf(board, "f1")).toBe("Forest");
  });

  it("finds it in hand", () => {
    expect(nameOf(board, "h1")).toBe("Grizzly Bears");
  });

  it("falls back to the identifier, which is true and not blank", () => {
    expect(nameOf(board, "elsewhere")).toBe("elsewhere");
  });
});

describe("lists", () => {
  it("says nothing about nothing", () => {
    expect(listed([])).toBe("");
  });

  it("leaves one alone", () => {
    expect(listed(["Forest"])).toBe("Forest");
  });

  it("joins two with 'and'", () => {
    expect(listed(["Forest", "Island"])).toBe("Forest and Island");
  });

  it("commas the rest", () => {
    expect(listed(["a", "b", "c"])).toBe("a, b and c");
  });
});

describe("what to tap", () => {
  it("says which, by name", () => {
    expect(paymentLine(board, ["f1", "f2"], [])).toBe("Tap Forest and Forest");
  });

  it("says what to keep up, which is the useful half", () => {
    expect(paymentLine(board, ["f1"], ["i1"])).toBe("Tap Forest · keep Island up");
  });
});

describe("attack plans", () => {
  it("shows the maths", () => {
    expect(planLine(plan)).toBe("2 damage · they go to 18");
  });

  it("shouts about lethal", () => {
    expect(planLine({ ...plan, lethal: true, defender_life_after: -1 })).toContain("LETHAL");
  });

  it("names what dies on each side", () => {
    const trade = { ...plan, they_lose: ["Ogre"], you_lose: ["Grizzly Bears"] };
    expect(planLine(trade)).toContain("kills Ogre");
    expect(planLine(trade)).toContain("loses Grizzly Bears");
  });

  it("counts life gained", () => {
    expect(planLine({ ...plan, you_gain: 2 })).toContain("+2 life");
  });

  it("calls the empty attack what it is", () => {
    expect(planTitle({ ...plan, attackers: [] })).toBe("Hold back");
    expect(planTitle(plan)).toBe("Grizzly Bears");
  });
});

describe("permanent notes", () => {
  it("says nothing about a permanent that can act", () => {
    expect(permanentNote(board.battlefield[0] as Permanent)).toBe("");
  });

  it("says tapped", () => {
    expect(permanentNote(board.battlefield[1] as Permanent)).toBe("tapped");
  });

  it("says a creature only just arrived", () => {
    expect(permanentNote(board.battlefield[2] as Permanent)).toBe("just arrived");
  });

  it("says both when both", () => {
    const stuck = { ...(board.battlefield[2] as Permanent), tapped: true };
    expect(permanentNote(stuck)).toBe("tapped · just arrived");
  });
});

describe("a response is not a snapshot because we said so", () => {
  const good = {
    version: 0,
    rules_available: true,
    state: { players: { you: {}, them: {} } },
    advice: { you: {}, them: {} },
  };

  it("accepts the real shape", () => {
    expect(isSnapshot(good)).toBe(true);
  });

  it("rejects null, which a cast used to let through", () => {
    expect(isSnapshot(null)).toBe(false);
  });

  it("rejects a string", () => {
    expect(isSnapshot("ok")).toBe(false);
  });

  it("rejects an array, which is an object to `typeof`", () => {
    expect(isSnapshot([])).toBe(false);
  });

  it("rejects a snapshot with no version, because ordering depends on it", () => {
    expect(isSnapshot({ ...good, version: undefined })).toBe(false);
  });

  it("rejects a snapshot that does not say whether rules questions work", () => {
    // A server too old to send it would otherwise render the question box as
    // though it worked, which is the thing the flag exists to prevent.
    expect(isSnapshot({ ...good, rules_available: undefined })).toBe(false);
  });

  it("rejects a board with no players, which is what the screen reads", () => {
    expect(isSnapshot({ ...good, state: {} })).toBe(false);
  });

  it("rejects a board missing a seat", () => {
    expect(isSnapshot({ ...good, state: { players: { you: {} } } })).toBe(false);
  });

  it("rejects advice missing a seat", () => {
    expect(isSnapshot({ ...good, advice: { you: {} } })).toBe(false);
  });

  it("rejects players that is an array", () => {
    expect(isSnapshot({ ...good, state: { players: [] } })).toBe(false);
  });
});
