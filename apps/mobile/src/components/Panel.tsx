/** A titled box. The only layout idea in the app, used for every section. */

import type { ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";

import { colour, space, text } from "../theme";

export function Panel({
  title,
  note,
  children,
}: {
  readonly title: string;
  readonly note?: string;
  readonly children: ReactNode;
}) {
  return (
    <View style={styles.panel}>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        {note === undefined ? null : <Text style={styles.note}>{note}</Text>}
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    backgroundColor: colour.panel,
    borderColor: colour.panelEdge,
    borderRadius: 10,
    borderWidth: 1,
    marginBottom: space.medium,
    padding: space.medium,
  },
  header: {
    alignItems: "baseline",
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: space.small,
  },
  title: { color: colour.text, fontSize: text.heading, fontWeight: "600" },
  note: { color: colour.quiet, fontSize: text.small },
});
