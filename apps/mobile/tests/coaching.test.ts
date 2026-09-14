/**
 * The coach's reply, on its way to the screen.
 *
 * This payload started life inside a language model. The server checked it
 * against the rules engine; these check that what arrived is the shape the app
 * dereferences, and that a reply the engine rejected cannot be read as advice.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { Coach, ServerError } from "../src/client";
import { planFor } from "../src/format";
import type { Coaching, Plan } from "../src/wire";
import { isCoaching } from "../src/wire";

/** Any token: these assert on what is sent, not on what the token is. */
const TOKEN = "t";

const ANSWER: Coaching = {
  explanation: {
    play: "land-1",
    attack: ["bear-1"],
    because: "It trades up.",
    in_short: "Yours is bigger.",
    watch_out: ["They have a card up."],
    check_yourself: [],
  },
  trusted: true,
  version: 0,
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

describe("asking for advice", () => {
  it("sends the seat and returns the answer", async () => {
    const stub = replying(200, ANSWER);
    vi.stubGlobal("fetch", stub);
    const reply = await new Coach("http://x", TOKEN).explain("g1", "them");
    expect(reply.explanation.in_short).toBe("Yours is bigger.");
    expect(stub).toHaveBeenCalledWith(
      "http://x/games/g1/coach",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ player: "them" }) }),
    );
  });

  it("keeps the untrusted flag rather than dropping the answer", async () => {
    vi.stubGlobal("fetch", replying(200, { ...ANSWER, trusted: false }));
    const reply = await new Coach("http://x", TOKEN).explain("g1", "you");
    expect(reply.trusted).toBe(false);
  });

  it("passes on the server's sentence when there is no coach", async () => {
    vi.stubGlobal("fetch", replying(503, { detail: "could not ask the coach: no claude" }));
    await expect(new Coach("http://x", TOKEN).explain("g1", "you")).rejects.toThrow(
      /no claude/,
    );
  });

  it("refuses a reply it cannot read rather than rendering undefined", async () => {
    vi.stubGlobal("fetch", replying(200, { explanation: { play: 7 }, trusted: true }));
    await expect(new Coach("http://x", TOKEN).explain("g1", "you")).rejects.toBeInstanceOf(
      ServerError,
    );
  });
});

describe("recognising a reply", () => {
  it("accepts the agreed shape", () => {
    expect(isCoaching(ANSWER)).toBe(true);
  });

  it.each([
    ["null", null],
    ["an array", [ANSWER]],
    ["a string", "yes"],
    ["no explanation", { trusted: true }],
    ["no verdict", { explanation: ANSWER.explanation }],
    ["a verdict that is not a boolean", { ...ANSWER, trusted: "yes" }],
    ["a play that is not a string", { ...ANSWER, explanation: { ...ANSWER.explanation, play: 1 } }],
    [
      "an attack that is not a list",
      { ...ANSWER, explanation: { ...ANSWER.explanation, attack: "bear-1" } },
    ],
    [
      "an attack holding something that is not a string",
      { ...ANSWER, explanation: { ...ANSWER.explanation, attack: [1] } },
    ],
    [
      "missing words",
      { ...ANSWER, explanation: { ...ANSWER.explanation, in_short: undefined } },
    ],
  ])("rejects %s", (_name: string, value: unknown) => {
    expect(isCoaching(value)).toBe(false);
  });
});

function plan(ids: readonly string[]): Plan {
  return {
    attackers: ids.map((id) => id.toUpperCase()),
    attacker_ids: ids,
    damage: ids.length,
    defender_life_after: 20 - ids.length,
    lethal: false,
    you_lose: [],
    they_lose: [],
    you_gain: 0,
    they_gain: 0,
  };
}

describe("finding the plan the coach chose", () => {
  const plans = [plan(["a"]), plan(["a", "b"]), plan(["b"])];

  it("matches regardless of the order the ids came back in", () => {
    expect(planFor(plans, ["b", "a"])?.attacker_ids).toEqual(["a", "b"]);
  });

  it("does not match a subset", () => {
    expect(planFor([plan(["a", "b"])], ["a"])).toBeUndefined();
  });

  it("has nothing to show for an empty recommendation", () => {
    expect(planFor(plans, [])).toBeUndefined();
  });

  it("has nothing to show for a plan that is not there", () => {
    expect(planFor(plans, ["ghost"])).toBeUndefined();
  });
});
