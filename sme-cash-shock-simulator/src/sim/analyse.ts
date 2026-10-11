import { planSentence } from "../model/plan";
import {
  resolveStrategyChoices,
  type Result,
  type Scenario,
  type StrategyResult,
} from "../model/types";
import { buildTree, pathIdOf, profitBridge, r2, r4, runMain, type PathSummary } from "./optimise";
import { runThreshold, searchBuffer } from "./threshold";

export type Stage = "main" | "shock_search" | "buffer_search" | "curve" | "done";
export type ProgressFn = (stage: Stage, pct: number) => void;

export interface AnalyseOptions {
  deterministic: boolean;
  scenarioName: string;
}

/** Direct cost of a path's actions (Addendum A4): excludes revenue, gross profit and supplier discounts. */
function directCost(x: PathSummary): number {
  const r = x.raw;
  return (
    r.financingFees + r.collectionCosts + r.discountsGiven + r.interestExpense + r.churnCost - r.lateFeeIncome
  );
}

/** The whole engine: main run, threshold searches and curve, assembled into the Result contract. */
export function analyse(s: Scenario, opts: AnalyseOptions, onProgress?: ProgressFn): Result {
  const t0 = performance.now();
  const det = opts.deterministic;

  const main = runMain(s, det, (pct) => onProgress?.("main", pct));
  onProgress?.("main", 100);

  const th = runThreshold(
    s,
    main.summaries.map((x) => x.path),
    main.best.path,
    det,
    (stage, pct) => onProgress?.(stage, pct),
  );

  const { best, def } = main;
  const s0 = s.strategies.find((x) => x.id === "S0")!;
  const byPath = new Map(main.summaries.map((x) => [x.id, x]));
  const resolved = s.strategies.map((st) => ({
    st,
    summary: byPath.get(pathIdOf(main.prep, resolveStrategyChoices(s, st)))!,
  }));
  const s0Cost = directCost(byPath.get(pathIdOf(main.prep, resolveStrategyChoices(s, s0)))!);
  const entries = resolved.map(({ st, summary }) => ({
    id: st.id,
    name: st.name,
    description: st.description,
    summary,
  }));
  if (!entries.some((e) => e.summary.id === best.id)) {
    entries.push({
      id: "BEST",
      name: "Best combination",
      description: planSentence(s, best.path.choices),
      summary: best,
    });
  }
  const recommendedIndex = entries.findIndex((e) => e.summary.id === best.id);
  const strategies: StrategyResult[] = entries.map((e, i) => ({
    id: e.id,
    name: e.name,
    description: e.description,
    pathId: e.summary.id,
    survivalProb: r4(e.summary.survivalProb),
    cost: r2(directCost(e.summary) - s0Cost),
    gapAtShock: e.summary.result.liquidity.gapAtShock,
    churnRisk: s.customers
      .map((c, ci) => ({ customerId: c.id, customerName: c.name, prob: r4(e.summary.churnProbs[ci]) }))
      .filter((x) => x.prob >= 0.01)
      .sort((a, b) => b.prob - a.prob),
    isRecommended: i === recommendedIndex,
  }));
  const defaultGap = {
    gapAtShock: def.result.liquidity.gapAtShock,
    extraBufferForChosenShock: searchBuffer(
      s,
      [def.path],
      det ? 1 : s.threshold.runsPerPath,
      det,
    ),
  };
  const result: Result = {
    scenarioName: opts.scenarioName,
    bestPathId: best.id,
    defaultPathId: def.id,
    bestMeetsTarget: best.survivalProb >= s.objective.survivalTarget,
    paths: main.summaries.map((x) => x.result),
    frontierPathIds: main.frontier.map((x) => x.id),
    strategies,
    defaultGap,
    profitSacrificed: r2(def.econ - best.econ),
    profitBridge: profitBridge(best.raw, def.raw),
    tree: buildTree(main),
    threshold: th,
    runInfo: {
      runsPerPath: det ? 1 : s.meta.runsPerPath,
      thresholdRunsPerPath: det ? 1 : s.threshold.runsPerPath,
      seed: s.meta.seed,
      pathCount: main.summaries.length,
      elapsedMs: Math.round(performance.now() - t0),
      deterministic: det,
    },
  };
  onProgress?.("done", 100);
  return result;
}
