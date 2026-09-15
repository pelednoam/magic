/**
 * The bits of HTTP that are not about this server in particular.
 *
 * Split out of `client.ts` when that file reached the length limit, and the
 * seam is a real one rather than a convenience: everything here is true of any
 * JSON server carrying a bearer token, and everything left in `client.ts` is a
 * route this project has.
 */

import { ServerError, detailOf } from "./failures";

/** An address and a token, and the three ways this app uses them. */
export class Http {
  readonly base: string;
  readonly token: string;

  constructor(base: string, token: string) {
    this.base = base.replace(/\/+$/, "");
    this.token = token;
  }

  async get<T>(path: string): Promise<T> {
    return unwrap<T>(await fetch(`${this.base}${path}`, { headers: this.headers() }));
  }

  async send<T>(method: string, path: string, body: Record<string, unknown>): Promise<T> {
    return unwrap<T>(
      await fetch(`${this.base}${path}`, {
        method,
        headers: { ...this.headers(), "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    );
  }

  /**
   * The same host, as a WebSocket address.
   *
   * The scheme swap is explicit rather than `replace(/^http/, "ws")`, which
   * silently produced a malformed URL for anything that was not lower-case
   * `http` — including `HTTPS://`, which browsers accept.
   */
  socketBase(): string {
    return this.base.replace(/^https:/i, "wss:").replace(/^http:/i, "ws:");
  }

  /**
   * What every request carries.
   *
   * The server has no other access control, so a request without this gets a
   * 401 whoever sent it — including a page the household happened to visit,
   * which is the thing the token is actually for.
   */
  private headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}` };
  }
}

/**
 * One path segment, escaped.
 *
 * A session id comes from the server, but a URL built by concatenation is a
 * habit worth not having — and a journal name comes off a disk, where a file
 * can be called whatever somebody called it.
 */
export function segment(value: string): string {
  return encodeURIComponent(value);
}

/**
 * The body, or the server's own sentence about why there is not one.
 *
 * The server writes better refusals than a client can ("you need one more
 * Forest", not "400"), so the status is carried alongside its words rather
 * than in place of them.
 */
async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  throw new ServerError(response.status, await detailOf(response));
}
