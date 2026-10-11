import type { Path, Scenario } from "../model/types";
import { compilePath, prepare, simulate } from "./engine";
import { evaluateQuick, pickBest, r4 } from "./optimise";

export interface ThresholdResult {
  largestSurvivableShock: number | null;
  atLeast: boolean;
  survivalAtThreshold: number | null;
  survivalAtNextStep: number | null;
  extraBufferForChosenShock: number | null;
  curve: { shock: number; survival: number }[];
}

function clone(s: Scenario): Scenario {
  return JSON.parse(JSON.stringify(s)) as Scenario;
}

export function withShockAmount(s: Scenario, shockId: string, amount: number): Scenario {
  const c = clone(s);
  const k = c.shocks.find((x) => x.id === shockId)!;
  k.amount = amount;
  return c;
}

export function withExtraCash(s: Scenario, delta: number): Scenario {
  const c = clone(s);
  c.business.cash0 += delta;
  return c;
}

/** Survival of the best-ranked path after re-running every path on the given scenario. */
export function bestSurvival(
  variant: Scenario,
  paths: Path[],
  runs: number,
  deterministic: boolean,
): number {
  const prep = prepare(variant);
  const ranked = evaluateQuick(
    prep,
    paths.map((p) => compilePath(prep, p)),
    runs,
    deterministic,
  );
  return pickBest(ranked, variant.objective.survivalTarget, variant.objective.profitTieToleranceSGD)
    .survivalProb;
}

/** Most failed runs a path can have and still reach survivalProb >= target. */
export function maxFailures(runs: number, target: number): number {
  let f = 0;
  while (f < runs && (runs - (f + 1)) / runs >= target) f++;
  return (runs - f) / runs >= target ? f : -1;
}

/**
 * True if at least one path reaches the survival target. This is the same test as
 * "the best path's survival >= target" (the best path is eligible whenever any path is),
 * but it stops a path as soon as it has too many failures and stops at the first passing path.
 * `paths` should be ordered most-promising first.
 */
export function anyPathMeetsTarget(
  variant: Scenario,
  paths: Path[],
  runs: number,
  deterministic: boolean,
): boolean {
  const prep = prepare(variant);
  const allowed = maxFailures(runs, variant.objective.survivalTarget);
  if (allowed < 0) return false;
  for (const p of paths) {
    const cp = compilePath(prep, p);
    let fails = 0;
    let ok = true;
    for (let r = 0; r < runs; r++) {
      const tr = simulate(prep, cp, r, { deterministic, record: false, collectEvents: false });
      if (tr.failed && ++fails > allowed) {
        ok = false;
        break;
      }
    }
    if (ok) return true;
  }
  return false;
}

export function survivalOfPath(
  variant: Scenario,
  path: Path,
  runs: number,
  deterministic: boolean,
): number {
  const prep = prepare(variant);
  return evaluateQuick(prep, [compilePath(prep, path)], runs, deterministic)[0].survivalProb;
}

/**
 * Smallest extra cash (on the grid of stepSGD) that lets some path in `paths` reach the survival
 * target for the chosen shock: 0 if none is needed, null if even maxExtraBuffer is not enough.
 */
export function searchBuffer(
  s: Scenario,
  paths: Path[],
  runs: number,
  deterministic: boolean,
  onEval?: () => void,
): number | null {
  const th = s.threshold;
  const step = th.stepSGD;
  const cache = new Map<number, boolean>();
  const passes = (delta: number): boolean => {
    let v = cache.get(delta);
    if (v === undefined) {
      v = anyPathMeetsTarget(withExtraCash(s, delta), paths, runs, deterministic);
      cache.set(delta, v);
      onEval?.();
    }
    return v;
  };
  if (passes(0)) return 0;
  if (!passes(th.maxExtraBuffer)) return null;
  let lo = 0; // fails
  let hi = th.maxExtraBuffer; // passes
  while (hi - lo > step + 1e-9) {
    let mid = lo + Math.round((hi - lo) / 2 / step) * step;
    if (mid <= lo) mid = lo + step;
    if (mid >= hi) mid = hi - step;
    if (passes(mid)) hi = mid;
    else lo = mid;
  }
  return hi;
}

type Progress = (stage: "shock_search" | "buffer_search" | "curve", pct: number) => void;

/**
 * Largest survivable shock, extra buffer for the chosen shock, and the survival curve
 * (spec: "Optimiser and threshold search").
 */
export function runThreshold(
  s: Scenario,
  paths: Path[],
  bestPath: Path,
  deterministic: boolean,
  onProgress?: Progress,
): ThresholdResult {
  const th = s.threshold;
  const runs = deterministic ? 1 : th.runsPerPath;
  const step = th.stepSGD;

  // ---- largest survivable shock ----
  const passCache = new Map<number, boolean>();
  const fullCache = new Map<number, number>();
  let evals = 0;
  const expectedShock = Math.ceil(Math.log2(Math.max(2, th.maxShock / step))) + 4;
  const tick = (stage: "shock_search" | "buffer_search", n: number, expected: number) =>
    onProgress?.(stage, Math.min(99, (n / expected) * 100));
  const passesShock = (amount: number): boolean => {
    let v = passCache.get(amount);
    if (v === undefined) {
      v = anyPathMeetsTarget(withShockAmount(s, th.shockIdToScale, amount), paths, runs, deterministic);
      passCache.set(amount, v);
      tick("shock_search", ++evals, expectedShock);
    }
    return v;
  };
  // Full ranking of every path at one amount, for the reported survival numbers.
  const survivalAtShock = (amount: number): number => {
    let v = fullCache.get(amount);
    if (v === undefined) {
      v = bestSurvival(withShockAmount(s, th.shockIdToScale, amount), paths, runs, deterministic);
      fullCache.set(amount, v);
      tick("shock_search", ++evals, expectedShock);
    }
    return v;
  };

  let largest: number | null;
  let atLeast = false;
  let survAt: number | null = null;
  let survNext: number | null = null;
  if (passesShock(th.maxShock)) {
    largest = th.maxShock;
    atLeast = true;
    survAt = survivalAtShock(th.maxShock);
  } else if (!passesShock(0)) {
    largest = null;
  } else {
    let lo = 0;
    let hi = th.maxShock;
    while (hi - lo > step + 1e-9) {
      let mid = lo + Math.round((hi - lo) / 2 / step) * step;
      if (mid <= lo) mid = lo + step;
      if (mid >= hi) mid = hi - step;
      if (passesShock(mid)) lo = mid;
      else hi = mid;
    }
    largest = lo;
    survAt = survivalAtShock(lo);
    survNext = survivalAtShock(Math.min(lo + step, th.maxShock));
  }
  onProgress?.("shock_search", 100);

  // ---- extra buffer for the chosen shock ----
  const expectedBuf = Math.ceil(Math.log2(Math.max(2, th.maxExtraBuffer / step))) + 3;
  let bevals = 0;
  const buffer = searchBuffer(s, paths, runs, deterministic, () =>
    tick("buffer_search", ++bevals, expectedBuf),
  );
  onProgress?.("buffer_search", 100);

  // ---- survival curve on the fixed best path ----
  const curveRuns = deterministic ? 1 : s.meta.runsPerPath;
  const amounts: number[] = [];
  for (let a = 0; a < th.maxShock; a += th.curveStepSGD) amounts.push(a);
  amounts.push(th.maxShock);
  const curve = amounts.map((a, i) => {
    const surv = survivalOfPath(
      withShockAmount(s, th.shockIdToScale, a),
      bestPath,
      curveRuns,
      deterministic,
    );
    onProgress?.("curve", ((i + 1) / amounts.length) * 100);
    return { shock: a, survival: r4(surv) };
  });

  return {
    largestSurvivableShock: largest,
    atLeast,
    survivalAtThreshold: survAt === null ? null : r4(survAt),
    survivalAtNextStep: survNext === null ? null : r4(survNext),
    extraBufferForChosenShock: buffer,
    curve,
  };
}
