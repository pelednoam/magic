/** Talking to the server, with the server stubbed out. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { Coach, ServerError } from "../src/client";

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

describe("asking", () => {
  it("lists the decks", async () => {
    vi.stubGlobal("fetch", replying(200, { decks: ["cats", "elves"] }));
    expect(await new Coach("http://x").decks()).toEqual(["cats", "elves"]);
  });

  it("starts a game", async () => {
    const stub = replying(200, { session_id: "abc" });
    vi.stubGlobal("fetch", stub);
    const game = await new Coach("http://x").start("cats", "elves");
    expect(game.session_id).toBe("abc");
    expect(stub).toHaveBeenCalledWith(
      "http://x/games",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("trims a trailing slash off the address", async () => {
    const stub = replying(200, { decks: [] });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x/").decks();
    expect(stub).toHaveBeenCalledWith("http://x/decks");
  });
});

describe("when the server says no", () => {
  it("carries the server's own sentence, which is better than ours", async () => {
    vi.stubGlobal("fetch", replying(400, { detail: "Grizzly Bears is not a land" }));
    await expect(new Coach("http://x").undo("g")).rejects.toThrow("Grizzly Bears is not a land");
  });

  it("carries the status too", async () => {
    vi.stubGlobal("fetch", replying(404, { detail: "no such game" }));
    const failure = await new Coach("http://x").look("g").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ServerError);
    expect((failure as ServerError).status).toBe(404);
  });

  it("says something useful when the body is not the usual shape", async () => {
    vi.stubGlobal("fetch", replying(500, "<html>gateway</html>"));
    await expect(new Coach("http://x").decks()).rejects.toThrow("the server said 500");
  });

  it("says something useful when the detail is empty", async () => {
    vi.stubGlobal("fetch", replying(400, { detail: "" }));
    await expect(new Coach("http://x").decks()).rejects.toThrow("the server said 400");
  });
});

describe("watching", () => {
  it("turns the address into a socket one", () => {
    expect(new Coach("http://laptop:8000").watchUrl("g")).toBe(
      "ws://laptop:8000/games/g/watch",
    );
  });

  it("keeps a secure connection secure", () => {
    expect(new Coach("https://laptop:8000").watchUrl("g")).toBe(
      "wss://laptop:8000/games/g/watch",
    );
  });
});
