/**
 * Talking to the server. No rules, no interpretation, no caching of judgement.
 *
 * Every call returns what the server said. The one piece of policy here is what
 * to do when it says no: an error carries the server's own sentence, because
 * the server writes better ones than a client can ("you need one more Forest",
 * not "400").
 */

import type { Coaching, NewGame, Snapshot } from "./wire";
import { isCoaching } from "./wire";

/** The server refused, and said why. */
export class ServerError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ServerError";
    this.status = status;
  }
}

/** How to reach the server, and how to ask it things. */
export class Coach {
  private readonly base: string;

  constructor(base: string) {
    this.base = base.replace(/\/+$/, "");
  }

  /** The decks this server can deal. */
  async decks(): Promise<readonly string[]> {
    const body = await this.get<{ decks: readonly string[] }>("/decks");
    return body.decks;
  }

  /** Start a game between two of them. */
  async start(you: string, them: string): Promise<NewGame> {
    return this.send<NewGame>("POST", "/games", { you, them });
  }

  /**
   * The board and the advice, as they stand.
   *
   * Also how a second device *joins*: a game is a session id, and anyone who
   * has it can open it. There is no auth, which PLAN.md records as a known
   * gap -- the server is meant for one LAN and one table.
   */
  async look(sessionId: string): Promise<Snapshot> {
    return this.get<Snapshot>(`/games/${segment(sessionId)}`);
  }

  /** Apply one event. The server decides whether it is legal. */
  async event(sessionId: string, event: Record<string, unknown>): Promise<Snapshot> {
    return this.send<Snapshot>("POST", `/games/${segment(sessionId)}/events`, event);
  }

  /** Take the last event back. */
  async undo(sessionId: string): Promise<Snapshot> {
    return this.send<Snapshot>("POST", `/games/${segment(sessionId)}/undo`, {});
  }

  /**
   * Ask Claude about this turn.
   *
   * Slow on purpose -- it is a subprocess on the server, not a lookup -- and
   * separate from every other call for exactly that reason. The engine's own
   * advice is already on screen and arrived instantly; this is the button you
   * press when that is not enough.
   *
   * A 503 means no answer could be got at all. That is a `ServerError` like
   * any other, and the panel it is shown in is the only thing that changes.
   */
  async explain(sessionId: string, player: string): Promise<Coaching> {
    const body = await this.send<unknown>("POST", `/games/${segment(sessionId)}/coach`, {
      player,
    });
    if (!isCoaching(body)) {
      throw new ServerError(0, "the server sent an answer this app cannot read");
    }
    return body;
  }

  /**
   * The address to watch a game on, for whoever owns the socket.
   *
   * The scheme swap is explicit rather than `replace(/^http/, "ws")`, which
   * silently produced a malformed URL for anything that was not lower-case
   * `http` -- including `HTTPS://`, which browsers accept.
   */
  watchUrl(sessionId: string): string {
    const socketBase = this.base.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:");
    return `${socketBase}/games/${segment(sessionId)}/watch`;
  }

  private async get<T>(path: string): Promise<T> {
    return this.unwrap<T>(await fetch(`${this.base}${path}`));
  }

  private async send<T>(
    method: string,
    path: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    const response = await fetch(`${this.base}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return this.unwrap<T>(response);
  }

  private async unwrap<T>(response: Response): Promise<T> {
    if (response.ok) {
      return (await response.json()) as T;
    }
    throw new ServerError(response.status, await detailOf(response));
  }
}

/**
 * The server's explanation, or a plain one if it did not give the usual shape.
 *
 * Never throws: this runs while handling an error, and an exception here would
 * replace a useful message with a confusing one.
 */
async function detailOf(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === "string" && detail.length > 0) {
        return detail;
      }
    }
  } catch {
    // Not JSON, or the connection went away mid-read. Fall through.
  }
  return `the server said ${response.status}`;
}

/** One path segment, escaped. A session id comes from the server, but a URL
 *  built by concatenation is a habit worth not having. */
function segment(value: string): string {
  return encodeURIComponent(value);
}
