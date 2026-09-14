/** The two narrowing helpers every guard in this folder is built from. */

/** An array of strings, and nothing else. */
export function isStrings(value: unknown): value is readonly string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * A plain object, or null.
 *
 * Arrays are excluded: `typeof [] === "object"` and `[] !== null`, so the
 * looser check accepted a JSON array as a snapshot.
 */
export function asObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}
