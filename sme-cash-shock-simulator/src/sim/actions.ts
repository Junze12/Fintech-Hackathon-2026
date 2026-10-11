import {
  ALL_CUSTOMERS,
  ALL_OPEN_RECEIVABLES,
  type Action,
  type CollectionAction,
  type DiscountOfferAction,
  type InvoiceFinancingAction,
  type PayableTimingAction,
  type PriceChangeAction,
} from "../model/types";
import { betaMean, uniformHashed } from "./rng";
import type { RunState } from "./engine";

/**
 * Apply one action of a decision point to one target on the state's current day.
 * (spec: "Action types and decision points"). The effects last to the end of the horizon.
 */
export function applyAction(
  st: RunState,
  action: Action,
  targetId: string,
  decisionId: string,
): void {
  switch (action.type) {
    case "collection":
      return applyCollection(st, action, targetId, decisionId);
    case "discount_offer":
      return applyDiscountOffer(st, action, targetId, decisionId);
    case "price_change":
      return applyPriceChange(st, action, targetId);
    case "payable_timing":
      return applyPayableTiming(st, action, targetId);
    case "invoice_financing":
      return applyInvoiceFinancing(st, action, targetId);
  }
}

function hasOpenInvoice(st: RunState, cust: number): boolean {
  for (const inv of st.open) if (inv.cust === cust) return true;
  return false;
}

function applyCollection(
  st: RunState,
  a: CollectionAction,
  targetId: string,
  decisionId: string,
): void {
  const p = st.prep;
  const c = p.custIndex.get(targetId);
  if (c === undefined) return;
  // Settled or churned customers: the action does nothing (no cost, no draw).
  if (st.churned[c] === 1 || !hasOpenInvoice(st, c)) return;

  const t = st.t;
  st.mult[c] *= a.payProbMultiplier;
  if (a.lateFeeRatePerMonth > 0) {
    st.lateRate[c] = Math.max(st.lateRate[c], a.lateFeeRatePerMonth);
    if (Number.isNaN(st.lateStart[c])) st.lateStart[c] = t; // kept if already set
  }
  if (a.cashCost > 0) {
    st.flow(-a.cashCost, "action");
    st.collectionCosts += a.cashCost;
  }
  st.emit("decision", `${a.label} (${p.s.customers[c].name})`, a.cashCost, targetId);

  const cust = p.s.customers[c];
  const prob = cust.keyClient ? a.churnProbKeyClient : a.churnProb;
  const hit = st.deterministic
    ? prob >= 0.5
    : uniformHashed(p.seed, st.run, p.hash(`churn:${targetId}:${decisionId}`), t) < prob;
  if (hit) {
    st.churned[c] = 1;
    st.emit("churn", `${cust.name} churned`, 0, targetId);
  }
}

function applyDiscountOffer(
  st: RunState,
  a: DiscountOfferAction,
  targetId: string,
  decisionId: string,
): void {
  if (targetId !== ALL_OPEN_RECEIVABLES) return;
  const p = st.prep;
  const t = st.t;
  // st.open is kept in invoice id order.
  for (const inv of st.open) {
    if (inv.accepted) continue;
    const prob = p.acceptProb[inv.cust];
    const accepted = st.deterministic
      ? prob >= 0.5
      : uniformHashed(p.seed, st.run, p.hash(`accept:${inv.id}:${decisionId}`), t) < prob;
    if (accepted) {
      inv.accepted = true;
      inv.offerPayDay = t + a.payWithinDays;
      inv.offerRate = a.offerRate;
    }
  }
  st.emit("decision", a.label, 0, targetId);
}

function applyPriceChange(st: RunState, a: PriceChangeAction, targetId: string): void {
  const p = st.prep;
  if (targetId === ALL_CUSTOMERS) {
    for (let c = 0; c < p.s.customers.length; c++) {
      if (st.churned[c] === 0) st.priceMult[c] = a.priceMultiplier;
    }
  } else {
    const c = p.custIndex.get(targetId);
    if (c === undefined || st.churned[c] === 1) return;
    st.priceMult[c] = a.priceMultiplier;
  }
  st.emit("decision", a.label, 0, targetId);
}

function applyPayableTiming(st: RunState, a: PayableTimingAction, targetId: string): void {
  const p = st.prep;
  const i = p.payIndex.get(targetId);
  if (i === undefined || st.payPaid[i] === 1) return;
  const pay = p.s.payables[i];
  const d = pay.earlyPayDiscount;
  if (a.payEarly && d !== null && st.t <= d.byDay) {
    st.payDay[i] = d.byDay;
    st.payAmt[i] = pay.amount * (1 - d.rate);
  } else {
    st.payDay[i] = pay.dueDay;
    st.payAmt[i] = pay.amount;
  }
  st.emit("decision", `${a.label} (${pay.label})`, 0, targetId);
}

/**
 * Invoice financing (Addendum A2): an advance now against an open invoice, repaid first when
 * the customer pays. Does nothing if the invoice is paid, already financed or does not exist.
 */
function applyInvoiceFinancing(st: RunState, a: InvoiceFinancingAction, targetId: string): void {
  const inv = st.open.find((i) => i.id === targetId);
  if (inv === undefined || inv.financed) return;
  const advance = a.advanceRate * inv.amount;
  const fee = a.feeRate * inv.amount;
  st.flow(advance - fee, "financing");
  st.financingOutstanding += advance;
  st.financingFees += fee;
  inv.financed = true;
  inv.advance = advance;
  st.emit("financing", `Advance on ${inv.id}`, advance - fee, inv.id);
}

/** Volume multiplier for a price multiplier: max(0, 1 + elasticity * (1 - priceMult)). */
export function volumeMultiplier(elasticity: number, priceMult: number): number {
  return Math.max(0, 1 + elasticity * (1 - priceMult));
}

/** Probability that a customer accepts a discount offer (Beta prior mean). */
export function acceptanceProbability(alpha: number, beta: number): number {
  return betaMean(alpha, beta);
}
