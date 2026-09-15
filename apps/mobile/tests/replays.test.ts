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
import { placeOf, seatName } from "../src/format";
import { isJournals, isWalkthrough } from "../src/wire";

const TOKEN = "t";

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

  it("fetches a whole journal in one request", async () => {
    const stub = replying(200, { games: [] });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x", TOKEN).walkthrough("overnight");
    expect(stub).toHaveBeenCalledWith("http://x/replays/overnight", expect.anything());
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
    const game = await new Coach("http://x", TOKEN).stepInto("overnight", 77, 20);
    expect(game.session_id).toBe("abc");
    expect(stub).toHaveBeenCalledWith(
      "http://x/replays/overnight/77/at/20",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("recognising what came back", () => {
  it("knows a walkthrough", () => {
    expect(isWalkthrough({ games: [] })).toBe(true);
  });

  it("knows a list of journals", () => {
    expect(isJournals({ replays: [] })).toBe(true);
  });

  it.each([null, "games", {}, { games: 3 }, { replays: 3 }])("rejects %o", (body) => {
    expect(isWalkthrough(body)).toBe(false);
    expect(isJournals(body)).toBe(false);
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
