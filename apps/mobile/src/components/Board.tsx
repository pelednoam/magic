/** One player's battlefield, and the two states that stop a permanent acting. */

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
});
