/**
 * Colours and spacing, in one place.
 *
 * Sized for the table this is used at: a phone propped against a deck box, in
 * whatever light a kitchen has, read by someone who is nine. Big text, high
 * contrast, and the difference between "you can" and "you cannot" carried by
 * more than colour alone -- the words say it too.
 */

export const colour = {
  background: "#12141a",
  panel: "#1b1f29",
  panelEdge: "#2a303e",
  text: "#eef1f7",
  quiet: "#9aa3b5",
  yes: "#5cd18a",
  no: "#e2707a",
  warn: "#e8b84b",
  accent: "#6ea8fe",
} as const;

export const space = {
  tight: 4,
  small: 8,
  medium: 12,
  large: 18,
} as const;

export const text = {
  title: 22,
  heading: 17,
  body: 15,
  small: 13,
} as const;
