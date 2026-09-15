/**
 * The replay half of the client, and the wording the stepper puts on screen.
 *
 * The screens themselves are out of reach here -- importing one pulls in
 * `react-native`, whose entry point is Flow and which rollup cannot parse -- so
 * everything a replay screen decides lives in `format.ts` or in these guards,
 * and is tested from there. That is the same bargain the rest of this suite
 * makes; see `vitest.config.ts`.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { Coach, ServerError } from "../src/client";
import { nameOf, placeOf, seatName } from "../src/format";
import { isJournals, isPlayedGame, isWalkthrough } from "../src/wire";

const TOKEN = "t";

/** One line of a journal's game list. */
const LINE = { index: 2, seed: 77, decks: ["inferno", "healing"], decisions: 81 };

/** A board with one card on it, for naming a checked choice. */
const BOARD = {
  life: 20,
  library: 30,
  lands_played_this_turn: 0,
  hand: [{ instance_id: "you-7", oracle_id: "uuid", name: "Skyship Buccaneer" }],
  battlefield: [],
  graveyard: [],
  exile: [],
};

/** One moment, down to what the stepper actually dereferences. */
const MOMENT = {
  turn: 7,
  step: "declare_attackers",
  player: "you",
  state: { turn: 7, step: "declare_attackers", active_player: "you", players: { you: {}, them: {} } },
  said: null,
  trusted: false,
  problems: [],
  error: "",
};

function replying(status: number, body: unknown): typeof fetch {
  return vi.fn(
    async () =>
      new Response(typeof body === "string" ? body : JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  ) as unknown as typeof fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("asking for replays", () => {
  it("lists the journals", async () => {
    vi.stubGlobal("fetch", replying(200, { replays: ["overnight", "demo"] }));
    expect(await new Coach("http://x", TOKEN).replays()).toEqual(["overnight", "demo"]);
  });

  it("refuses a list it cannot read, rather than handing back undefined", async () => {
    vi.stubGlobal("fetch", replying(200, { games: [] }));
    await expect(new Coach("http://x", TOKEN).replays()).rejects.toBeInstanceOf(ServerError);
  });

  it("lists a journal's games without their boards", async () => {
    const stub = replying(200, { games: [LINE] });
    vi.stubGlobal("fetch", stub);
    const walk = await new Coach("http://x", TOKEN).walkthrough("overnight");
    expect(walk.games[0]?.decisions).toBe(81);
    expect(stub).toHaveBeenCalledWith("http://x/replays/overnight", expect.anything());
  });

  it("fetches one game whole, addressed by position", async () => {
    const stub = replying(200, { ...LINE, moments: [MOMENT] });
    vi.stubGlobal("fetch", stub);
    const game = await new Coach("http://x", TOKEN).game("overnight", 2);
    expect(game.moments).toHaveLength(1);
    expect(stub).toHaveBeenCalledWith("http://x/replays/overnight/2", expect.anything());
  });

  it("refuses a game whose moments have no board", async () => {
    // The shallow guard let this through and the crash arrived one render
    // later, inside `moment.state.players`, far from the frame that caused it.
    vi.stubGlobal("fetch", replying(200, { ...LINE, moments: [{ turn: 1, step: "upkeep" }] }));
    await expect(new Coach("http://x", TOKEN).game("x", 0)).rejects.toBeInstanceOf(ServerError);
  });

  it("escapes a journal name, because a file is called whatever it is called", async () => {
    const stub = replying(200, { games: [] });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x", TOKEN).walkthrough("last night/run");
    expect(stub).toHaveBeenCalledWith("http://x/replays/last%20night%2Frun", expect.anything());
  });

  it("refuses a walkthrough it cannot read", async () => {
    vi.stubGlobal("fetch", replying(200, { replays: [] }));
    await expect(new Coach("http://x", TOKEN).walkthrough("x")).rejects.toBeInstanceOf(ServerError);
  });

  it("steps into a moment as a game", async () => {
    const stub = replying(200, { session_id: "abc" });
    vi.stubGlobal("fetch", stub);
    const game = await new Coach("http://x", TOKEN).stepInto("overnight", 3, 20);
    expect(game.session_id).toBe("abc");
    expect(stub).toHaveBeenCalledWith(
      "http://x/replays/overnight/3/at/20",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("recognising what came back", () => {
  it("knows a walkthrough", () => {
    expect(isWalkthrough({ games: [LINE] })).toBe(true);
  });

  it("knows a list of journals", () => {
    expect(isJournals({ replays: ["a"] })).toBe(true);
  });

  it("knows a played game", () => {
    expect(isPlayedGame({ ...LINE, moments: [MOMENT] })).toBe(true);
  });

  it.each([null, "games", {}, { games: 3 }, { replays: 3 }])("rejects %o", (body) => {
    expect(isWalkthrough(body)).toBe(false);
    expect(isJournals(body)).toBe(false);
    expect(isPlayedGame(body)).toBe(false);
  });

  // These are the shapes a shallow guard accepted and a screen then crashed
  // on, one render after the frame that caused it.
  it.each([
    { games: [{ index: 0 }] },
    { games: [{ index: 0, seed: 1, decks: [2] }] },
    { replays: [3] },
  ])("rejects malformed contents %o", (body) => {
    expect(isWalkthrough(body) || isJournals(body)).toBe(false);
  });

  it.each([
    { ...LINE, moments: [{ turn: 1, step: "upkeep" }] },
    { ...LINE, moments: [{ ...MOMENT, state: {} }] },
    { ...LINE, moments: [{ ...MOMENT, problems: "none" }] },
    { ...LINE, moments: "all of them" },
  ])("rejects a game whose moments will not render %o", (body) => {
    expect(isPlayedGame(body)).toBe(false);
  });
});

describe("saying where in a game a moment is", () => {
  it("uses words a child says out loud", () => {
    expect(placeOf(7, "declare_attackers")).toBe("Turn 7, attacking");
  });

  it("keeps a step it does not know, rather than guessing at it", () => {
    // A wrong word here would teach a wrong rule, which is worse than an
    // unfamiliar one. The step ids are the rules' own names and are correct.
    expect(placeOf(1, "first_strike_damage")).toBe("Turn 1, first_strike_damage");
  });

  it("marks the seat that was being asked", () => {
    expect(seatName("you", "You", "you")).toBe("You — choosing here");
    expect(seatName("them", "Them", "you")).toBe("Them");
  });
});

describe("what the replay panel may claim was checked", () => {
  // `advice.verify` checks the card named in `play` and the attack named in
  // `attack`. It checks nothing about `in_short` or `because`, which are prose
  // a model wrote. A badge over the prose is a claim about the wrong text.
  it("names the checked choice from the board it was made on", () => {
    expect(nameOf(BOARD, "you-7")).toBe("Skyship Buccaneer");
  });

  it("falls back to the identifier for a card the board no longer holds", () => {
    // Better an unfamiliar word than a blank space, which reads as a bug.
    expect(nameOf(BOARD, "you-99")).toBe("you-99");
  });
});
