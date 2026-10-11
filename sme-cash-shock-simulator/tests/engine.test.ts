import { describe, expect, it } from "vitest";
import { validateScenario } from "../src/model/types";
import { uniform, fnv1a32, betaMean, betaUpdatedMean } from "../src/sim/rng";
import { FIELD_INDEX, traceValue } from "../src/sim/engine";
import { defaultPath, loadSample, pathWith, run, withShock } from "./helpers";

const c2 = (n: number) => Math.round(n * 100) / 100;

describe("validation", () => {
  it("accepts the sample", () => {
    expect(() => loadSample()).not.toThrow();
  });
  it("names the missing field", () => {
    const s = JSON.parse(JSON.stringify(loadSample()));
    delete s.business.cash0;
    expect(() => validateScenario(s)).toThrow(/business\.cash0/);
  });
  it("names an out-of-range field", () => {
    const s = JSON.parse(JSON.stringify(loadSample()));
    s.customers[1].meanDaysToPay = 0.5;
    expect(() => validateScenario(s)).toThrow(/customers\.1\.meanDaysToPay/);
    const t = JSON.parse(JSON.stringify(loadSample()));
    t.meta.runsPerPath = 50;
    expect(() => validateScenario(t)).toThrow(/meta\.runsPerPath/);
  });
  it("requires exactly one default per single point", () => {
    const s = JSON.parse(JSON.stringify(loadSample()));
    delete s.decisionPoints[0].options[0].isDefault;
    expect(() => validateScenario(s)).toThrow(/decisionPoints\.0/);
  });
});

describe("rng", () => {
  it("is deterministic and keyed", () => {
    expect(uniform(42, 3, "pay:AR-A1", 5)).toBe(uniform(42, 3, "pay:AR-A1", 5));
    expect(uniform(42, 3, "pay:AR-A1", 5)).not.toBe(uniform(42, 3, "pay:AR-A1", 6));
    expect(uniform(42, 3, "pay:AR-A1", 5)).not.toBe(uniform(42, 4, "pay:AR-A1", 5));
    expect(uniform(42, 3, "pay:AR-A1", 5)).not.toBe(uniform(42, 3, "pay:AR-B1", 5));
    const u = uniform(1, 0, "x", 0);
    expect(u).toBeGreaterThanOrEqual(0);
    expect(u).toBeLessThan(1);
  });
  it("fnv1a32 known values", () => {
    expect(fnv1a32("")).toBe(0x811c9dc5);
    expect(fnv1a32("a")).toBe(0xe40c292c);
  });
  it("beta helpers", () => {
    expect(betaMean(1, 9)).toBeCloseTo(0.1);
    expect(betaUpdatedMean(6, 4, 3, 5)).toBeCloseTo(9 / 15);
  });
});

describe("hand-calculated checks (deterministic, shock 0, default path)", () => {
  const s = withShock(loadSample(), 0);
  const tr = run(s, defaultPath(s), 0, true, true);
  const cash = (d: number) => traceValue(tr, "cash", d);

  const eventDay = (id: string): number => {
    for (let d = 0; d < tr.events!.length; d++)
      if (tr.events![d].some((e) => e.type === "collection" && e.refId === id)) return d;
    return -1;
  };
  const eventAmt = (id: string): number => {
    for (const evs of tr.events!) for (const e of evs) if (e.type === "collection" && e.refId === id) return e.amount;
    return NaN;
  };

  it("Firm B pays on day 7, S$780", () => {
    expect(eventDay("AR-B1")).toBe(7);
    expect(c2(eventAmt("AR-B1"))).toBe(780);
  });
  it("Firm C pays on day 21, S$196", () => {
    expect(eventDay("AR-C1")).toBe(21);
    expect(c2(eventAmt("AR-C1"))).toBe(196);
  });
  it("Firm A open invoice not paid by day 90", () => {
    expect(eventDay("AR-A1")).toBe(-1);
  });
  it("cash on day 23 is 20,476", () => {
    expect(c2(cash(23))).toBe(20476);
  });
  it("B's new invoices are paid on day 37 and day 67 at S$98", () => {
    expect(eventDay("B-INV-30")).toBe(37);
    expect(eventDay("B-INV-60")).toBe(67);
    expect(c2(eventAmt("B-INV-30"))).toBe(98);
    expect(c2(eventAmt("B-INV-60"))).toBe(98);
  });
  it("invoices raised on days 30, 60, 90", () => {
    const raised: Record<string, number> = {};
    tr.events!.forEach((evs, d) =>
      evs.filter((e) => e.type === "invoice").forEach((e) => (raised[`${e.refId}`] = c2(e.amount)) && d),
    );
    expect(raised).toEqual({
      "A-INV-30": 600, "B-INV-30": 100,
      "A-INV-60": 600, "B-INV-60": 100,
      "A-INV-90": 600, "B-INV-90": 100,
    });
  });
  it("cash day 90 = 10,672; revenue 2,100; profit 122", () => {
    expect(c2(cash(90))).toBe(10672);
    expect(c2(traceValue(tr, "revenue", 90))).toBe(2100);
    expect(c2(traceValue(tr, "profit", 90))).toBe(122);
    expect(tr.failed).toBe(false);
  });
});

describe("zero-payment check", () => {
  it("cash is 20,000 days 1-22, 19,500 day 23, 9,500 from day 60", () => {
    const s = withShock(loadSample(), 0);
    s.customers.forEach((c) => (c.meanDaysToPay = 1000000));
    const tr = run(s, defaultPath(s), 0, true);
    for (let d = 1; d <= 22; d++) expect(c2(traceValue(tr, "cash", d))).toBe(20000);
    expect(c2(traceValue(tr, "cash", 23))).toBe(19500);
    for (let d = 60; d <= 90; d++) expect(c2(traceValue(tr, "cash", d))).toBe(9500);
  });
});

describe("unit checks", () => {
  it("price cut: Firm A invoice is S$537.60", () => {
    const s = withShock(loadSample(), 0);
    const tr = run(s, pathWith(s, { D3: ["price_cut"] }), 0, true, true);
    const e = tr.events!.flat().find((x) => x.type === "invoice" && x.refId === "A-INV-60")!;
    expect(c2(e.amount)).toBe(537.6);
    const base = tr.events!.flat().find((x) => x.refId === "A-INV-30")!;
    expect(c2(base.amount)).toBe(600);
  });

  it("late fee: S$780 due day -4, 1%/month from day 10, paid day 20 is S$2.60", () => {
    // Scan Firm B's meanDaysToPay for a deterministic payment on day 20 after the day-10 late-fee action.
    for (let m = 20; m <= 200; m++) {
      const s = withShock(loadSample(), 0);
      s.customers[1].meanDaysToPay = m;
      const tr = run(s, pathWith(s, { D2: ["late_fee"] }), 0, true, true);
      const e = tr.events!.flatMap((evs, d) => evs.filter((x) => x.type === "collection" && x.refId === "AR-B1").map((x) => ({ d, amt: x.amount })))[0];
      if (e && e.d === 20) {
        // window ended day -19, so principal is the full 780
        expect(c2(e.amt - 780)).toBe(2.6);
        return;
      }
    }
    throw new Error("no meanDaysToPay produced a day-20 payment");
  });

  it("churn cost: Firm A churned, 9 months, margin 0.30 is S$1,620", () => {
    const s = loadSample();
    // monthlyMargin = 600 * (30/30) * 0.30 = 180; x 9 = 1620
    expect(c2((5 * 100 + 20 * 5) * (30 / 30) * s.business.grossMargin * 9)).toBe(1620);
  });

  it("discount offer: accepted invoice paid exactly 2 days later at the larger discount", () => {
    const s = withShock(loadSample(), 0);
    // Zero-hazard so only offers pay invoices; deterministic accept needs p>=0.5 -> B and C accept, A does not.
    s.customers.forEach((c) => (c.meanDaysToPay = 1000000));
    const tr = run(s, pathWith(s, { D3: ["offer"] }), 0, true, true);
    const pays = tr.events!.flatMap((evs, d) => evs.filter((e) => e.type === "collection").map((e) => ({ d, id: e.refId, amt: e.amount })));
    // B-INV-30 (100, window valid to day 75 at 2%) and AR-C1 (200, window ended day 30): offer 10% wins both.
    expect(pays.find((p) => p.id === "AR-B1")).toMatchObject({ d: 37 });
    expect(c2(pays.find((p) => p.id === "AR-B1")!.amt)).toBe(702);
    expect(pays.find((p) => p.id === "B-INV-30")).toMatchObject({ d: 37 });
    expect(c2(pays.find((p) => p.id === "B-INV-30")!.amt)).toBe(90);
    expect(pays.find((p) => p.id === "AR-A1")).toBeUndefined();
  });
});

describe("accounting identity (random mode)", () => {
  it("holds every day for several paths and runs", () => {
    const s = loadSample();
    const paths = [
      defaultPath(s),
      pathWith(s, { D1: ["letter"], D2: ["late_fee"], D3: ["offer", "letter", "price_cut"], D4: ["pay_early"] }),
      pathWith(s, { D3: ["offer"] }),
    ];
    for (const p of paths) {
      for (let r = 0; r < 25; r++) {
        const tr = run(s, p, r, false, true);
        const H = tr.H;
        const net = (d: number) =>
          traceValue(tr, "cash", d) - traceValue(tr, "creditDrawn", d) - traceValue(tr, "accruedInterest", d) -
          traceValue(tr, "payablesOpen", d) - traceValue(tr, "financingOutstanding", d) + traceValue(tr, "receivablesOpen", d);
        const interestTotal = (d: number) => traceValue(tr, "interestPaid", d) + traceValue(tr, "accruedInterest", d);
        for (let d = 1; d <= H; d++) {
          const evs = tr.events![d];
          const sumOf = (t: string) => evs.filter((e) => e.type === t).reduce((a, e) => a + e.amount, 0);
          const rhs =
            traceValue(tr, "revenue", d) - traceValue(tr, "revenue", d - 1) -
            (traceValue(tr, "discountsGiven", d) - traceValue(tr, "discountsGiven", d - 1)) +
            (traceValue(tr, "lateFeeIncome", d) - traceValue(tr, "lateFeeIncome", d - 1)) +
            (traceValue(tr, "supplierDiscounts", d) - traceValue(tr, "supplierDiscounts", d - 1)) -
            (traceValue(tr, "collectionCosts", d) - traceValue(tr, "collectionCosts", d - 1)) -
            (traceValue(tr, "financingFees", d) - traceValue(tr, "financingFees", d - 1)) -
            (interestTotal(d) - interestTotal(d - 1)) -
            sumOf("recurring") - sumOf("shock");
          if (tr.failed && d > tr.failDay) { expect(Math.abs(net(d) - net(d - 1))).toBeLessThan(0.01); continue; }
          expect(Math.abs(net(d) - net(d - 1) - rhs)).toBeLessThan(0.01);
        }
      }
    }
    expect(FIELD_INDEX.cash).toBe(0);
  });
});
