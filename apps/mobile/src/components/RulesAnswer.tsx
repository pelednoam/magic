/**
 * What came back, with the rules it was drawn from underneath it.
 *
 * The retrieved passages are shown whether or not the model cited them, and
 * whether or not the answer survived its check. They are the part that is
 * certainly true: a parent who can read 702.19b does not have to trust anybody
 * about trample, and when the check fails they are all that is left — which is
 * still a useful answer to a rules question.
 */

import { StyleSheet, Text, View } from "react-native";

import { colour, space, text } from "../theme";
import type { Asked, RuleText } from "../wire";

export function Answer({ reply }: { readonly reply: Asked }) {
  const cited = new Set(reply.answer.citations);
  return (
    <View>
      {reply.cited || !reply.matched ? null : (
        <Text style={styles.refused}>
          The answer did not stay inside the rules the server found — it used one
          that was not there, or gave none at all — so it is not shown. The rules
          below are the real ones; read those.
        </Text>
      )}
      {reply.answer.in_short === "" ? null : (
        <Text style={styles.short}>{reply.answer.in_short}</Text>
      )}
      {reply.answer.answer === "" ? null : (
        <Text style={styles.full}>{reply.answer.answer}</Text>
      )}
      {reply.answer.unsure === "" ? null : (
        <Text style={styles.unsure}>
          {reply.cited || !reply.matched
            ? "Not settled by these rules: "
            : "Why it was not shown: "}
          {reply.answer.unsure}
        </Text>
      )}
      {reply.rules.length === 0 ? null : (
        <View style={styles.rules}>
          <Text style={styles.rulesTitle}>
            From the rules — these are the source; the wording above is Claude&apos;s
          </Text>
          {reply.rules.map((rule, at) => (
            <Rule
              key={`${at}-${rule.reference}`}
              rule={rule}
              cited={cited.has(rule.reference)}
            />
          ))}
        </View>
      )}
    </View>
  );
}

/** One retrieved rule. The cited ones are marked, not filtered: a player
 *  reading around the answer is the behaviour this is trying to encourage. */
function Rule({ rule, cited }: { readonly rule: RuleText; readonly cited: boolean }) {
  return (
    <View style={styles.rule}>
      <Text style={[styles.reference, cited ? styles.used : null]}>
        {rule.reference}
        {rule.title === "" || rule.title === rule.reference ? "" : ` · ${rule.title}`}
      </Text>
      <Text style={styles.ruleText}>{rule.text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  refused: { color: colour.warn, fontSize: text.body, marginTop: space.small },
  short: {
    color: colour.text,
    fontSize: text.heading,
    fontWeight: "600",
    marginTop: space.medium,
  },
  full: { color: colour.text, fontSize: text.body, marginTop: space.small },
  unsure: { color: colour.warn, fontSize: text.small, marginTop: space.small },
  none: { color: colour.quiet, fontSize: text.small, marginTop: space.small },
  rules: { marginTop: space.medium },
  rulesTitle: {
    color: colour.quiet,
    fontSize: text.small,
    fontWeight: "700",
    marginBottom: space.tight,
  },
  rule: { marginBottom: space.small },
  reference: { color: colour.quiet, fontSize: text.small, fontWeight: "700" },
  used: { color: colour.yes },
  ruleText: { color: colour.text, fontSize: text.small },
});
