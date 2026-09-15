/**
 * One player's battlefield, and the two states that stop a permanent acting.
 *
 * Plus anything waiting on the stack. The stack is a public zone (CR 400.2) and
 * it is where a spell *is* between being cast and resolving -- the moment when
 * the other player may answer it. A tracker that did not show it would be
 * hiding the one thing that moment is about.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { permanentNote } from "../format";
import { colour, space, text } from "../theme";
import type { Permanent, Player } from "../wire";

import { Panel } from "./Panel";

export function Board({
  title,
  player,
  onTap,
}: {
  readonly title: string;
  readonly player: Player;
  readonly onTap?: (permanent: Permanent) => void;
}) {
  return (
    <Panel title={title} note={`${player.life} life · ${player.library} in library`}>
      {player.stack.length === 0 ? null : (
        <Text style={styles.waiting}>
          {`Waiting to resolve: ${player.stack.map((card) => card.name).join(", ")}`}
        </Text>
      )}
      {player.battlefield.length === 0 ? (
        <Text style={styles.empty}>Nothing on the battlefield.</Text>
      ) : (
        <View style={styles.grid}>
          {player.battlefield.map((permanent) => (
            <Pressable
              key={permanent.instance_id}
              accessibilityRole="button"
              accessibilityLabel={`${permanent.name}${permanent.tapped ? ", tapped" : ""}`}
              disabled={onTap === undefined}
              onPress={() => onTap?.(permanent)}
              style={[styles.permanent, permanent.tapped ? styles.tapped : null]}
            >
              <Text style={styles.name}>{permanent.name}</Text>
              {permanentNote(permanent) === "" ? null : (
                <Text style={styles.note}>{permanentNote(permanent)}</Text>
              )}
            </Pressable>
          ))}
        </View>
      )}
    </Panel>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.small },
  permanent: {
    backgroundColor: "#222839",
    borderRadius: 6,
    paddingHorizontal: space.small,
    paddingVertical: space.tight,
  },
  tapped: { backgroundColor: "#2c2430", opacity: 0.65 },
  name: { color: colour.text, fontSize: text.small, fontWeight: "600" },
  note: { color: colour.quiet, fontSize: text.small },
  empty: { color: colour.quiet, fontSize: text.body },
  waiting: { color: colour.warn, fontSize: text.small, paddingBottom: space.small },
});
