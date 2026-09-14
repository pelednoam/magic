/**
 * What to put on screen when something failed.
 *
 * One function, in its own file, because it is the only thing several screens
 * and both hooks agree on — and because it used to live inside a screen, which
 * meant importing it dragged the whole of `react-native` along. That made
 * `thinking.ts` untestable: rollup cannot parse React Native's Flow entry
 * point, so a test that touched the hooks could not even be collected.
 */

/**
 * The server's own sentence, or a plain one.
 *
 * `ServerError` carries what the server said, and the server writes better
 * messages than a client can — "you need one more Forest", not "400".
 */
export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "could not reach the server";
}
