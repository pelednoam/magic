/**
 * What attacking would do, ranked, with the maths shown.
 *
 * `unavailable` is a first-class state, not an empty list: the engine says
 * "it is not your combat" or "this board is too large to work out exactly", and
 * showing nothing instead would read as "do not attack" -- which is advice, and
 * not the advice it gave.
 */

import { StyleSheet, Text, View } from "react-native";

import { planLine, planTitle } from "../format";
import { colour, space, text } from "../theme";
import type { Attacks as AttackOptions } from "../wire";

import { Panel } from "./Panel";

export function Attacks({ attacks }: { readonly attacks: AttackOptions }) {
  if (attacks.unavailable !== "") {
    return (
      <Panel title="Attacking">
        <Text style={styles.unavailable}>{attacks.unavailable}</Text>
      </Panel>
    );
  }
  const best = attacks.plans.slice(0, 4);
  return (
    <Panel title="Attacking" note={`${attacks.plans.length} options`}>
      {best.map((plan, index) => (
        <View
          // Keyed by identity, not name: two Grizzly Bears is the ordinary
          // case, and names collide the moment a deck runs a playset.
          key={plan.attacker_ids.join("+") || "hold-back"}
          style={[styles.plan, index === 0 ? styles.top : null]}
        >
          <Text style={styles.attackers}>{planTitle(plan)}</Text>
          <Text style={plan.lethal ? styles.lethal : styles.detail}>{planLine(plan)}</Text>
        </View>
      ))}
    </Panel>
  );
}

const styles = StyleSheet.create({
  plan: {
    borderRadius: 6,
    marginBottom: space.small,
    paddingHorizontal: space.small,
    paddingVertical: space.small,
  },
  top: { backgroundColor: "#1d2434" },
  attackers: { color: colour.text, fontSize: text.body, fontWeight: "600" },
  detail: { color: colour.quiet, fontSize: text.small, marginTop: space.tight },
  lethal: { color: colour.warn, fontSize: text.small, fontWeight: "700", marginTop: space.tight },
  unavailable: { color: colour.quiet, fontSize: text.body },
});
