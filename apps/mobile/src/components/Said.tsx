/**
 * What the coach said at one moment of a game that has already been played.
 *
 * A component of its own because a replayed answer is not a live one: it is
 * already been checked, already been acted on or refused, and the screen's job
 * is to report that rather than offer it. `Coaching` is the live version.
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
      {moment.trusted ? null : <Objections problems={moment.problems} />}
    </Panel>
  );
}

/**
 * Where the engine disagreed, in the engine's own words.
 *
 * Shown rather than hidden. A moment where the coach was wrong and the engine
 * caught it is one of the most useful ones to walk through -- it is the rule
 * being stated out loud -- and the advice was never played, so hiding it would
 * teach less and match the game less.
 */
function Objections({ problems }: { readonly problems: readonly string[] }) {
  return (
    <View style={styles.objections}>
      <Text style={styles.head}>The engine disagreed, so this was not played:</Text>
      {problems.map((problem) => (
        <Text key={problem} style={styles.objection}>{`· ${problem}`}</Text>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  short: { color: colour.text, fontSize: text.body },
  because: { color: colour.quiet, fontSize: text.small, paddingTop: space.small },
  quiet: { color: colour.quiet, fontSize: text.small },
  objections: { paddingTop: space.small },
  head: { color: colour.no, fontSize: text.small, fontWeight: "600" },
  objection: { color: colour.no, fontSize: text.small },
});
