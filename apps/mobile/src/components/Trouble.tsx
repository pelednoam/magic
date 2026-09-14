/**
 * What to show when the server said no, and how to get past it.
 *
 * Recoverable, not terminal. The commonest reason is the laptop not being up
 * yet, and a dead-end screen means quitting the app to retry.
 *
 * The token case is the other one. A build on the same laptop picks the token
 * up from the environment; a phone cannot, so it has to be typed once — and
 * the field only appears when the server has actually refused for want of it,
 * which keeps it out of the way the rest of the time.
 */

import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colour, space, text } from "../theme";

export function Trouble({
  problem,
  needsToken,
  typed,
  onTyped,
  onRetry,
}: {
  /** The server's own sentence. */
  readonly problem: string;
  readonly needsToken: boolean;
  readonly typed: string;
  readonly onTyped: (token: string) => void;
  readonly onRetry: () => void;
}) {
  return (
    <View style={styles.page}>
      <Text style={styles.problem}>
        {needsToken
          ? "This server needs its token. It is printed where the server was started."
          : problem}
      </Text>
      {needsToken ? (
        <TextInput
          accessibilityLabel="Server token"
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={onTyped}
          placeholder="paste the token"
          placeholderTextColor={colour.quiet}
          style={styles.code}
          value={typed}
        />
      ) : null}
      <Pressable
        accessibilityRole="button"
        disabled={needsToken && typed.trim() === ""}
        onPress={onRetry}
      >
        <Text style={styles.back}>{needsToken ? "use this token" : "try again"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.large },
  problem: { color: colour.no, fontSize: text.body, paddingBottom: space.medium },
  back: { color: colour.accent, fontSize: text.small, marginTop: space.medium },
  code: {
    backgroundColor: colour.panel,
    borderColor: colour.panelEdge,
    borderRadius: 8,
    borderWidth: 1,
    color: colour.text,
    marginBottom: space.small,
    padding: space.medium,
  },
});
