/**
 * Tell React it is allowed to be rendered by a test.
 *
 * Without this every `act()` prints "The current testing environment is not
 * configured to support act(...)" to stderr. The tests pass either way, but a
 * gate that prints warnings on a green run teaches everyone to ignore it.
 */

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean | undefined;
}

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

export {};
