/**
 * The game is over, said once and plainly.
 *
 * It used to not be said at all. A player could reach 0 life and the tracker
 * would carry on: offering cards to play, advancing steps, taking advice for
 * somebody who had already lost — and the server accepted all of it, because
 * nothing in the state recorded a result.
 *
 * Said in the words a nine-year-old uses about a game they just played, and
 * with the rules reason underneath, because "you ran out of cards" and "you ran
 * out of life" are different things to learn from.
 */

import { StyleSheet, Text, View } from "react-native";

import { colour, space, text } from "../theme";
import type { Over } from "../wire";

/** What each reason means, in a sentence rather than a rule number. */
const BECAUSE: Readonly<Record<string, string>> = {
  life: "ran out of life",
  empty_library: "ran out of cards to draw",
};

export function Finished({ over, seat }: { readonly over: Over; readonly seat: string }) {
  return (
    <View style={styles.box}>
      <Text style={styles.headline}>{headline(over, seat)}</Text>
      {over.lost.map((one) => (
        <Text key={one.player} style={styles.why}>
          {`${one.player === seat ? "You" : "They"} ${BECAUSE[one.why] ?? one.why}.`}
        </Text>
      ))}
      <Text style={styles.done}>
        Nothing more can happen in this game. Start a new one when you are ready.
      </Text>
    </View>
  );
}

/** Who won, from the point of view of the device reading it. */
function headline(over: Over, seat: string): string {
  if (over.drawn) {
    // CR 104.4b. Rare, and a real result rather than a missing one.
    return "A draw — you both lost at the same moment.";
  }
  if (over.winner === null) {
    // The server said not drawn and named nobody, which it should not. Saying
    // so beats printing "undefined won".
    return "The game is over.";
  }
  return over.winner === seat ? "You won." : "They won.";
}

const styles = StyleSheet.create({
  box: {
    backgroundColor: colour.panel,
    borderColor: colour.accent,
    borderRadius: 10,
    borderWidth: 2,
    marginBottom: space.medium,
    padding: space.medium,
  },
  headline: { color: colour.text, fontSize: text.title, fontWeight: "700" },
  why: { color: colour.text, fontSize: text.body, paddingTop: space.small },
  done: { color: colour.quiet, fontSize: text.small, paddingTop: space.small },
});
