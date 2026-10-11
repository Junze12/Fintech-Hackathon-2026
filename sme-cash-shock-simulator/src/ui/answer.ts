import type { PathResult, Result, Scenario, StrategyResult } from "../model/types";
import { fmtMoney } from "./format";

// Pure helpers for the answer page: the headline sentences (Addendum A6.1), the gap-bridge bars
// (A6.2) and the failure cut-off for single-run lines (A1.4). The UI reads from these, never
// recomputing engine metrics.

export function pathOf(result: Result, pathId: string): PathResult {
  return result.paths.find((p) => p.id === pathId)!;
}

export function strategyOf(result: Result, id: string): StrategyResult {
  return result.strategies.find((s) => s.id === id)!;
}

export function recommended(result: Result): StrategyResult {
  return result.strategies.find((s) => s.isRecommended)!;
}

export function chosenShock(scenario: Scenario) {
  return scenario.shocks.find((k) => k.id === scenario.threshold.shockIdToScale)!;
}

// ---------------------------------------------------------------------------
// Headline
// ---------------------------------------------------------------------------

export type Segment = { text: string; tone?: "good" | "bad" };
export interface Headline {
  /** 1-4 as in the addendum; "2b" is case 2 when doing nothing does not miss the shock itself */
  id: "1" | "2" | "2b" | "3" | "4";
  line1: Segment[];
  line2: Segment[];
}

const whole = (p: number) => `${Math.round(p * 100)}%`;

/** The most frequent failure day in a failDayHistogram; ties go to the earliest day. */
export function modalFailDay(hist: Record<string, number>): number | null {
  let best: number | null = null;
  let bestCount = -1;
  for (const [day, count] of Object.entries(hist)) {
    const d = Number(day);
    if (count > bestCount || (count === bestCount && best !== null && d < best)) {
      best = d;
      bestCount = count;
    }
  }
  return best;
}

export function headline(result: Result, scenario: Scenario): Headline {
  const shock = chosenShock(scenario);
  const D = shock.dueDay;
  const target = scenario.objective.survivalTarget;
  const R = recommended(result);
  const S0 = strategyOf(result, "S0");
  const gap0 = result.defaultGap.gapAtShock;

  if (S0.survivalProb >= target) {
    return {
      id: "1",
      line1: [
        { text: "You can cover the " },
        { text: fmtMoney(shock.amount), tone: "good" },
        { text: ` on day ${D} without doing anything.` },
      ],
      line2: [{ text: `${whole(S0.survivalProb)} of simulated runs make it.` }],
    };
  }
  if (R.survivalProb >= target) {
    const money = R.cost < 0 ? `Gains ${fmtMoney(-R.cost)}` : `Costs ${fmtMoney(R.cost)}`;
    return {
      id: gap0 > 0 ? "2" : "2b",
      line1:
        gap0 > 0
          ? [
              { text: "Without action you'll be " },
              { text: fmtMoney(gap0), tone: "bad" },
              { text: ` short on day ${D}.` },
            ]
          : [{ text: `Without action the business runs short after day ${D}.` }],
      line2: [
        { text: `Best move: ${R.name}. ${money}, and ${whole(R.survivalProb)} of runs survive.` },
      ],
    };
  }
  if (R.gapAtShock > 0) {
    const extra = result.threshold.extraBufferForChosenShock;
    const amount =
      extra === null
        ? `more than ${fmtMoney(scenario.threshold.maxExtraBuffer)}`
        : `about ${fmtMoney(extra)}`;
    return {
      id: "3",
      line1: [
        { text: "Even the best plan leaves you " },
        { text: fmtMoney(R.gapAtShock), tone: "bad" },
        { text: ` short on day ${D}.` },
      ],
      line2: [{ text: `You need ${amount} more cash or credit before day ${D}.` }],
    };
  }
  const modal = modalFailDay(pathOf(result, R.pathId).metrics.failDayHistogram);
  return {
    id: "4",
    line1: [{ text: `You can cover day ${D}, but the business still runs short later.` }],
    line2: [{ text: `Most failures happen on day ${modal ?? "unknown"}.` }],
  };
}

export const segmentsText = (segs: Segment[]) => segs.map((s) => s.text).join("");

// ---------------------------------------------------------------------------
// Gap bridge: "Cash you can reach on day D"
// ---------------------------------------------------------------------------

export type BarKind = "total" | "down" | "up" | "margin";
export interface Bar {
  key: string;
  label: string;
  kind: BarKind;
  /** signed step (or the level for a total bar) */
  value: number;
  /** running level before and after this bar */
  from: number;
  to: number;
  hidden: boolean;
}

export interface Bridge {
  bars: Bar[];
  /** sum of bars 1-6 (the level reached before the final total) */
  reached: number;
  /** bar 7 */
  worst: number;
  /** true when bars 1-6 add up to bar 7 within S$1 */
  adds: boolean;
}

export function gapBridge(result: Result, scenario: Scenario, strategyId: string): Bridge {
  const D = chosenShock(scenario).dueDay;
  const C = scenario.creditLines.reduce((a, l) => a + l.limit, 0);
  const sel = pathOf(result, strategyOf(result, strategyId).pathId).liquidity;
  const base = pathOf(result, strategyOf(result, "S0").pathId).liquidity;
  const isBase = strategyId === "S0";

  const bars: Bar[] = [];
  let level = 0;
  const step = (key: string, label: string, kind: BarKind, value: number, hidden = false) => {
    const from = kind === "total" ? 0 : level;
    const to = kind === "total" ? value : level + value;
    bars.push({ key, label, kind, value, from, to, hidden });
    if (!hidden) level = to;
  };
  step("cash", "Cash today", "total", scenario.business.cash0);
  step("bills", `Bills before day ${D}`, "down", -base.meanOutflows);
  step("customers", "Customers paying", "up", base.meanInflows);
  step("credit", "Credit line", "up", C);
  step("plan", "Your plan adds", sel.meanLiquidity - base.meanLiquidity >= 0 ? "up" : "down", sel.meanLiquidity - base.meanLiquidity, isBase);
  step("margin", "Bad-luck margin", "margin", -(sel.meanLiquidity - sel.safeLiquidity));
  const reached = level;
  bars.push({ key: "worst", label: "Worst likely position", kind: "total", value: sel.safeLiquidity, from: 0, to: sel.safeLiquidity, hidden: false });
  return { bars, reached, worst: sel.safeLiquidity, adds: Math.abs(reached - sel.safeLiquidity) < 1 };
}

// ---------------------------------------------------------------------------
// Single-run lines stop at the failure day (A1.4)
// ---------------------------------------------------------------------------

/** First failed day of a median run, or null if it never failed. */
export function failDayOf(run: PathResult["medianRun"]): number | null {
  const s = run.find((x) => x.failed);
  return s ? s.day : null;
}

/** Last day drawn for a single-run line: its failure day, or the last day. */
export function lastDayOf(run: PathResult["medianRun"]): number {
  return failDayOf(run) ?? run[run.length - 1].day;
}
