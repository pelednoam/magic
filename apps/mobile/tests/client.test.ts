/** Talking to the server, with the server stubbed out. */

import { afterEach, describe, expect, it, vi } from "vitest";

import { Coach, ServerError } from "../src/client";

/** Any token: these assert on what is sent, not on what the token is. */
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

describe("asking", () => {
  it("lists the decks", async () => {
    vi.stubGlobal("fetch", replying(200, { decks: ["cats", "elves"] }));
    expect(await new Coach("http://x", TOKEN).decks()).toEqual(["cats", "elves"]);
  });

  it("starts a game", async () => {
    const stub = replying(200, { session_id: "abc" });
    vi.stubGlobal("fetch", stub);
    const game = await new Coach("http://x", TOKEN).start("cats", "elves");
    expect(game.session_id).toBe("abc");
    expect(stub).toHaveBeenCalledWith(
      "http://x/games",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("trims a trailing slash off the address", async () => {
    const stub = replying(200, { decks: [] });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x/", TOKEN).decks();
    expect(stub).toHaveBeenCalledWith("http://x/decks", expect.anything());
  });
});

describe("when the server says no", () => {
  it("carries the server's own sentence, which is better than ours", async () => {
    vi.stubGlobal("fetch", replying(400, { detail: "Grizzly Bears is not a land" }));
    await expect(new Coach("http://x", TOKEN).undo("g")).rejects.toThrow("Grizzly Bears is not a land");
  });

  it("carries the status too", async () => {
    vi.stubGlobal("fetch", replying(404, { detail: "no such game" }));
    const failure = await new Coach("http://x", TOKEN).look("g").catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ServerError);
    expect((failure as ServerError).status).toBe(404);
  });

  it("says something useful when the body is not the usual shape", async () => {
    vi.stubGlobal("fetch", replying(500, "<html>gateway</html>"));
    await expect(new Coach("http://x", TOKEN).decks()).rejects.toThrow("the server said 500");
  });

  it("says something useful when the detail is empty", async () => {
    vi.stubGlobal("fetch", replying(400, { detail: "" }));
    await expect(new Coach("http://x", TOKEN).decks()).rejects.toThrow("the server said 400");
  });
});

describe("watching", () => {
  it("turns the address into a socket one", () => {
    expect(new Coach("http://laptop:8000", TOKEN).watchUrl("g")).toBe(
      "ws://laptop:8000/games/g/watch?token=t",
    );
  });

  it("keeps a secure connection secure", () => {
    expect(new Coach("https://laptop:8000", TOKEN).watchUrl("g")).toBe(
      "wss://laptop:8000/games/g/watch?token=t",
    );
  });
});

describe("the token", () => {
  it("goes on every request as a bearer header", async () => {
    const stub = replying(200, { decks: [] });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x", "sekrit").decks();
    expect(stub).toHaveBeenCalledWith(
      "http://x/decks",
      expect.objectContaining({ headers: { Authorization: "Bearer sekrit" } }),
    );
  });

  it("goes on a write as well as a read", async () => {
    const stub = replying(200, { session_id: "g" });
    vi.stubGlobal("fetch", stub);
    await new Coach("http://x", "sekrit").start("cats", "elves");
    expect(stub).toHaveBeenCalledWith(
      "http://x/games",
      expect.objectContaining({
        headers: { Authorization: "Bearer sekrit", "Content-Type": "application/json" },
      }),
    );
  });

  it("is escaped in the socket URL, which is a URL", async () => {
    expect(new Coach("http://x", "a b/c").watchUrl("g")).toBe(
      "ws://x/games/g/watch?token=a%20b%2Fc",
    );
  });

  it("says when the server refused for want of one", async () => {
    vi.stubGlobal("fetch", replying(401, { detail: "this server needs its token" }));
    // The start screen shows a field on this, rather than "unauthorized" to
    // somebody who has no idea what that means.
    await expect(new Coach("http://x", "").decks()).rejects.toMatchObject({
      needsToken: true,
    });
  });

  it("does not call any other refusal a token problem", async () => {
    vi.stubGlobal("fetch", replying(400, { detail: "unknown deck" }));
    await expect(new Coach("http://x", "t").decks()).rejects.toMatchObject({
      needsToken: false,
    });
  });
});
