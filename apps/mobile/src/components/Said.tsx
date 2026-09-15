/**
 * What the coach said at one moment of a game that has already been played.
 *
 * A component of its own because a replayed answer is not a live one: it has
 * already been checked, already been acted on or refused, and the screen's job
 * is to report that rather than offer it. `Coaching` is the live version.
 *
 * It shows the *whole* answer. The first version showed only the headline and
 * the reason, and labelled that "checked" — so a caveat the coach had written
 * ("they have two untapped lands") and a thing it had asked the player to
 * verify for themselves ("count their blockers first") were dropped, while the
 * remaining prose carried the badge saying the engine had agreed with it. On
 * the screen somebody learns the rules from, that is the wrong half to keep.
 */

import { StyleSheet, Text, View } from "react-native";

import { colour, space, text } from "../theme";
import type { Moment } from "../wire";

import { Panel } from "./Panel";

export function Said({ moment }: { readonly moment: Moment }) {
  if (moment.said === null) {
    return (
      <Panel title="No advice here">
        <Text style={styles.quiet}>
          {moment.error === "" ? "The coach had no answer at this moment." : moment.error}
        </Text>
      </Panel>
    );
  }
  return (
    <Panel title="The coach said" note={moment.trusted ? "checked" : "not checked"}>
      <Text style={styles.short}>{moment.said.in_short}</Text>
      {moment.said.because === "" ? null : (
        <Text style={styles.because}>{moment.said.because}</Text>
      )}
      <Bullets items={moment.said.watch_out} style={styles.watch} />
      <Bullets items={moment.said.check_yourself} style={styles.check} />
      {moment.trusted ? null : <Objections problems={moment.problems} />}
    </Panel>
  );
}

/**
 * Where the engine disagreed, in the engine's own words.
 *
 * Shown rather than hidden. A moment where the coach was wrong and the engine
 * caught it is one of the most useful ones to walk through — it is the rule
 * being stated out loud — and the advice was never played, so hiding it would
 * teach less and match the game less.
 */
function Objections({ problems }: { readonly problems: readonly string[] }) {
  return (
    <View style={styles.objections}>
      <Text style={styles.head}>The engine disagreed, so this was not played:</Text>
      <Bullets items={problems} style={styles.objection} />
    </View>
  );
}

/** A list of short lines, in whatever colour says what kind they are. */
function Bullets({
  items,
  style,
}: {
  readonly items: readonly string[];
  readonly style: { readonly color: string };
}) {
  return (
    <>
      {/* Keyed by position as well as text. The words come from a model and
          repeat often enough to matter -- two identical "check the Pacifism"
          lines silently collapsed into one. */}
      {items.map((item, at) => (
        <Text key={`${at}-${item}`} style={[styles.bullet, style]}>
          {`• ${item}`}
        </Text>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  short: { color: colour.text, fontSize: text.body },
  because: { color: colour.quiet, fontSize: text.small, paddingTop: space.small },
  quiet: { color: colour.quiet, fontSize: text.small },
  bullet: { fontSize: text.small, paddingTop: space.tight },
  watch: { color: colour.warn },
  check: { color: colour.accent },
  objections: { paddingTop: space.small },
  head: { color: colour.no, fontSize: text.small, fontWeight: "600" },
  objection: { color: colour.no },
});
