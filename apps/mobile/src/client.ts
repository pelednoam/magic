/**
 * Talking to the server. No rules, no interpretation, no caching of judgement.
 *
 * Every call returns what the server said. The one piece of policy here is what
 * to do when it says no: an error carries the server's own sentence, because
 * the server writes better ones than a client can ("you need one more Forest",
 * not "400").
 */

import { ServerError } from "./failures";
import { Http, segment } from "./transport";

import type { Asked, Coaching, NewGame, PlayedGame, Snapshot, Walkthrough } from "./wire";
import { isAsked, isCoaching, isJournals, isPlayedGame, isWalkthrough } from "./wire";

// Re-exported: every caller already imports it from here, and where the class
// happens to live is not their business.
export { ServerError } from "./failures";

/** How to reach the server, and how to ask it things. */
export class Coach {
  private readonly http: Http;

  constructor(base: string, token: string) {
    this.http = new Http(base, token);
  }

  /** The same server, with a different token. Used when one is typed in. */
  withToken(token: string): Coach {
    return new Coach(this.http.base, token);
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
   * Ask a rules question.
   *
   * The server searches the Comprehensive Rules first and answers from what it
   * found, so the reply carries the passages as well as the answer. Slow for
   * the same reason as `explain`, and 503 when the rules are not installed on
   * that server -- which is a legitimate way to run it.
   */
  async ask(sessionId: string, question: string, player: string): Promise<Asked> {
    const body = await this.send<unknown>("POST", `/games/${segment(sessionId)}/ask`, {
      question,
      player,
    });
    if (!isAsked(body)) {
      throw new ServerError(0, "the server sent an answer this app cannot read");
    }
    return body;
  }

  /** The played games this server has kept, newest first. */
  async replays(): Promise<readonly string[]> {
    const body = await this.get<unknown>("/replays");
    if (!isJournals(body)) {
      throw new ServerError(0, "the server sent a list this app cannot read");
    }
    return body.replays;
  }

  /**
   * What is in one journal: a line per game, and no boards.
   *
   * Without the moments on purpose. A twelve-game coached season is several
   * megabytes once every position is serialised, and this is read to choose
   * between a few lines of text.
   */
  async walkthrough(name: string): Promise<Walkthrough> {
    const body = await this.get<unknown>(`/replays/${segment(name)}`);
    if (!isWalkthrough(body)) {
      throw new ServerError(0, "the server sent a replay this app cannot read");
    }
    return body;
  }

  /**
   * One game, with every moment of it.
   *
   * The whole game in one request, deliberately: stepping should be instant,
   * and a request per step would make the back button slower than the forward
   * one — the wrong way round for a screen whose purpose is going back over
   * something. Addressed by position, because two runs into one journal repeat
   * a seed and a seed is then not an address.
   */
  async game(name: string, index: number): Promise<PlayedGame> {
    const body = await this.get<unknown>(`/replays/${segment(name)}/${index}`);
    if (!isPlayedGame(body)) {
      throw new ServerError(0, "the server sent a game this app cannot read");
    }
    return body;
  }

  /**
   * Open one moment of a played game as a game of its own.
   *
   * Which is what makes a replay answer questions: from here it is an ordinary
   * session, so `ask`, `explain` and `event` all work on a position out of last
   * night's game. Nothing is re-asked to produce it -- the board is the one the
   * recorded events actually built.
   */
  async stepInto(name: string, game: number, index: number): Promise<NewGame> {
    return this.send<NewGame>("POST", `/replays/${segment(name)}/${game}/at/${index}`, {});
  }

  /**
   * The address to watch a game on, for whoever owns the socket.
   *
   * The scheme swap is explicit rather than `replace(/^http/, "ws")`, which
   * silently produced a malformed URL for anything that was not lower-case
   * `http` -- including `HTTPS://`, which browsers accept.
   */
  watchUrl(sessionId: string): string {
    // The token goes in the query string because a page cannot set headers on
    // a WebSocket handshake. That is a real if small cost -- a query string
    // reaches logs and browser history in a way a header does not -- and the
    // alternative is a socket nobody can open from a browser.
    const token = encodeURIComponent(this.http.token);
    return `${this.http.socketBase()}/games/${segment(sessionId)}/watch?token=${token}`;
  }

  private async get<T>(path: string): Promise<T> {
    return this.http.get<T>(path);
  }

  private async send<T>(
    method: string,
    path: string,
    body: Record<string, unknown>,
  ): Promise<T> {
    return this.http.send<T>(method, path, body);
  }
}
