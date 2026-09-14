/**
 * What Claude said, and whether the engine agreed with it.
 *
 * The child's sentence comes first and biggest, because that is who this app is
 * for. The reasoning is underneath for whoever is teaching. Neither is ever
 * shown as the *rules* -- the panels above are the rules, and they were there
 * before this one appeared.
 *
 * When `trusted` is false the server has already replaced the answer with its
 * refusal text. This panel says so in its own colour and its own words, so that
 * a refusal cannot be mistaken for advice at a glance.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { planFor } from "../format";
import { colour, space, text } from "../theme";
import type { Coaching as Reply, Playable, Plan } from "../wire";

import { Panel } from "./Panel";

export function Coaching({
  reply,
  asking,
  problem,
  hand,
  plans,
  onAsk,
}: {
  /** Null until the button has been pressed. */
  readonly reply: Reply | null;
  readonly asking: boolean;
  /** The server's own sentence when there was no answer at all. */
  readonly problem: string;
  /** The engine's hand, for turning a recommended id back into a card. */
  readonly hand: readonly Playable[];
  /** The engine's plans, for the same reason. */
  readonly plans: readonly Plan[];
  readonly onAsk: () => void;
}) {
  return (
    <Panel title="Coach me" note={asking ? "thinking…" : undefined}>
      <Pressable
        accessibilityRole="button"
        disabled={asking}
        onPress={onAsk}
        style={[styles.ask, asking ? styles.asking : null]}
      >
        {asking ? (
          <ActivityIndicator color={colour.text} />
        ) : (
          <Text style={styles.askLabel}>
            {reply === null ? "Ask what to do" : "Ask again"}
          </Text>
        )}
      </Pressable>
      {problem === "" ? null : <Text style={styles.problem}>{problem}</Text>}
      {reply === null ? (
        <Text style={styles.idle}>
          The lists above are always right and always free. This asks Claude which of
          them is best, which takes a moment.
        </Text>
      ) : (
        <Answer reply={reply} hand={hand} plans={plans} />
      )}
    </Panel>
  );
}

function Answer({
  reply,
  hand,
  plans,
}: {
  readonly reply: Reply;
  readonly hand: readonly Playable[];
  readonly plans: readonly Plan[];
}) {
  return (
    <View>
      {reply.trusted ? null : (
        <Text style={styles.refused}>
          The coach disagreed with the rules engine, so its answer is not shown. Use
          the lists above — those are checked.
        </Text>
      )}
      {/* The checked choice first, then the words about it. These are named
          from the engine's own lists; everything below them is prose a model
          wrote, and nothing checked it. */}
      {reply.trusted ? <Recommendation reply={reply} hand={hand} plans={plans} /> : null}
      {reply.explanation.in_short === "" ? null : (
        <Text style={styles.short}>{reply.explanation.in_short}</Text>
      )}
      {reply.explanation.because === "" ? null : (
        <Text style={styles.because}>{reply.explanation.because}</Text>
      )}
      <Bullets style={styles.watch} items={reply.explanation.watch_out} />
      <Bullets style={styles.check} items={reply.explanation.check_yourself} />
    </View>
  );
}

/** The choice itself, named from the engine's own lists rather than the model's. */
function Recommendation({
  reply,
  hand,
  plans,
}: {
  readonly reply: Reply;
  readonly hand: readonly Playable[];
  readonly plans: readonly Plan[];
}) {
  const play = hand.find((card) => card.instance_id === reply.explanation.play);
  const attack = planFor(plans, reply.explanation.attack);
  // "Attack with nobody" is a recommendation, and a common one. It arrives as
  // an empty `attack`, which matches no plan — so keying the line on a matched
  // plan meant the advice to hold back was silently never shown. Shown only
  // when there was an attack to consider: with no plans, "do not attack" is
  // not advice, it is the rules.
  const holdBack = reply.explanation.attack.length === 0 && plans.length > 0;
  if (play === undefined && attack === undefined && !holdBack) {
    return null;
  }
  return (
    <View style={styles.choice}>
      {play === undefined ? null : <Text style={styles.chosen}>Play {play.name}</Text>}
      {attack === undefined ? null : (
        <Text style={styles.chosen}>Attack with {attack.attackers.join(", ")}</Text>
      )}
      {holdBack ? <Text style={styles.chosen}>Do not attack this turn</Text> : null}
    </View>
  );
}

function Bullets({
  items,
  style,
}: {
  readonly items: readonly string[];
  readonly style: { readonly color: string };
}) {
  return (
    <>
      {/* Keyed by position. The text comes from a model and repeats often
          enough to matter -- two identical "check the Pacifism" lines silently
          collapsed into one. */}
      {items.map((item, at) => (
        <Text key={`${at}-${item}`} style={[styles.bullet, style]}>
          • {item}
        </Text>
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  ask: {
    backgroundColor: colour.accent,
    borderRadius: 8,
    minHeight: 44,
    justifyContent: "center",
    paddingVertical: space.small,
  },
  asking: { backgroundColor: colour.panelEdge },
  askLabel: {
    color: "#0d1016",
    fontSize: text.body,
    fontWeight: "700",
    textAlign: "center",
  },
  idle: { color: colour.quiet, fontSize: text.small, marginTop: space.small },
  problem: { color: colour.no, fontSize: text.body, marginTop: space.small },
  refused: { color: colour.warn, fontSize: text.body, marginTop: space.small },
  short: {
    color: colour.text,
    fontSize: text.heading,
    fontWeight: "600",
    marginTop: space.medium,
  },
  choice: { marginTop: space.small },
  chosen: { color: colour.yes, fontSize: text.body, fontWeight: "600" },
  because: { color: colour.quiet, fontSize: text.body, marginTop: space.small },
  bullet: { fontSize: text.small, marginTop: space.tight },
  watch: { color: colour.warn },
  check: { color: colour.quiet },
});
