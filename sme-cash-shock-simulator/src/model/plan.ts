import { ALL_CUSTOMERS, ALL_OPEN_RECEIVABLES, type Scenario } from "./types";

/** "Letter of demand (Firm B)": the option label plus a readable target, if the target is one thing. */
function optionText(s: Scenario, actionId: string, targetId: string): string {
  const action = s.actions.find((a) => a.id === actionId)!;
  if (targetId === ALL_OPEN_RECEIVABLES || targetId === ALL_CUSTOMERS) return action.label;
  const target =
    s.customers.find((c) => c.id === targetId)?.name ?? s.payables.find((p) => p.id === targetId)?.label;
  return target ? `${action.label} (${target})` : action.label;
}

/** Plan sentence from a path's choices, in day order. No free text, no LLM. */
export function planSentence(s: Scenario, choices: Record<string, string[]>): string {
  const dps = [...s.decisionPoints].sort((a, b) => a.day - b.day || a.order - b.order);
  return dps
    .map((dp) => {
      const ids = choices[dp.id] ?? [];
      if (ids.length === 0) return `Day ${dp.day}: No action.`;
      const text = ids
        .map((id) => {
          const o = dp.options.find((x) => x.actionId === id)!;
          return optionText(s, id, o.targetId);
        })
        .join(" + ");
      return `Day ${dp.day}: ${text}.`;
    })
    .join(" ");
}
