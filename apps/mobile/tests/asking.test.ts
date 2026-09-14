/**
 * A rules answer on its way to the screen.
 *
 * The answer began inside a language model; the retrieved passages did not.
 * The guard checks the whole payload down to what the screen dereferences,
 * because a malformed `rules` entry would crash one render later inside a
 * `.map`, which is the worst place for a type error to surface.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { Coach, ServerError } from "../src/client";
import type { Asked } from "../src/wire";
import { isAsked } from "../src/wire";

const ASKED: Asked = {
  answer: {
    answer: "Lethal damage goes to the blocker first; the rest tramples over.",
    in_short: "The extra damage still gets through.",
    citations: ["702.19b"],
    unsure: "",
  },
  trusted: true,
  rules: [
    { reference: "702.19b", title: "Trample", text: "The controller of an attacking creature…" },
  ],
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

describe("asking a rules question", () => {
  it("sends the question and the seat", async () => {
    const stub = replying(200, ASKED);
    vi.stubGlobal("fetch", stub);
    const reply = await new Coach("http://x").ask("g1", "how does trample work?", "them");
    expect(reply.answer.citations).toEqual(["702.19b"]);
    expect(stub).toHaveBeenCalledWith(
      "http://x/games/g1/ask",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question: "how does trample work?", player: "them" }),
      }),
    );
  });

  it("keeps the retrieved rules even when the answer was refused", async () => {
    vi.stubGlobal("fetch", replying(200, { ...ASKED, trusted: false }));
    const reply = await new Coach("http://x").ask("g1", "q", "you");
    expect(reply.trusted).toBe(false);
    expect(reply.rules).toHaveLength(1);
  });

  it("passes on the server's sentence when the rules are not installed", async () => {
    vi.stubGlobal(
      "fetch",
      replying(503, { detail: "the Comprehensive Rules are not installed on this server" }),
    );
    await expect(new Coach("http://x").ask("g1", "q", "you")).rejects.toThrow(/not installed/);
  });

  it("refuses a reply it cannot read rather than rendering undefined", async () => {
    vi.stubGlobal("fetch", replying(200, { trusted: true, rules: [], answer: { answer: 7 } }));
    await expect(new Coach("http://x").ask("g1", "q", "you")).rejects.toBeInstanceOf(ServerError);
  });
});

describe("recognising a rules answer", () => {
  it("accepts the agreed shape", () => {
    expect(isAsked(ASKED)).toBe(true);
  });

  it("accepts an answer that retrieved nothing", () => {
    expect(isAsked({ ...ASKED, rules: [] })).toBe(true);
  });

  it.each([
    ["null", null],
    ["an array", [ASKED]],
    ["no answer", { trusted: true, rules: [] }],
    ["no verdict", { answer: ASKED.answer, rules: [] }],
    ["no rules list", { answer: ASKED.answer, trusted: true }],
    ["rules that are not a list", { ...ASKED, rules: { a: 1 } }],
    ["a rule with no text", { ...ASKED, rules: [{ reference: "1", title: "x" }] }],
    ["a rule that is not an object", { ...ASKED, rules: ["702.19b"] }],
    [
      "citations that are not strings",
      { ...ASKED, answer: { ...ASKED.answer, citations: [7] } },
    ],
    [
      "a missing unsure field",
      { ...ASKED, answer: { ...ASKED.answer, unsure: undefined } },
    ],
  ])("rejects %s", (_name: string, value: unknown) => {
    expect(isAsked(value)).toBe(false);
  });
});
