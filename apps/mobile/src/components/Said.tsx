/**
 * What the coach said at one moment of a game that has already been played.
 *
 * A component of its own because a replayed answer is not a live one: it has
 * already been checked, already been acted on or refused, and the screen's job
 * is to report that rather than offer it. `Coaching` is the live version, and
 * this says the same things about the same answer in the same order.
 *
 * **The badge belongs to the choice, not to the words.** `advice.verify` checks
 * the card named in `play` and the attack named in `attack` against what the
 * engine offered; it checks nothing at all about `in_short` or `because`, which
 * are prose a model wrote. An earlier version of this panel put "checked" over
 * the prose and did not show the choice — so the one thing that had been
 * verified was missing and the badge was making a claim about the one thing
 * that had not. `Coaching` has always drawn that line in its own words; this
 * draws it in the same ones.
 */

import { StyleSheet, Text, View } from "react-native";

import { nameOf } from "../format";
import { colour, space, text } from "../theme";
import type { Explanation, Moment, Player } from "../wire";

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
  const board = moment.state.players[moment.player];
  return (
    <Panel
      title="The coach said"
      note={moment.trusted ? "the choice was checked" : "refused, not played"}
    >
      {moment.trusted ? (
        <Chose said={moment.said} board={board} />
      ) : (
        <Text style={styles.refused}>
          The coach disagreed with the rules engine, so this was never played.
        </Text>
      )}
      <Text style={styles.short}>{moment.said.in_short}</Text>
      {moment.said.because === "" ? null : (
        <Text style={styles.because}>{moment.said.because}</Text>
      )}
      {moment.trusted ? (
        <Text style={styles.caveat}>
          The choice above was checked against the rules engine. The wording is
          Claude&apos;s, and nothing checked that.
        </Text>
      ) : null}
      <Bullets items={moment.said.watch_out} style={styles.watch} />
      <Bullets items={moment.said.check_yourself} style={styles.check} />
      {moment.trusted ? null : <Objections problems={moment.problems} />}
    </Panel>
  );
}

/**
 * The choice the engine checked, named from the board it was made on.
 *
 * Named rather than printed: `play` and `attack` are instance ids, and "Play
 * you-7" teaches nobody anything. A card the board no longer holds keeps its
 * id, which `nameOf` already does — better an unfamiliar word than a blank.
 */
function Chose({
  said,
  board,
}: {
  readonly said: Explanation;
  readonly board: Player | undefined;
}) {
  if (board === undefined) {
    return null;
  }
  // "Attack with nobody" is a recommendation and a common one; it arrives as an
  // empty list, so it has to be said in words or it reads as no advice at all.
  const holdBack = said.play === "" && said.attack.length === 0;
  return (
    <View style={styles.choice}>
      {said.play === "" ? null : (
        <Text style={styles.chosen}>{`Play ${nameOf(board, said.play)}`}</Text>
      )}
      {said.attack.length === 0 ? null : (
        <Text style={styles.chosen}>
          {`Attack with ${said.attack.map((one) => nameOf(board, one)).join(", ")}`}
        </Text>
      )}
      {holdBack ? <Text style={styles.chosen}>Do nothing this turn</Text> : null}
    </View>
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
      <Text style={styles.head}>What the engine said was wrong with it:</Text>
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
  choice: { paddingBottom: space.small },
  chosen: { color: colour.yes, fontSize: text.body, fontWeight: "600" },
  short: { color: colour.text, fontSize: text.body },
  because: { color: colour.quiet, fontSize: text.small, paddingTop: space.small },
  caveat: { color: colour.quiet, fontSize: text.small, paddingTop: space.small },
  quiet: { color: colour.quiet, fontSize: text.small },
  refused: { color: colour.no, fontSize: text.small, paddingBottom: space.small },
  bullet: { fontSize: text.small, paddingTop: space.tight },
  watch: { color: colour.warn },
  check: { color: colour.accent },
  objections: { paddingTop: space.small },
  head: { color: colour.no, fontSize: text.small, fontWeight: "600" },
  objection: { color: colour.no },
});
