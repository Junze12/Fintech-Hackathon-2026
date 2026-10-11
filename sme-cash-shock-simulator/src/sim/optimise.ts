import {
  MAX_PATHS,
  ScenarioError,
  type CustomerStats,
  type DailyPct,
  type DaySnapshot,
  type Liquidity,
  type Metrics,
  type Path,
  type PathResult,
  type Pct,
  type Scenario,
  type TreeEdge,
  type TreeNode,
} from "../model/types";
import {
  FIELD_INDEX,
  STAT_WIDTH,
  compilePath,
  finalValue,
  prepare,
  simulate,
  traceValue,
  type CompiledPath,
  type FieldName,
  type Prepared,
  type Trace,
} from "./engine";

// ---------------------------------------------------------------------------
// Rounding for output (money 2 dp, probabilities 4 dp). Never used during a run.
// ---------------------------------------------------------------------------

export const r2 = (x: number): number => {
  const v = Math.round(x * 100) / 100;
  return v === 0 ? 0 : v; // avoid -0
};
export const r4 = (x: number): number => {
  const v = Math.round(x * 10000) / 10000;
  return v === 0 ? 0 : v;
};

// ---------------------------------------------------------------------------
// Path enumeration
// ---------------------------------------------------------------------------

/** Subsets of n listed items: empty set first, then by size, then in listed order. */
export function subsetsOf(n: number): number[][] {
  const out: number[][] = [[]];
  for (let k = 1; k <= n; k++) {
    const combo: number[] = [];
    const rec = (start: number) => {
      if (combo.length === k) {
        out.push([...combo]);
        return;
      }
      for (let i = start; i < n; i++) {
        combo.push(i);
        rec(i + 1);
        combo.pop();
      }
    };
    rec(0);
  }
  return out;
}

interface OptionSet {
  /** option ids (action ids) in listed order */
  ids: string[];
  labels: string[];
}

/** Every choice at one decision point, in enumeration order. */
export function optionSets(prep: Prepared, dpIndex: number): OptionSet[] {
  const dp = prep.decisionPoints[dpIndex];
  const label = (actionId: string) => prep.actionsById.get(actionId)!.label;
  if (dp.kind === "single") {
    return dp.options.map((o) => ({ ids: [o.actionId], labels: [label(o.actionId)] }));
  }
  return subsetsOf(dp.options.length).map((idx) => ({
    ids: idx.map((i) => dp.options[i].actionId),
    labels: idx.map((i) => label(dp.options[i].actionId)),
  }));
}

export function countPaths(s: Scenario): number {
  let n = 1;
  for (const dp of s.decisionPoints) {
    n *= dp.kind === "single" ? dp.options.length : Math.pow(2, dp.options.length);
  }
  return n;
}

export function pathIdOf(prep: Prepared, choices: Record<string, string[]>): string {
  return prep.decisionPoints
    .map((dp) => `${dp.id}:${choices[dp.id].length ? choices[dp.id].join("+") : "none"}`)
    .join("|");
}

export function enumeratePaths(prep: Prepared): Path[] {
  const total = countPaths(prep.s);
  if (total > MAX_PATHS) {
    throw new ScenarioError(
      `decisionPoints: ${total} paths exceeds the limit of ${MAX_PATHS}; reduce the options`,
    );
  }
  const sets = prep.decisionPoints.map((_, i) => optionSets(prep, i));
  const defaults = prep.decisionPoints.map((dp) =>
    dp.kind === "single" ? dp.options.find((o) => o.isDefault)!.actionId : null,
  );
  const paths: Path[] = [];
  const pick: number[] = new Array(sets.length).fill(0);
  const rec = (d: number) => {
    if (d === sets.length) {
      const choices: Record<string, string[]> = {};
      let isDefault = true;
      for (let i = 0; i < sets.length; i++) {
        const ids = sets[i][pick[i]].ids;
        choices[prep.decisionPoints[i].id] = ids;
        const def = defaults[i];
        if (def === null ? ids.length !== 0 : !(ids.length === 1 && ids[0] === def)) isDefault = false;
      }
      paths.push({ id: pathIdOf(prep, choices), choices, isDefault });
      return;
    }
    for (let k = 0; k < sets[d].length; k++) {
      pick[d] = k;
      rec(d + 1);
    }
  };
  rec(0);
  return paths;
}

// ---------------------------------------------------------------------------
// Per-run scalars
// ---------------------------------------------------------------------------

export function churnCostOf(prep: Prepared, tr: Trace): number {
  let c = 0;
  for (const i of tr.churned) {
    c += prep.monthlyMargin[i] * prep.s.objective.churnHorizonMonthsAfterEnd;
  }
  return c;
}

export function endNetCashOf(tr: Trace): number {
  return (
    finalValue(tr, "cash") -
    finalValue(tr, "creditDrawn") -
    finalValue(tr, "accruedInterest") -
    finalValue(tr, "financingOutstanding")
  );
}

export function economicProfitOf(prep: Prepared, tr: Trace): number {
  return finalValue(tr, "profit") - churnCostOf(prep, tr);
}

// ---------------------------------------------------------------------------
// Quick evaluation (threshold searches): survival, mean economic profit, mean end net cash
// ---------------------------------------------------------------------------

export interface Ranked {
  id: string;
  survivors: number;
  runs: number;
  survivalProb: number;
  /** mean days survived: failDay for a failed run, horizonDays for a survivor */
  days: number;
  /** the ranking value (mean economic profit unless the scenario sets a valueFormula) */
  value: number;
  econ: number; // mean economic profit
  endNet: number; // mean end net cash
}

export function evaluateQuick(
  prep: Prepared,
  paths: CompiledPath[],
  runs: number,
  deterministic: boolean,
  onPath?: (done: number) => void,
): Ranked[] {
  const out: Ranked[] = [];
  for (let p = 0; p < paths.length; p++) {
    let surv = 0;
    let econ = 0;
    let endNet = 0;
    let days = 0;
    const sums: Record<string, number> | null = prep.valueFn ? {} : null;
    for (let r = 0; r < runs; r++) {
      const tr = simulate(prep, paths[p], r, { deterministic, record: false, collectEvents: false });
      if (!tr.failed) surv++;
      days += tr.failed ? tr.failDay : prep.H;
      econ += economicProfitOf(prep, tr);
      endNet += endNetCashOf(tr);
      if (sums) {
        const sc = scalarsOf(prep, tr) as unknown as Record<string, number | boolean>;
        for (const k of Object.keys(sc)) if (typeof sc[k] === "number") sums[k] = (sums[k] ?? 0) + (sc[k] as number);
      }
    }
    let value = econ / runs;
    if (sums && prep.valueFn) {
      const means: Record<string, number> = {};
      for (const k of Object.keys(sums)) means[k] = sums[k] / runs;
      means.survivalProb = surv / runs;
      value = prep.valueFn(means);
    }
    out.push({
      id: paths[p].id,
      survivors: surv,
      runs,
      survivalProb: surv / runs,
      days: days / runs,
      value,
      econ: econ / runs,
      endNet: endNet / runs,
    });
    onPath?.(p + 1);
  }
  return out;
}

// ---------------------------------------------------------------------------
// Ranking (spec: "Objective, constraints and goodwill cost -> Ranking")
// ---------------------------------------------------------------------------

const idCmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

/**
 * The best-ranked item of a non-empty list.
 * Eligible paths (survivalProb >= target): highest value, ties within the tolerance broken by
 * survivalProb, endNetCash, id. If none is eligible (Addendum A1.3): survivalProb, mean days
 * survived, value, id.
 */
export function pickBest<T extends Ranked>(items: T[], target: number, tol: number): T {
  let maxValue = -Infinity;
  let anyEligible = false;
  for (const it of items) {
    if (it.survivalProb >= target) {
      anyEligible = true;
      if (it.value > maxValue) maxValue = it.value;
    }
  }
  let best: T | null = null;
  if (anyEligible) {
    for (const it of items) {
      if (it.survivalProb < target || it.value < maxValue - tol) continue;
      if (
        best === null ||
        it.survivalProb > best.survivalProb ||
        (it.survivalProb === best.survivalProb &&
          (it.endNet > best.endNet || (it.endNet === best.endNet && idCmp(it.id, best.id) < 0)))
      ) {
        best = it;
      }
    }
  } else {
    for (const it of items) {
      if (
        best === null ||
        it.survivors > best.survivors ||
        (it.survivors === best.survivors &&
          (it.days > best.days ||
            (it.days === best.days &&
              (it.value > best.value || (it.value === best.value && idCmp(it.id, best.id) < 0)))))
      ) {
        best = it;
      }
    }
  }
  return best!;
}

/** All items ordered best first. */
export function rankAll<T extends Ranked>(items: T[], target: number, tol: number): T[] {
  const rem = [...items];
  const out: T[] = [];
  while (rem.length > 0) {
    const b = pickBest(rem, target, tol);
    out.push(b);
    rem.splice(rem.indexOf(b), 1);
  }
  return out;
}

/** Paths not beaten by any other path on both survivalProb and mean economic profit. */
export function frontierOf<T extends Ranked>(items: T[]): T[] {
  return items.filter(
    (i) =>
      !items.some(
        (j) =>
          j !== i &&
          j.survivalProb >= i.survivalProb &&
          j.econ >= i.econ &&
          (j.survivalProb > i.survivalProb || j.econ > i.econ),
      ),
  );
}

// ---------------------------------------------------------------------------
// Full summary of one path
// ---------------------------------------------------------------------------

/** nearest rank: the value at index ceil(p/100 * n) - 1 of the ascending sorted values */
export function nearestRank(sorted: ArrayLike<number>, n: number, p: number): number {
  return sorted[Math.max(0, Math.ceil((p / 100) * n) - 1)];
}

/** Rearrange a[lo..hi] so that a[k] holds the k-th smallest value, smaller-or-equal to its left, larger-or-equal to its right. */
function select(a: Float64Array, k: number, lo: number, hi: number): void {
  while (lo < hi) {
    const x = a[lo];
    const y = a[(lo + hi) >> 1];
    const z = a[hi];
    const pivot = x < y ? (y < z ? y : x < z ? z : x) : x < z ? x : y < z ? z : y;
    let i = lo;
    let j = hi;
    while (i <= j) {
      while (a[i] < pivot) i++;
      while (a[j] > pivot) j--;
      if (i <= j) {
        const t = a[i];
        a[i] = a[j];
        a[j] = t;
        i++;
        j--;
      }
    }
    if (k <= j) hi = j;
    else if (k >= i) lo = i;
    else return;
  }
}

/** Nearest-rank p10, p50, p90 of a[0..n-1] without a full sort. Reorders `a`. */
function threePercentiles(a: Float64Array, n: number): [number, number, number] {
  const k10 = Math.max(0, Math.ceil(0.1 * n) - 1);
  const k50 = Math.max(0, Math.ceil(0.5 * n) - 1);
  const k90 = Math.max(0, Math.ceil(0.9 * n) - 1);
  select(a, k50, 0, n - 1);
  if (k10 < k50) select(a, k10, 0, k50 - 1);
  if (k90 > k50) select(a, k90, k50 + 1, n - 1);
  return [a[k10], a[k50], a[k90]];
}

const DAILY_FIELDS: FieldName[] = [
  "cash",
  "creditDrawn",
  "receivablesOpen",
  "payablesOpen",
  "revenue",
  "profit",
];

interface RunScalars {
  failed: boolean;
  failDay: number;
  revenue: number;
  grossProfit: number;
  discountsGiven: number;
  lateFeeIncome: number;
  supplierDiscounts: number;
  collectionCosts: number;
  operatingExpense: number;
  interestExpense: number;
  financingFees: number;
  financingOutstanding: number;
  shockExpense: number;
  churnCost: number;
  profit: number;
  economicProfit: number;
  endNetCash: number;
  peakCreditDrawn: number;
  endReceivables: number;
  endPayables: number;
  daysSurvived: number;
}

function scalarsOf(prep: Prepared, tr: Trace): RunScalars {
  let peak = 0;
  const off = FIELD_INDEX.creditDrawn * tr.W;
  for (let d = 0; d < tr.W; d++) peak = Math.max(peak, tr.data[off + d]);
  const churnCost = churnCostOf(prep, tr);
  const profit = finalValue(tr, "profit");
  return {
    failed: tr.failed,
    failDay: tr.failDay,
    revenue: finalValue(tr, "revenue"),
    grossProfit: finalValue(tr, "revenue") - finalValue(tr, "cogs"),
    discountsGiven: finalValue(tr, "discountsGiven"),
    lateFeeIncome: finalValue(tr, "lateFeeIncome"),
    supplierDiscounts: finalValue(tr, "supplierDiscounts"),
    collectionCosts: finalValue(tr, "collectionCosts"),
    operatingExpense: finalValue(tr, "operatingExpense"),
    interestExpense: finalValue(tr, "interestPaid") + finalValue(tr, "accruedInterest"),
    financingFees: finalValue(tr, "financingFees"),
    financingOutstanding: finalValue(tr, "financingOutstanding"),
    daysSurvived: tr.failed ? tr.failDay : tr.H,
    shockExpense: finalValue(tr, "shockExpense"),
    churnCost,
    profit,
    economicProfit: profit - churnCost,
    endNetCash: endNetCashOf(tr),
    peakCreditDrawn: peak,
    endReceivables: finalValue(tr, "receivablesOpen"),
    endPayables: finalValue(tr, "payablesOpen"),
  };
}

type RawMetrics = {
  survivalProb: number;
  economicProfit: number;
  profit: number;
  endNetCash: number;
  revenue: number;
  grossProfit: number;
  discountsGiven: number;
  lateFeeIncome: number;
  supplierDiscounts: number;
  collectionCosts: number;
  operatingExpense: number;
  interestExpense: number;
  financingFees: number;
  financingOutstanding: number;
  daysSurvived: number;
  shockExpense: number;
  churnCost: number;
  peakCreditDrawn: number;
  endReceivables: number;
  endPayables: number;
};

/** Unrounded means over a set of runs, used for ranking and the profit bridge. */
function rawMeans(sc: RunScalars[], totalRuns: number): RawMetrics {
  const n = sc.length;
  const m = (f: (s: RunScalars) => number) => {
    let x = 0;
    for (const s of sc) x += f(s);
    return n === 0 ? 0 : x / n;
  };
  return {
    survivalProb: sc.filter((s) => !s.failed).length / totalRuns,
    economicProfit: m((s) => s.economicProfit),
    profit: m((s) => s.profit),
    endNetCash: m((s) => s.endNetCash),
    revenue: m((s) => s.revenue),
    grossProfit: m((s) => s.grossProfit),
    discountsGiven: m((s) => s.discountsGiven),
    lateFeeIncome: m((s) => s.lateFeeIncome),
    supplierDiscounts: m((s) => s.supplierDiscounts),
    collectionCosts: m((s) => s.collectionCosts),
    operatingExpense: m((s) => s.operatingExpense),
    interestExpense: m((s) => s.interestExpense),
    financingFees: m((s) => s.financingFees),
    financingOutstanding: m((s) => s.financingOutstanding),
    daysSurvived: m((s) => s.daysSurvived),
    shockExpense: m((s) => s.shockExpense),
    churnCost: m((s) => s.churnCost),
    peakCreditDrawn: m((s) => s.peakCreditDrawn),
    endReceivables: m((s) => s.endReceivables),
    endPayables: m((s) => s.endPayables),
  };
}

function pctOf(values: number[]): Pct {
  const v = Float64Array.from(values).sort();
  const n = v.length;
  return {
    p10: r2(nearestRank(v, n, 10)),
    p50: r2(nearestRank(v, n, 50)),
    p90: r2(nearestRank(v, n, 90)),
  };
}

function buildMetrics(sc: RunScalars[], totalRuns: number, histogram: boolean): Metrics {
  const raw = rawMeans(sc, totalRuns);
  const hist: Record<string, number> = {};
  if (histogram) {
    for (const s of sc) if (s.failed) hist[String(s.failDay)] = (hist[String(s.failDay)] ?? 0) + 1;
  }
  return {
    survivalProb: r4(raw.survivalProb),
    economicProfit: { mean: r2(raw.economicProfit), ...pctOf(sc.map((s) => s.economicProfit)) },
    profit: { mean: r2(raw.profit), ...pctOf(sc.map((s) => s.profit)) },
    endNetCash: { mean: r2(raw.endNetCash), ...pctOf(sc.map((s) => s.endNetCash)) },
    revenue: r2(raw.revenue),
    grossProfit: r2(raw.grossProfit),
    discountsGiven: r2(raw.discountsGiven),
    lateFeeIncome: r2(raw.lateFeeIncome),
    supplierDiscounts: r2(raw.supplierDiscounts),
    collectionCosts: r2(raw.collectionCosts),
    operatingExpense: r2(raw.operatingExpense),
    interestExpense: r2(raw.interestExpense),
    financingFees: r2(raw.financingFees),
    financingOutstanding: r2(raw.financingOutstanding),
    shockExpense: r2(raw.shockExpense),
    churnCost: r2(raw.churnCost),
    peakCreditDrawn: r2(raw.peakCreditDrawn),
    endReceivables: r2(raw.endReceivables),
    endPayables: r2(raw.endPayables),
    failDayHistogram: hist,
  };
}

export function medianRunSnapshots(prep: Prepared, cp: CompiledPath, run: number, det: boolean): DaySnapshot[] {
  const tr = simulate(prep, cp, run, { deterministic: det, record: true, collectEvents: true });
  const out: DaySnapshot[] = [];
  for (let d = 0; d <= tr.H; d++) {
    out.push({
      day: d,
      cash: r2(traceValue(tr, "cash", d)),
      creditDrawn: r2(traceValue(tr, "creditDrawn", d)),
      receivablesOpen: r2(traceValue(tr, "receivablesOpen", d)),
      payablesOpen: r2(traceValue(tr, "payablesOpen", d)),
      revenue: r2(traceValue(tr, "revenue", d)),
      profit: r2(traceValue(tr, "profit", d)),
      failed: tr.failed && d >= tr.failDay,
      events: tr.events![d].map((e) => ({ ...e, amount: r2(e.amount) })),
    });
  }
  return out;
}

export interface PathSummary extends Ranked {
  path: Path;
  cp: CompiledPath;
  raw: RawMetrics;
  result: PathResult;
  /** share of runs in which each customer churned, by customer index */
  churnProbs: number[];
}

/** Liquidity at the shock day over all runs (Addendum A3). */
function buildLiquidity(
  prep: Prepared,
  samples: { liquidity: number; inflows: number; outflows: number; collections: number; financingNet: number; actionCosts: number }[],
): Liquidity {
  const n = samples.length;
  const mean = (f: (x: (typeof samples)[number]) => number) => {
    let t = 0;
    for (const x of samples) t += f(x);
    return t / n;
  };
  const sorted = Float64Array.from(samples.map((x) => x.liquidity)).sort();
  const safe = nearestRank(sorted, n, (1 - prep.s.objective.survivalTarget) * 100);
  const shock = prep.s.shocks.find((k) => k.id === prep.s.threshold.shockIdToScale)!.amount;
  return {
    meanLiquidity: r2(mean((x) => x.liquidity)),
    safeLiquidity: r2(safe),
    meanInflows: r2(mean((x) => x.inflows)),
    meanOutflows: r2(mean((x) => x.outflows)),
    gapAtShock: r2(Math.max(0, shock - safe)),
    spareAtShock: r2(Math.max(0, safe - shock)),
    meanFinancingNet: r2(mean((x) => x.financingNet)),
    meanCollections: r2(mean((x) => x.collections)),
    meanActionCosts: r2(mean((x) => x.actionCosts)),
  };
}

export function summarizePath(
  prep: Prepared,
  path: Path,
  runs: number,
  deterministic: boolean,
): PathSummary {
  const cp = compilePath(prep, path);
  const W = prep.H + 1;
  const nCust = prep.s.customers.length;
  const buf = DAILY_FIELDS.map(() => new Float64Array(W * runs));
  const dailyOffsets = DAILY_FIELDS.map((name) => FIELD_INDEX[name] * W);
  const scalars: RunScalars[] = [];
  const liqSamples: Parameters<typeof buildLiquidity>[1] = [];
  const custTotals = new Float64Array(nCust * STAT_WIDTH);
  const churnCounts = new Float64Array(nCust);
  for (let r = 0; r < runs; r++) {
    const tr = simulate(prep, cp, r, { deterministic, record: true, collectEvents: false, track: true });
    scalars.push(scalarsOf(prep, tr));
    liqSamples.push(tr.liq!);
    for (let i = 0; i < custTotals.length; i++) custTotals[i] += tr.stats![i];
    for (const c of tr.churned) churnCounts[c] += 1;
    const data = tr.data;
    for (let f = 0; f < DAILY_FIELDS.length; f++) {
      const off = dailyOffsets[f];
      const b = buf[f];
      for (let d = 0; d < W; d++) b[d * runs + r] = data[off + d];
    }
  }

  const fan = (f: number): DailyPct => {
    const o: DailyPct = { p10: [], p50: [], p90: [] };
    for (let d = 0; d < W; d++) {
      const sub = buf[f].subarray(d * runs, (d + 1) * runs);
      const [a, b, c] = threePercentiles(sub, runs);
      o.p10.push(r2(a));
      o.p50.push(r2(b));
      o.p90.push(r2(c));
    }
    return o;
  };
  const daily = {
    cash: fan(0),
    creditDrawn: fan(1),
    receivablesOpen: fan(2),
    payablesOpen: fan(3),
    revenue: fan(4),
    profit: fan(5),
  };

  const raw = rawMeans(scalars, runs);
  const survivors = scalars.filter((s) => !s.failed);

  // median run: closest endNetCash to the path's p50 endNetCash, ties to the lowest run index
  const sortedEnd = Float64Array.from(scalars.map((s) => s.endNetCash)).sort();
  const p50 = nearestRank(sortedEnd, runs, 50);
  let medianIdx = 0;
  let bestDist = Infinity;
  for (let r = 0; r < runs; r++) {
    const dist = Math.abs(scalars[r].endNetCash - p50);
    if (dist < bestDist) {
      bestDist = dist;
      medianIdx = r;
    }
  }

  const churnProbs = Array.from(churnCounts, (x) => x / runs);
  const customerStats: CustomerStats[] = prep.s.customers.map((c, i) => {
    const o = i * STAT_WIDTH;
    const invoices = custTotals[o];
    const paid = custTotals[o + 1];
    const due = custTotals[o + 3];
    return {
      customerId: c.id,
      customerName: c.name,
      invoicesPerRun: r2(invoices / runs),
      paidShare: r4(invoices > 0 ? paid / invoices : 0),
      avgDaysToPay: paid > 0 ? r2(custTotals[o + 2] / paid) : null,
      paidByDueShare: due > 0 ? r4(custTotals[o + 4] / due) : null,
      offerAcceptProb: r4(prep.acceptProb[i]),
      churnProb: r4(churnProbs[i]),
    };
  });

  const result: PathResult = {
    id: path.id,
    choices: path.choices,
    isDefault: path.isDefault,
    metrics: buildMetrics(scalars, runs, true),
    metricsSurvivorsOnly: survivors.length > 0 ? buildMetrics(survivors, runs, false) : null,
    liquidity: buildLiquidity(prep, liqSamples),
    customerStats,
    daily,
    medianRun: medianRunSnapshots(prep, cp, medianIdx, deterministic),
  };

  return {
    id: path.id,
    survivors: survivors.length,
    runs,
    survivalProb: raw.survivalProb,
    days: raw.daysSurvived,
    value: prep.valueFn ? prep.valueFn(raw as unknown as Record<string, number>) : raw.economicProfit,
    econ: raw.economicProfit,
    endNet: raw.endNetCash,
    path,
    cp,
    raw,
    result,
    churnProbs,
  };
}

// ---------------------------------------------------------------------------
// Main run: every path, ranked
// ---------------------------------------------------------------------------

export interface MainRun {
  prep: Prepared;
  summaries: PathSummary[]; // ranked, best first
  best: PathSummary;
  def: PathSummary;
  frontier: PathSummary[];
}

export function runMain(
  s: Scenario,
  deterministic: boolean,
  onProgress?: (pct: number) => void,
): MainRun {
  const prep = prepare(s);
  const paths = enumeratePaths(prep);
  const runs = deterministic ? 1 : s.meta.runsPerPath;
  const sums: PathSummary[] = [];
  for (let i = 0; i < paths.length; i++) {
    sums.push(summarizePath(prep, paths[i], runs, deterministic));
    onProgress?.(((i + 1) / paths.length) * 100);
  }
  const { survivalTarget, profitTieToleranceSGD } = s.objective;
  const ranked = rankAll(sums, survivalTarget, profitTieToleranceSGD);
  const frontierSet = new Set(frontierOf(sums));
  return {
    prep,
    summaries: ranked,
    best: ranked[0],
    def: sums.find((x) => x.path.isDefault)!,
    frontier: ranked.filter((x) => frontierSet.has(x)),
  };
}

// ---------------------------------------------------------------------------
// Profit bridge and decision tree
// ---------------------------------------------------------------------------

/**
 * Items are (mean of best path) - (mean of default path), signed so they add up to the
 * difference in mean economic profit. Cent rounding uses largest remainder so the rounded
 * items add up exactly to the rounded difference.
 */
export function profitBridge(best: RawMetrics, def: RawMetrics): { item: string; amount: number }[] {
  const items: [string, number][] = [
    ["Gross profit", best.grossProfit - def.grossProfit],
    ["Discounts given", -(best.discountsGiven - def.discountsGiven)],
    ["Late fees", best.lateFeeIncome - def.lateFeeIncome],
    ["Supplier discounts", best.supplierDiscounts - def.supplierDiscounts],
    ["Collection costs", -(best.collectionCosts - def.collectionCosts)],
    ["Operating expense", -(best.operatingExpense - def.operatingExpense)],
    ["Interest", -(best.interestExpense - def.interestExpense)],
    ["Financing fees", -(best.financingFees - def.financingFees)],
    ["Shock", -(best.shockExpense - def.shockExpense)],
    ["Churn cost", -(best.churnCost - def.churnCost)],
  ];
  const targetCents = Math.round((best.economicProfit - def.economicProfit) * 100);
  const cents = items.map(([, v]) => Math.round(v * 100));
  let diff = targetCents - cents.reduce((a, b) => a + b, 0);
  const frac = items.map(([, v], i) => ({ i, f: v * 100 - cents[i] }));
  // hand out the remaining cents to the items that lost the most / gained the least in rounding
  frac.sort((a, b) => (diff > 0 ? b.f - a.f : a.f - b.f));
  for (let k = 0; diff !== 0; k = (k + 1) % frac.length) {
    const step = diff > 0 ? 1 : -1;
    cents[frac[k].i] += step;
    diff -= step;
  }
  return items.map(([name], i) => ({ item: name, amount: cents[i] / 100 || 0 }));
}

export function buildTree(
  main: MainRun,
): { nodes: TreeNode[]; edges: TreeEdge[] } {
  const { prep, summaries, best } = main;
  const nodes: TreeNode[] = prep.decisionPoints.map((dp) => ({
    id: dp.id,
    day: dp.day,
    order: dp.order,
    label: dp.label,
    kind: dp.kind,
  }));
  const edges: TreeEdge[] = [];
  prep.decisionPoints.forEach((dp, di) => {
    for (const set of optionSets(prep, di)) {
      const key = set.ids.join("+");
      const first = summaries.find((x) => x.path.choices[dp.id].join("+") === key)!;
      edges.push({
        nodeId: dp.id,
        optionId: set.ids.length ? key : "none",
        label: set.ids.length ? set.labels.join(" + ") : "No action",
        bestPathId: first.id,
        survivalProb: r4(first.survivalProb),
        economicProfit: r2(first.econ),
        onBestPath: best.path.choices[dp.id].join("+") === key,
      });
    }
  });
  return { nodes, edges };
}
