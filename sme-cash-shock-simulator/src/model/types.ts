import { z } from "zod";
import { parseFormula } from "../sim/formula";

// ---------------------------------------------------------------------------
// Scenario schema (spec: "Input data model" and "Field reference").
// Every field is required unless the spec marks it nullable; unknown fields are
// refused so nothing is silently ignored or guessed.
// ---------------------------------------------------------------------------

const int = z.number().int();
const money = z.number().finite();
const nonNeg = z.number().finite().min(0);
const unit = z.number().finite().min(0).max(1);

const earlyPayDiscountSchema = z
  .object({ rate: unit, windowDays: int.min(0) })
  .strict();

const customerSchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    keyClient: z.boolean(),
    meanDaysToPay: z.number().finite().min(1),
    dueDays: int.min(0),
    earlyPayDiscount: earlyPayDiscountSchema.nullable(),
    offerAcceptance: z
      .object({ alpha: z.number().finite().gt(0), beta: z.number().finite().gt(0) })
      .strict(),
    orderCycleDays: int.min(1),
    firstOrderDay: int.min(1),
    orders: z
      .array(
        z
          .object({ item: z.string().min(1), unitPrice: nonNeg, qtyPerCycle: nonNeg })
          .strict(),
      ),
  })
  .strict();

const receivableSchema = z
  .object({
    id: z.string().min(1),
    customerId: z.string().min(1),
    amount: z.number().finite().gt(0),
    invoiceDay: int.max(0),
  })
  .strict();

const payableSchema = z
  .object({
    id: z.string().min(1),
    label: z.string().min(1),
    amount: z.number().finite().gt(0),
    dueDay: int.min(1),
    affectsProfit: z.boolean(),
    earlyPayDiscount: z.object({ rate: unit, byDay: int.min(1) }).strict().nullable(),
  })
  .strict();

const recurringCostSchema = z
  .object({
    id: z.string().min(1),
    label: z.string().min(1),
    amount: nonNeg,
    firstDay: int.min(1),
    repeatEveryDays: int.min(1),
    affectsProfit: z.boolean(),
  })
  .strict();

const creditLineSchema = z
  .object({ id: z.string().min(1), limit: nonNeg, ratePerMonth: nonNeg })
  .strict();

const shockSchema = z
  .object({
    id: z.string().min(1),
    label: z.string().min(1),
    amount: nonNeg,
    announceDay: int,
    dueDay: int.min(1),
    // Addendum A1.2: a shock is a cash event by default; true books it as an expense.
    affectsProfit: z.boolean().default(false),
  })
  .strict();

const collectionActionSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("collection"),
    label: z.string().min(1),
    payProbMultiplier: nonNeg,
    cashCost: nonNeg,
    lateFeeRatePerMonth: nonNeg,
    churnProb: unit,
    churnProbKeyClient: unit,
  })
  .strict();

const discountOfferActionSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("discount_offer"),
    label: z.string().min(1),
    offerRate: unit,
    payWithinDays: int.min(0),
  })
  .strict();

const priceChangeActionSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("price_change"),
    label: z.string().min(1),
    priceMultiplier: nonNeg,
  })
  .strict();

const payableTimingActionSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("payable_timing"),
    label: z.string().min(1),
    payEarly: z.boolean(),
  })
  .strict();

const invoiceFinancingActionSchema = z
  .object({
    id: z.string().min(1),
    type: z.literal("invoice_financing"),
    label: z.string().min(1),
    advanceRate: unit,
    feeRate: nonNeg,
  })
  .strict();

const actionSchema = z.discriminatedUnion("type", [
  collectionActionSchema,
  discountOfferActionSchema,
  priceChangeActionSchema,
  payableTimingActionSchema,
  invoiceFinancingActionSchema,
]);

const strategySchema = z
  .object({
    id: z.string().min(1),
    name: z.string().min(1),
    description: z.string(),
    choices: z.record(z.string(), z.array(z.string())),
  })
  .strict();

const decisionPointSchema = z
  .object({
    id: z.string().min(1),
    day: int.min(1),
    order: int,
    label: z.string().min(1),
    kind: z.enum(["single", "subset"]),
    options: z
      .array(
        z
          .object({
            actionId: z.string().min(1),
            targetId: z.string().min(1),
            isDefault: z.boolean().optional(),
          })
          .strict(),
      )
      .min(1),
  })
  .strict();

const scenarioSchema = z
  .object({
    name: z.string().min(1).optional(),
    meta: z
      .object({
        currency: z.string().min(1),
        horizonDays: int.min(1).max(365),
        runsPerPath: int.min(100).max(10000),
        seed: int.min(0).max(4294967295),
      })
      .strict(),
    business: z
      .object({ cash0: money, grossMargin: unit, creditRepayAbove: nonNeg })
      .strict(),
    priceElasticity: nonNeg,
    customers: z.array(customerSchema),
    receivables: z.array(receivableSchema),
    payables: z.array(payableSchema),
    recurringCosts: z.array(recurringCostSchema),
    creditLines: z.array(creditLineSchema),
    shocks: z.array(shockSchema),
    actions: z.array(actionSchema),
    decisionPoints: z.array(decisionPointSchema),
    strategies: z.array(strategySchema).min(1),
    objective: z
      .object({
        survivalTarget: unit,
        churnHorizonMonthsAfterEnd: nonNeg,
        profitTieToleranceSGD: nonNeg,
        /** optional ranking value, a formula over path means; default is economicProfit */
        valueFormula: z.string().min(1).optional(),
      })
      .strict(),
    threshold: z
      .object({
        shockIdToScale: z.string().min(1),
        maxShock: nonNeg,
        maxExtraBuffer: nonNeg,
        stepSGD: z.number().finite().gt(0),
        runsPerPath: int.min(100).max(10000),
        curveStepSGD: z.number().finite().gt(0),
      })
      .strict(),
  })
  .strict();

export type Scenario = z.infer<typeof scenarioSchema>;
export type Customer = Scenario["customers"][number];
export type Receivable = Scenario["receivables"][number];
export type Payable = Scenario["payables"][number];
export type RecurringCost = Scenario["recurringCosts"][number];
export type CreditLine = Scenario["creditLines"][number];
export type Shock = Scenario["shocks"][number];
export type Action = z.infer<typeof actionSchema>;
export type CollectionAction = z.infer<typeof collectionActionSchema>;
export type DiscountOfferAction = z.infer<typeof discountOfferActionSchema>;
export type PriceChangeAction = z.infer<typeof priceChangeActionSchema>;
export type PayableTimingAction = z.infer<typeof payableTimingActionSchema>;
export type InvoiceFinancingAction = z.infer<typeof invoiceFinancingActionSchema>;
export type Strategy = z.infer<typeof strategySchema>;
export type DecisionPoint = Scenario["decisionPoints"][number];
export type DecisionOption = DecisionPoint["options"][number];

export const ALL_OPEN_RECEIVABLES = "ALL_OPEN_RECEIVABLES";
export const ALL_CUSTOMERS = "ALL_CUSTOMERS";
export const MAX_SUBSET_OPTIONS = 6;
export const MAX_PATHS = 5000;

export class ScenarioError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ScenarioError";
  }
}

function dup(ids: string[]): string | null {
  const seen = new Set<string>();
  for (const id of ids) {
    if (seen.has(id)) return id;
    seen.add(id);
  }
  return null;
}

/** Cross-field checks that the per-field schema cannot express. Returns the first error or null. */
function crossCheck(s: Scenario): string | null {
  const H = s.meta.horizonDays;
  const customerIds = new Set(s.customers.map((c) => c.id));
  const payableIds = new Set(s.payables.map((p) => p.id));
  const actionById = new Map(s.actions.map((a) => [a.id, a]));
  const invoiceIds = new Set<string>(s.receivables.map((r) => r.id));
  for (const c of s.customers) {
    if (c.orders.length === 0) continue;
    for (let d = c.firstOrderDay; d <= H; d += c.orderCycleDays) invoiceIds.add(`${c.id}-INV-${d}`);
  }

  for (const [list, ids] of [
    ["customers", s.customers.map((c) => c.id)],
    ["receivables", s.receivables.map((r) => r.id)],
    ["payables", s.payables.map((p) => p.id)],
    ["recurringCosts", s.recurringCosts.map((r) => r.id)],
    ["creditLines", s.creditLines.map((c) => c.id)],
    ["shocks", s.shocks.map((c) => c.id)],
    ["actions", s.actions.map((a) => a.id)],
    ["decisionPoints", s.decisionPoints.map((d) => d.id)],
  ] as const) {
    const d = dup(ids as string[]);
    if (d !== null) return `${list}: duplicate id "${d}"`;
  }

  for (let i = 0; i < s.receivables.length; i++) {
    if (!customerIds.has(s.receivables[i].customerId))
      return `receivables.${i}.customerId: unknown customer "${s.receivables[i].customerId}"`;
  }
  for (let i = 0; i < s.payables.length; i++) {
    const p = s.payables[i];
    if (p.dueDay > H) return `payables.${i}.dueDay: must be between 1 and horizonDays (${H})`;
    if (p.earlyPayDiscount && p.earlyPayDiscount.byDay > H)
      return `payables.${i}.earlyPayDiscount.byDay: must be between 1 and horizonDays (${H})`;
  }
  for (let i = 0; i < s.shocks.length; i++) {
    const k = s.shocks[i];
    if (k.dueDay > H) return `shocks.${i}.dueDay: must be between 1 and horizonDays (${H})`;
    if (k.announceDay > k.dueDay) return `shocks.${i}.announceDay: must not be after dueDay`;
  }
  if (!s.shocks.some((k) => k.id === s.threshold.shockIdToScale))
    return `threshold.shockIdToScale: unknown shock "${s.threshold.shockIdToScale}"`;

  if (s.objective.valueFormula !== undefined) {
    const f = parseFormula(s.objective.valueFormula);
    if (!f.ok) return `objective.valueFormula: ${f.message}`;
  }

  const dayOrder = new Set<string>();
  for (let i = 0; i < s.decisionPoints.length; i++) {
    const dp = s.decisionPoints[i];
    const at = `decisionPoints.${i}`;
    if (dp.day > H) return `${at}.day: must be between 1 and horizonDays (${H})`;
    const key = `${dp.day}/${dp.order}`;
    if (dayOrder.has(key)) return `${at}.order: duplicate (day, order) pair ${key}`;
    dayOrder.add(key);
    if (dp.kind === "subset" && dp.options.length > MAX_SUBSET_OPTIONS)
      return `${at}.options: a subset decision point may have at most ${MAX_SUBSET_OPTIONS} options`;
    const dd = dup(dp.options.map((o) => o.actionId));
    if (dd !== null) return `${at}.options: actionId "${dd}" listed twice in one decision point`;
    if (dp.kind === "single") {
      const defaults = dp.options.filter((o) => o.isDefault === true).length;
      if (defaults !== 1)
        return `${at}.options: a single-choice point needs exactly one option with isDefault: true (found ${defaults})`;
    }
    for (let j = 0; j < dp.options.length; j++) {
      const o = dp.options[j];
      const oat = `${at}.options.${j}`;
      const a = actionById.get(o.actionId);
      if (!a) return `${oat}.actionId: unknown action "${o.actionId}"`;
      if (a.type === "collection" && !customerIds.has(o.targetId))
        return `${oat}.targetId: collection target must be a customer id, got "${o.targetId}"`;
      if (a.type === "discount_offer" && o.targetId !== ALL_OPEN_RECEIVABLES)
        return `${oat}.targetId: discount_offer target must be ${ALL_OPEN_RECEIVABLES}`;
      if (
        a.type === "price_change" &&
        o.targetId !== ALL_CUSTOMERS &&
        !customerIds.has(o.targetId)
      )
        return `${oat}.targetId: price_change target must be ${ALL_CUSTOMERS} or a customer id`;
      if (a.type === "invoice_financing" && !invoiceIds.has(o.targetId))
        return `${oat}.targetId: invoice_financing target must be an invoice id, got "${o.targetId}"`;
      if (a.type === "payable_timing") {
        if (!payableIds.has(o.targetId))
          return `${oat}.targetId: payable_timing target must be a payable id, got "${o.targetId}"`;
        const p = s.payables.find((x) => x.id === o.targetId)!;
        if (a.payEarly && p.earlyPayDiscount === null)
          return `${oat}.targetId: payable "${p.id}" has no earlyPayDiscount, so it cannot be paid early`;
      }
    }
  }
  return crossCheckStrategies(s);
}

/**
 * The option ids a strategy picks at every decision point, in listed order: unlisted points take
 * their default (the isDefault option, or none for subset points). Throws ScenarioError naming the
 * strategy and decision point when a choice is invalid.
 */
export function resolveStrategyChoices(s: Scenario, st: Strategy): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const key of Object.keys(st.choices)) {
    if (!s.decisionPoints.some((d) => d.id === key))
      throw new ScenarioError(`strategies "${st.id}": unknown decision point "${key}"`);
  }
  for (const dp of s.decisionPoints) {
    const listed = st.choices[dp.id];
    if (listed === undefined) {
      out[dp.id] = dp.kind === "single" ? [dp.options.find((o) => o.isDefault)!.actionId] : [];
      continue;
    }
    for (const id of listed) {
      if (!dp.options.some((o) => o.actionId === id))
        throw new ScenarioError(
          `strategies "${st.id}", decision point "${dp.id}": unknown option id "${id}"`,
        );
    }
    if (new Set(listed).size !== listed.length)
      throw new ScenarioError(`strategies "${st.id}", decision point "${dp.id}": option listed twice`);
    if (dp.kind === "single" && listed.length !== 1)
      throw new ScenarioError(
        `strategies "${st.id}", decision point "${dp.id}": a single-choice point needs exactly one option id (got ${listed.length})`,
      );
    out[dp.id] = dp.options.map((o) => o.actionId).filter((id) => listed.includes(id));
  }
  return out;
}

function crossCheckStrategies(s: Scenario): string | null {
  const d = dup(s.strategies.map((x) => x.id));
  if (d !== null) return `strategies: duplicate id "${d}"`;
  try {
    for (const st of s.strategies) {
      const choices = resolveStrategyChoices(s, st);
      if (st.id === "S0") {
        for (const dp of s.decisionPoints) {
          const def = dp.kind === "single" ? [dp.options.find((o) => o.isDefault)!.actionId] : [];
          if (choices[dp.id].join("+") !== def.join("+"))
            return `strategies "S0", decision point "${dp.id}": S0 must be the default path`;
        }
      }
    }
  } catch (e) {
    return e instanceof ScenarioError ? e.message : String(e);
  }
  if (!s.strategies.some((x) => x.id === "S0")) return `strategies: a strategy with id "S0" is required`;
  return null;
}

/** Parse and validate a scenario. Throws ScenarioError naming the offending field. */
export function validateScenario(input: unknown): Scenario {
  const parsed = scenarioSchema.safeParse(input);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const path = issue.path.join(".") || "(root)";
    throw new ScenarioError(`${path}: ${issue.message}`);
  }
  const err = crossCheck(parsed.data);
  if (err !== null) throw new ScenarioError(err);
  return parsed.data;
}

// ---------------------------------------------------------------------------
// Paths and traces
// ---------------------------------------------------------------------------

export interface Path {
  id: string;
  /** decisionPointId -> chosen option ids ([] = none) */
  choices: Record<string, string[]>;
  isDefault: boolean;
}

export type EventType =
  | "invoice"
  | "collection"
  | "payable"
  | "recurring"
  | "shock"
  | "credit_draw"
  | "credit_repay"
  | "interest"
  | "decision"
  | "churn"
  | "financing"
  | "failure";

export interface SimEvent {
  type: EventType;
  label: string;
  amount: number;
  refId: string;
}

export interface DaySnapshot {
  day: number;
  cash: number;
  creditDrawn: number;
  receivablesOpen: number;
  payablesOpen: number;
  revenue: number;
  profit: number;
  failed: boolean;
  events: SimEvent[];
}

// ---------------------------------------------------------------------------
// Result contract (spec: "Output data contract")
// ---------------------------------------------------------------------------

export type Pct = { p10: number; p50: number; p90: number };
export type DailyPct = { p10: number[]; p50: number[]; p90: number[] };

export type Metrics = {
  survivalProb: number;
  economicProfit: Pct & { mean: number };
  profit: Pct & { mean: number };
  endNetCash: Pct & { mean: number };
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
  peakCreditDrawn: number;
  endReceivables: number;
  endPayables: number;
  failDayHistogram: Record<string, number>;
};

/** Cash you can reach on the shock's due day, before the shock is paid (Addendum A3). */
export type Liquidity = {
  meanLiquidity: number;
  safeLiquidity: number; // nearest-rank percentile (1 - survivalTarget) x 100
  meanInflows: number;
  meanOutflows: number;
  gapAtShock: number; // max(0, shockAmount - safeLiquidity)
  spareAtShock: number; // max(0, safeLiquidity - shockAmount)
  // components up to the shock day, for the bridge tooltip
  meanFinancingNet: number;
  meanCollections: number;
  meanActionCosts: number;
};

/** How one customer paid across the runs of a path. */
export type CustomerStats = {
  customerId: string;
  customerName: string;
  invoicesPerRun: number;
  paidShare: number; // share of invoices paid within the horizon
  avgDaysToPay: number | null; // among paid invoices, counted from max(invoice day, 0)
  paidByDueShare: number | null; // among invoices due within the horizon
  offerAcceptProb: number;
  churnProb: number; // share of runs in which the customer churned
};

export type PathResult = {
  id: string;
  choices: Record<string, string[]>;
  isDefault: boolean;
  metrics: Metrics;
  metricsSurvivorsOnly: Metrics | null;
  liquidity: Liquidity;
  customerStats: CustomerStats[];
  daily: {
    cash: DailyPct;
    creditDrawn: DailyPct;
    receivablesOpen: DailyPct;
    payablesOpen: DailyPct;
    revenue: DailyPct;
    profit: DailyPct;
  };
  medianRun: DaySnapshot[];
};

export type TreeNode = {
  id: string;
  day: number;
  order: number;
  label: string;
  kind: "single" | "subset";
};

export type TreeEdge = {
  nodeId: string;
  optionId: string;
  label: string;
  bestPathId: string;
  survivalProb: number;
  economicProfit: number;
  onBestPath: boolean;
};

export type StrategyResult = {
  id: string;
  name: string;
  description: string;
  pathId: string;
  survivalProb: number;
  cost: number; // direct cost vs S0; positive = costs more than doing nothing
  gapAtShock: number;
  churnRisk: { customerId: string; customerName: string; prob: number }[];
  isRecommended: boolean;
};

export type Result = {
  scenarioName: string;
  bestPathId: string;
  defaultPathId: string;
  bestMeetsTarget: boolean;
  paths: PathResult[];
  frontierPathIds: string[];
  strategies: StrategyResult[];
  defaultGap: { gapAtShock: number; extraBufferForChosenShock: number | null };
  profitSacrificed: number;
  profitBridge: { item: string; amount: number }[];
  tree: { nodes: TreeNode[]; edges: TreeEdge[] };
  threshold: {
    largestSurvivableShock: number | null;
    atLeast: boolean;
    survivalAtThreshold: number | null;
    survivalAtNextStep: number | null;
    extraBufferForChosenShock: number | null;
    curve: { shock: number; survival: number }[];
  };
  runInfo: {
    runsPerPath: number;
    thresholdRunsPerPath: number;
    seed: number;
    pathCount: number;
    elapsedMs: number;
    deterministic: boolean;
  };
};
