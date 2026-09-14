/**
 * What a refusal looks like on this side of the wire.
 *
 * The server writes better messages than a client can — "you need one more
 * Forest", not "400" — so the policy here is to carry its sentence through
 * and add nothing. The one thing worth interpreting is a 401, because the
 * start screen has something useful to do about that: ask for the token.
 */

/** The server refused, and said why. */
export class ServerError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ServerError";
    this.status = status;
  }

  /**
   * Whether this was the server saying "you have the wrong token".
   *
   * The start screen asks for one when it sees this, rather than showing
   * "unauthorized" to somebody who has no idea what that means.
   */
  get needsToken(): boolean {
    return this.status === UNAUTHORIZED;
  }
}

/** What the server answers a request with no usable token. */
const UNAUTHORIZED = 401;


/**
 * The server's explanation, or a plain one if it did not give the usual shape.
 *
 * Never throws: this runs while handling an error, and an exception here would
 * replace a useful message with a confusing one.
 */
export async function detailOf(response: Response): Promise<string> {
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
