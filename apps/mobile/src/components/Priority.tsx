/**
 * The stack, whose moment it is, and the two buttons that move it on.
 *
 * The panel the app did not have. Tapping a card cast it and resolved it in
 * one gesture, so the moment between those — the moment a player decides
 * whether to answer — did not exist on screen, in the app whose whole purpose
 * is to teach a nine-year-old that it is there. A spell resolves because every
 * player has passed in succession (CR 117.4, CR 608.1); this is where the
 * passing happens.
 *
 * It decides nothing, and every judgement in it is made in `moment.ts`, where
 * it can be tested. The buttons send events; the server refuses them in its
 * own words if it disagrees.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { resolving, waiting, whoseMove } from "../moment";
import { colour, space, text } from "../theme";
import type { GameState } from "../wire";

import { Panel } from "./Panel";

/** What resolving one spell takes: which card, and which zone it goes to. */
export type Resolve = (instanceId: string, to: string) => void;

export function Priority({
  state,
  seat,
  gaps,
  onPass,
  onResolve,
}: {
  readonly state: GameState;
  readonly seat: string;
  /** What the rules engine does not model here — `advice.not_modelled`. */
  readonly gaps: readonly string[];
  readonly onPass?: (() => void) | undefined;
  readonly onResolve?: Resolve | undefined;
}) {
  const stack = waiting(state);
  const next = resolving(state, seat);
  return (
    <Panel title="The stack" note={whoseMove(state, seat)}>
      {stack.length === 0 ? (
        <Text style={styles.empty}>Nothing is waiting to resolve.</Text>
      ) : (
        stack.map((spell, index) => (
          <Text key={spell.instance_id} style={styles.spell}>
            {`${index === 0 ? "Next: " : ""}${spell.name} (${spell.controller})`}
          </Text>
        ))
      )}
      <View style={styles.row}>
        {onPass === undefined || state.priority !== seat ? null : (
          <Button label="Pass" onPress={onPass} />
        )}
        {next === undefined || onResolve === undefined || !next.yours || next.to === "" ? null : (
          <Button
            label={`Resolve ${next.card.name}`}
            onPress={() => {
              onResolve(next.card.instance_id, next.to);
            }}
          />
        )}
      </View>
      {next === undefined || next.yours || next.to === "" ? null : (
        <Text style={styles.gap}>{`${next.card.name} is theirs to resolve.`}</Text>
      )}
      {next === undefined || next.to !== "" ? null : (
        <Text style={styles.gap}>{`The coach cannot say where ${next.card.name} resolves.`}</Text>
      )}
      {gaps.map((gap) => (
        <Text key={gap} style={styles.gap}>
          {gap}
        </Text>
      ))}
    </Panel>
  );
}

function Button({ label, onPress }: { readonly label: string; readonly onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.button}>
      <Text style={styles.buttonLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  empty: { color: colour.quiet, fontSize: text.body },
  spell: { color: colour.text, fontSize: text.body, marginBottom: space.tight },
  row: { flexDirection: "row", gap: space.small, marginTop: space.small },
  button: {
    backgroundColor: colour.accent,
    borderRadius: 8,
    flex: 1,
    paddingVertical: space.small,
  },
  buttonLabel: {
    color: "#0d1016",
    fontSize: text.body,
    fontWeight: "700",
    textAlign: "center",
  },
  gap: { color: colour.quiet, fontSize: text.small, marginTop: space.small },
});
