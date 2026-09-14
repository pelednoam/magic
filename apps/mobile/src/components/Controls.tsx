/** The row of buttons at the bottom: step, draw, undo.

 Undo is here rather than beside the thing it undoes because it undoes the last
 *event*, whatever that was -- putting it next to any one action would suggest
 it only takes that one back. */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { colour, space, text } from "../theme";

export function Controls({
  onStep,
  onDraw,
  onUndo,
}: {
  readonly onStep: () => void;
  readonly onDraw: () => void;
  readonly onUndo: () => void;
}) {
  return (
    <View style={styles.controls}>
      <Action label="Next step" onPress={onStep} />
      <Action label="Draw" onPress={onDraw} />
      <Action label="Undo" onPress={onUndo} />
    </View>
  );
}

function Action({
  label,
  onPress,
}: {
  readonly label: string;
  readonly onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.action}>
      <Text style={styles.actionLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  controls: { flexDirection: "row", gap: space.small },
  action: {
    backgroundColor: colour.accent,
    borderRadius: 8,
    flex: 1,
    paddingVertical: space.medium,
  },
  actionLabel: {
    color: "#0d1016",
    fontSize: text.body,
    fontWeight: "700",
    textAlign: "center",
  },
});
