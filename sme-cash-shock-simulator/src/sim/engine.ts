import {
  type Action,
  type DecisionPoint,
  type EventType,
  type Path,
  type Scenario,
  type SimEvent,
} from "../model/types";
import { applyAction, acceptanceProbability, volumeMultiplier } from "./actions";
import { valueFunction, type Vars } from "./formula";
import { fnv1a32, uniformHashed } from "./rng";

// ---------------------------------------------------------------------------
// Prepared scenario: everything the daily loop needs, computed once.
// ---------------------------------------------------------------------------

export interface Invoice {
  id: string;
  hash: number; // fnv1a32("pay:" + id), computed once
  cust: number;
  amount: number;
  invoiceDay: number;
  dueDay: number;
  accepted: boolean;
  offerPayDay: number;
  offerRate: number;
  surv: number; // deterministic mode survival value
  financed: boolean;
  advance: number;
}

export interface ChosenAction {
  decisionId: string;
  action: Action;
  targetId: string;
}

export interface CompiledPath {
  id: string;
  /** decision day -> actions in (order, listed option) order */
  byDay: Map<number, ChosenAction[]>;
}

export interface Prepared {
  s: Scenario;
  H: number;
  seed: number;
  /** due day of the shock named in threshold.shockIdToScale: the liquidity measurement day */
  liqDay: number;
  creditLimitTotal: number;
  custIndex: Map<string, number>;
  payIndex: Map<string, number>;
  actionsById: Map<string, Action>;
  hazard: number[];
  acceptProb: number[];
  monthlyMargin: number[];
  decisionPoints: DecisionPoint[]; // sorted by (day, order)
  initialInvoices: Invoice[]; // sorted by id
  /** ranking value from path means when the scenario sets objective.valueFormula; else undefined */
  valueFn: ((vars: Vars) => number) | undefined;
  hash(key: string): number;
}

const hashCache = new Map<string, number>();
function cachedHash(key: string): number {
  let h = hashCache.get(key);
  if (h === undefined) {
    h = fnv1a32(key);
    if (hashCache.size > 200000) hashCache.clear();
    hashCache.set(key, h);
  }
  return h;
}

export function prepare(s: Scenario): Prepared {
  const custIndex = new Map(s.customers.map((c, i) => [c.id, i]));
  const payIndex = new Map(s.payables.map((p, i) => [p.id, i]));
  const initialInvoices: Invoice[] = s.receivables.map((r) => {
    const c = custIndex.get(r.customerId)!;
    return {
      id: r.id,
      hash: cachedHash("pay:" + r.id),
      cust: c,
      amount: r.amount,
      invoiceDay: r.invoiceDay,
      dueDay: r.invoiceDay + s.customers[c].dueDays,
      accepted: false,
      offerPayDay: 0,
      offerRate: 0,
      surv: 1,
      financed: false,
      advance: 0,
    };
  });
  initialInvoices.sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return {
    s,
    H: s.meta.horizonDays,
    seed: s.meta.seed,
    liqDay: s.shocks.find((k) => k.id === s.threshold.shockIdToScale)!.dueDay,
    creditLimitTotal: s.creditLines.reduce((a, l) => a + l.limit, 0),
    custIndex,
    payIndex,
    actionsById: new Map(s.actions.map((a) => [a.id, a])),
    hazard: s.customers.map((c) => 1 / Math.max(c.meanDaysToPay, 1)),
    acceptProb: s.customers.map((c) =>
      acceptanceProbability(c.offerAcceptance.alpha, c.offerAcceptance.beta),
    ),
    monthlyMargin: s.customers.map(
      (c) =>
        c.orders.reduce((sum, o) => sum + o.unitPrice * o.qtyPerCycle, 0) *
        (30 / c.orderCycleDays) *
        s.business.grossMargin,
    ),
    decisionPoints: [...s.decisionPoints].sort((a, b) => a.day - b.day || a.order - b.order),
    initialInvoices,
    valueFn: valueFunction(s.objective.valueFormula),
    hash: cachedHash,
  };
}

/** Turn a path's chosen option ids into the actions to apply on each decision day. */
export function compilePath(prep: Prepared, path: Path): CompiledPath {
  const byDay = new Map<number, ChosenAction[]>();
  for (const dp of prep.decisionPoints) {
    const chosen = new Set(path.choices[dp.id] ?? []);
    const list = byDay.get(dp.day) ?? [];
    for (const o of dp.options) {
      if (!chosen.has(o.actionId)) continue;
      list.push({ decisionId: dp.id, action: prep.actionsById.get(o.actionId)!, targetId: o.targetId });
    }
    if (list.length > 0) byDay.set(dp.day, list);
  }
  return { id: path.id, byDay };
}

// ---------------------------------------------------------------------------
// Per-run state and trace layout
// ---------------------------------------------------------------------------

export const FIELDS = [
  "cash",
  "creditDrawn",
  "accruedInterest",
  "receivablesOpen",
  "payablesOpen",
  "revenue",
  "cogs",
  "discountsGiven",
  "lateFeeIncome",
  "supplierDiscounts",
  "collectionCosts",
  "operatingExpense",
  "shockExpense",
  "interestPaid",
  "profit",
  "financingOutstanding",
  "financingFees",
] as const;
export type FieldName = (typeof FIELDS)[number];
const F: Record<FieldName, number> = Object.fromEntries(FIELDS.map((f, i) => [f, i])) as Record<
  FieldName,
  number
>;
export const FIELD_INDEX = F;

/** Cash you can reach on the shock day (Addendum A3), with the flows that built it. */
export interface LiquiditySample {
  liquidity: number;
  inflows: number;
  outflows: number;
  collections: number;
  financingNet: number;
  actionCosts: number;
}

/** Per-customer counters kept when `track` is on: [invoices, paid, daysSum, dueCount, paidByDue]. */
export const STAT_WIDTH = 5;

export interface Trace {
  H: number;
  /** stride per field: H + 1 when every day was recorded, 1 when only the final day was */
  W: number;
  /** data[fieldIndex * W + day] (day ignored when W === 1: the value is the final-day value) */
  data: Float64Array;
  failed: boolean;
  failDay: number;
  /** indices of customers churned during the run */
  churned: number[];
  /** events[day] when collectEvents was on, else null */
  events: SimEvent[][] | null;
  /** liquidity at the shock day, when `track` was on */
  liq: LiquiditySample | null;
  /** customer payment counters, when `track` was on */
  stats: Float64Array | null;
}

export function traceValue(tr: Trace, field: FieldName, day: number): number {
  return tr.data[F[field] * tr.W + (tr.W === 1 ? 0 : day)];
}

/** Value of a field on the last day, for either recording mode. */
export function finalValue(tr: Trace, field: FieldName): number {
  return tr.data[F[field] * tr.W + tr.W - 1];
}

export type FlowKind = "collection" | "financing" | "action" | "payable" | "recurring" | "interest" | "shock";

export interface RunState {
  prep: Prepared;
  run: number;
  deterministic: boolean;
  t: number;
  cash: number;
  mult: Float64Array;
  lateRate: Float64Array;
  lateStart: Float64Array; // NaN = not set
  churned: Uint8Array;
  priceMult: Float64Array;
  open: Invoice[]; // kept in invoice id order
  payDay: number[];
  payAmt: number[];
  payPaid: Uint8Array;
  drawn: Float64Array;
  collectionCosts: number;
  financingOutstanding: number;
  financingFees: number;
  /** move cash (not for credit draws or repayments), tracking the flow when liquidity is tracked */
  flow(delta: number, kind: FlowKind): void;
  emit(type: EventType, label: string, amount: number, refId: string): void;
}

export interface SimOptions {
  deterministic: boolean;
  /** record every field on every day (needed for fans, charts, tests); off = final day only */
  record: boolean;
  /** collect per-day events (implies record) */
  collectEvents: boolean;
  /** track liquidity at the shock day and per-customer payment counters */
  track?: boolean;
}

function insertSorted(list: Invoice[], inv: Invoice): void {
  let i = list.length;
  list.push(inv);
  while (i > 0 && list[i - 1].id > inv.id) {
    list[i] = list[i - 1];
    i--;
  }
  list[i] = inv;
}

/**
 * simulate(scenario, path, run): the daily loop of the spec's "Cash accounting rules".
 * Every random draw is keyed by what it is for, so all paths share draws for run i.
 */
export function simulate(prep: Prepared, path: CompiledPath, run: number, opts: SimOptions): Trace {
  const s = prep.s;
  const H = prep.H;
  const record = opts.record || opts.collectEvents;
  const W = record ? H + 1 : 1;
  const nCust = s.customers.length;
  const nPay = s.payables.length;
  const lines = s.creditLines;
  const nLines = lines.length;
  const elasticity = s.priceElasticity;
  const gm = s.business.grossMargin;
  const repayAbove = s.business.creditRepayAbove;
  const seed = prep.seed;
  const det = opts.deterministic;
  const track = opts.track === true;

  const data = new Float64Array(FIELDS.length * W);
  const events: SimEvent[][] | null = opts.collectEvents
    ? Array.from({ length: H + 1 }, () => [])
    : null;
  const stats = track ? new Float64Array(nCust * STAT_WIDTH) : null;

  // liquidity tracking (Addendum A3)
  let liqTaken = false;
  let liqSample: LiquiditySample | null = null;
  let inflows = 0;
  let outflows = 0;
  let collectionsTotal = 0;
  let financingNetTotal = 0;
  let actionCostsTotal = 0;

  const st: RunState = {
    prep,
    run,
    deterministic: det,
    t: 0,
    cash: s.business.cash0,
    mult: new Float64Array(nCust).fill(1),
    lateRate: new Float64Array(nCust),
    lateStart: new Float64Array(nCust).fill(NaN),
    churned: new Uint8Array(nCust),
    priceMult: new Float64Array(nCust).fill(1),
    open: prep.initialInvoices.map((i) => ({ ...i })),
    payDay: s.payables.map((p) => p.dueDay),
    payAmt: s.payables.map((p) => p.amount),
    payPaid: new Uint8Array(nPay),
    drawn: new Float64Array(nLines),
    collectionCosts: 0,
    financingOutstanding: 0,
    financingFees: 0,
    flow(delta, kind) {
      st.cash += delta;
      if (!track || liqTaken) return;
      if (delta >= 0) inflows += delta;
      else outflows -= delta;
      if (kind === "collection") collectionsTotal += delta;
      else if (kind === "financing") financingNetTotal += delta;
      else if (kind === "action") actionCostsTotal -= delta;
    },
    emit(type, label, amount, refId) {
      if (events) events[st.t].push({ type, label, amount, refId });
    },
  };

  // running totals
  let receivablesOpen = 0;
  for (const inv of st.open) {
    receivablesOpen += inv.amount;
    if (stats) stats[inv.cust * STAT_WIDTH] += 1;
    if (stats && inv.dueDay <= H) stats[inv.cust * STAT_WIDTH + 3] += 1;
  }
  let payablesOpen = 0;
  for (const p of s.payables) payablesOpen += p.amount;
  let accrued = 0;
  let revenue = 0;
  let cogs = 0;
  let discountsGiven = 0;
  let lateFeeIncome = 0;
  let supplierDiscounts = 0;
  let operatingExpense = 0;
  let shockExpense = 0;
  let interestPaid = 0;
  let failed = false;
  let failDay = -1;
  // amounts booked today that a failure on the same day reverses (Addendum A1.1)
  let dayDiscounts = 0;
  let dayFees = 0;

  const creditDrawnTotal = () => {
    let x = 0;
    for (let i = 0; i < nLines; i++) x += st.drawn[i];
    return x;
  };

  const write = (day: number) => {
    const t = record ? day : 0;
    const profit =
      revenue -
      cogs -
      discountsGiven +
      lateFeeIncome +
      supplierDiscounts -
      st.collectionCosts -
      st.financingFees -
      operatingExpense -
      (interestPaid + accrued) -
      shockExpense;
    data[F.cash * W + t] = st.cash;
    data[F.creditDrawn * W + t] = creditDrawnTotal();
    data[F.accruedInterest * W + t] = accrued;
    data[F.receivablesOpen * W + t] = receivablesOpen;
    data[F.payablesOpen * W + t] = payablesOpen;
    data[F.revenue * W + t] = revenue;
    data[F.cogs * W + t] = cogs;
    data[F.discountsGiven * W + t] = discountsGiven;
    data[F.lateFeeIncome * W + t] = lateFeeIncome;
    data[F.supplierDiscounts * W + t] = supplierDiscounts;
    data[F.collectionCosts * W + t] = st.collectionCosts;
    data[F.operatingExpense * W + t] = operatingExpense;
    data[F.shockExpense * W + t] = shockExpense;
    data[F.interestPaid * W + t] = interestPaid;
    data[F.profit * W + t] = profit;
    data[F.financingOutstanding * W + t] = st.financingOutstanding;
    data[F.financingFees * W + t] = st.financingFees;
  };

  const takeLiquidity = () => {
    liqTaken = true;
    let headroom = 0;
    for (let i = 0; i < nLines; i++) headroom += lines[i].limit - st.drawn[i];
    liqSample = {
      liquidity: st.cash + headroom,
      inflows,
      outflows,
      collections: collectionsTotal,
      financingNet: financingNetTotal,
      actionCosts: actionCostsTotal,
    };
  };

  // Step 5: draw credit when cash < 0, repay when cash is above the repay level.
  const creditStep = (t: number) => {
    if (st.cash < 0) {
      for (let i = 0; i < nLines && st.cash < 0; i++) {
        const avail = lines[i].limit - st.drawn[i];
        if (avail <= 0) continue;
        const draw = Math.min(avail, -st.cash);
        st.drawn[i] += draw;
        st.cash += draw;
        st.emit("credit_draw", `Drew on ${lines[i].id}`, draw, lines[i].id);
      }
      if (st.cash < 0 && !failed) {
        failed = true;
        failDay = t;
        // A payment that causes failure earns no discount and no late fee (Addendum A1.1).
        if (dayDiscounts !== 0 || dayFees !== 0) {
          st.cash -= dayDiscounts + dayFees;
          supplierDiscounts -= dayDiscounts;
          lateFeeIncome -= dayFees;
          if (track && !liqTaken) {
            outflows += dayDiscounts;
            inflows -= dayFees;
            collectionsTotal -= dayFees;
          }
          dayDiscounts = 0;
          dayFees = 0;
        }
        st.emit("failure", "Cash below zero with every credit line fully drawn", st.cash, "");
      }
    } else if (st.cash > repayAbove) {
      let room = st.cash - repayAbove;
      for (let i = nLines - 1; i >= 0 && room > 0; i--) {
        const rep = Math.min(st.drawn[i], room);
        if (rep <= 0) continue;
        st.drawn[i] -= rep;
        st.cash -= rep;
        room -= rep;
        st.emit("credit_repay", `Repaid ${lines[i].id}`, rep, lines[i].id);
      }
    }
  };

  if (record) write(0);

  for (let t = 1; t <= H; t++) {
    st.t = t;
    if (failed) {
      if (!record) break; // state is frozen; the final write below stores it
      for (let f = 0; f < FIELDS.length; f++) data[f * W + t] = data[f * W + t - 1];
      continue;
    }
    dayDiscounts = 0;
    dayFees = 0;

    // 1. DECISIONS
    const chosen = path.byDay.get(t);
    if (chosen) {
      for (const c of chosen) applyAction(st, c.action, c.targetId, c.decisionId);
    }

    // 2. NEW INVOICES
    for (let c = 0; c < nCust; c++) {
      const cu = s.customers[c];
      if (st.churned[c] === 1) continue;
      if (t < cu.firstOrderDay || (t - cu.firstOrderDay) % cu.orderCycleDays !== 0) continue;
      const pm = st.priceMult[c];
      const vol = volumeMultiplier(elasticity, pm);
      let amount = 0;
      for (const o of cu.orders) amount += o.unitPrice * pm * o.qtyPerCycle * vol;
      if (amount > 0) {
        const id = `${cu.id}-INV-${t}`;
        insertSorted(st.open, {
          id,
          hash: prep.hash("pay:" + id),
          cust: c,
          amount,
          invoiceDay: t,
          dueDay: t + cu.dueDays,
          accepted: false,
          offerPayDay: 0,
          offerRate: 0,
          surv: 1,
          financed: false,
          advance: 0,
        });
        receivablesOpen += amount;
        revenue += amount;
        cogs += amount * (1 - gm);
        if (stats) {
          stats[c * STAT_WIDTH] += 1;
          if (t + cu.dueDays <= H) stats[c * STAT_WIDTH + 3] += 1;
        }
        st.emit("invoice", `Invoice ${id}`, amount, id);
      }
    }

    // 3. COLLECTIONS (invoice id order; skip invoices raised today)
    {
      let w = 0;
      for (let i = 0; i < st.open.length; i++) {
        const inv = st.open[i];
        let pay = false;
        if (inv.invoiceDay !== t) {
          if (inv.accepted) {
            pay = t === inv.offerPayDay;
          } else {
            const p = Math.min(0.95, prep.hazard[inv.cust] * st.mult[inv.cust]);
            if (det) {
              inv.surv *= 1 - p;
              pay = inv.surv <= 0.5;
            } else {
              pay = uniformHashed(seed, run, inv.hash, t) < p;
            }
          }
        }
        if (pay) {
          const cu = s.customers[inv.cust];
          let rate = 0;
          const d = cu.earlyPayDiscount;
          if (d !== null && t <= inv.invoiceDay + d.windowDays) rate = d.rate;
          if (inv.accepted && inv.offerRate > rate) rate = inv.offerRate;
          const principal = inv.amount * (1 - rate);
          const lr = st.lateRate[inv.cust];
          const fee =
            lr > 0
              ? (inv.amount * lr * Math.max(0, t - Math.max(inv.dueDay, st.lateStart[inv.cust]))) / 30
              : 0;
          // a financed invoice repays the financier's advance first
          const movement = principal + fee - (inv.financed ? inv.advance : 0);
          st.flow(movement, "collection");
          if (inv.financed) st.financingOutstanding -= inv.advance;
          discountsGiven += inv.amount - principal;
          lateFeeIncome += fee;
          dayFees += fee;
          receivablesOpen -= inv.amount;
          if (stats) {
            const o = inv.cust * STAT_WIDTH;
            stats[o + 1] += 1;
            stats[o + 2] += t - Math.max(inv.invoiceDay, 0);
            if (inv.dueDay <= H && t <= inv.dueDay) stats[o + 4] += 1;
          }
          st.emit("collection", `${cu.name} paid ${inv.id}`, movement, inv.id);
        } else {
          st.open[w++] = inv;
        }
      }
      st.open.length = w;
    }

    // 4. OUTFLOWS: payables, recurring costs, then (after measuring liquidity) shocks
    for (let i = 0; i < nPay; i++) {
      if (st.payPaid[i] === 1 || st.payDay[i] !== t) continue;
      const p = s.payables[i];
      const paid = st.payAmt[i];
      st.flow(-paid, "payable");
      supplierDiscounts += p.amount - paid;
      dayDiscounts += p.amount - paid;
      if (p.affectsProfit) operatingExpense += paid;
      payablesOpen -= p.amount;
      st.payPaid[i] = 1;
      st.emit("payable", `Paid ${p.label}`, paid, p.id);
    }
    for (const r of s.recurringCosts) {
      if (t >= r.firstDay && (t - r.firstDay) % r.repeatEveryDays === 0) {
        st.flow(-r.amount, "recurring");
        if (r.affectsProfit) operatingExpense += r.amount;
        st.emit("recurring", r.label, r.amount, r.id);
      }
    }
    if (track && !liqTaken && t === prep.liqDay) takeLiquidity();
    for (const k of s.shocks) {
      if (k.dueDay === t) {
        st.flow(-k.amount, "shock");
        if (k.affectsProfit) shockExpense += k.amount;
        st.emit("shock", k.label, k.amount, k.id);
      }
    }

    // 5. CREDIT
    creditStep(t);

    // 6. INTEREST
    for (let i = 0; i < nLines; i++) accrued += (st.drawn[i] * lines[i].ratePerMonth) / 30;
    if (t % 30 === 0 || t === H) {
      st.flow(-accrued, "interest");
      interestPaid += accrued;
      if (accrued > 0) st.emit("interest", "Interest charged", accrued, "");
      accrued = 0;
      if (st.cash < 0) creditStep(t);
    }

    // 7. SNAPSHOT
    if (record) write(t);
  }
  if (!record) write(H);
  // a run that failed before the shock day is measured in its frozen failure state
  if (track && !liqTaken) takeLiquidity();

  const churned: number[] = [];
  for (let c = 0; c < nCust; c++) if (st.churned[c] === 1) churned.push(c);

  return { H, W, data, failed, failDay, churned, events, liq: liqSample, stats };
}
