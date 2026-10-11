import { describe, expect, it } from "vitest";
import { validateScenario } from "../src/model/types";
import { analyse } from "../src/sim/analyse";
import { compilePath, finalValue, prepare, simulate, traceValue } from "../src/sim/engine";
import { enumeratePaths } from "../src/sim/optimise";
import { defaultPath, loadNearEdge, loadSample, pathWith, quick, withFields } from "./helpers";

const c2 = (n: number) => Math.round(n * 100) / 100;
const NE = loadNearEdge();

describe("A1.1 a payment that causes failure earns no discount", () => {
  it("hand-drawn, S$26,000 shock due day 25: runs failing on day 45 book no supplier discount", () => {
    const s = withFields(loadSample(), (c) => {
      c.shocks[0].amount = 26000;
      c.shocks[0].announceDay = 20;
      c.shocks[0].dueDay = 25;
    });
    const prep = prepare(s);
    let failedOn45 = 0;
    for (const p of enumeratePaths(prep)) {
      const cp = compilePath(prep, p);
      for (let r = 0; r < 150; r++) {
        const tr = simulate(prep, cp, r, { deterministic: false, record: true, collectEvents: false });
        if (tr.failed && tr.failDay === 45) {
          failedOn45++;
          expect(finalValue(tr, "supplierDiscounts")).toBeLessThanOrEqual(1e-9);
        }
      }
    }
    expect(failedOn45).toBeGreaterThan(0); // the test would be vacuous otherwise
  });
});

describe("A1.2 shocks are cash events by default", () => {
  it("profit is identical with a S$0 or S$30,000 shock for a run that survives both and draws no credit", () => {
    const base = withFields(NE, (c) => (c.shocks[0].amount = 0));
    const big = withFields(NE, (c) => (c.shocks[0].amount = 30000));
    const pa = prepare(base), pb = prepare(big);
    const path = compilePath(pa, defaultPath(NE));
    let found = 0;
    for (let r = 0; r < 600; r++) {
      const a = simulate(pa, path, r, { deterministic: false, record: true, collectEvents: false });
      const b = simulate(pb, compilePath(pb, defaultPath(NE)), r, { deterministic: false, record: true, collectEvents: false });
      expect(finalValue(b, "shockExpense")).toBe(0);
      if (a.failed || b.failed) continue;
      let peak = 0;
      for (let d = 0; d <= b.H; d++) peak = Math.max(peak, traceValue(b, "creditDrawn", d));
      if (peak > 0) continue;
      found++;
      expect(finalValue(b, "profit")).toBeCloseTo(finalValue(a, "profit"), 6);
    }
    expect(found).toBeGreaterThan(0);
  });
  it("with affectsProfit: true the shock is booked as an expense", () => {
    const s = withFields(NE, (c) => (c.shocks[0].affectsProfit = true));
    const prep = prepare(s);
    const tr = simulate(prep, compilePath(prep, defaultPath(s)), 0, { deterministic: true, record: true, collectEvents: false });
    expect(finalValue(tr, "shockExpense")).toBe(30000);
  });
  it("the default is false when the field is omitted", () => {
    const raw = JSON.parse(JSON.stringify(NE));
    delete raw.shocks[0].affectsProfit;
    expect(validateScenario(raw).shocks[0].affectsProfit).toBe(false);
  });
});

describe("A1.3 ranking when no path meets the target", () => {
  it("every path has survival 0: the best path has the highest mean days survived", () => {
    const s = quick(loadSample(), 100); // S$30,000 shock: nothing survives
    const r = analyse(s, { deterministic: false, scenarioName: "t" });
    expect(r.paths.every((p) => p.metrics.survivalProb === 0)).toBe(true);
    const meanDays = (p: (typeof r.paths)[number]) => {
      let sum = 0, n = 0;
      for (const [day, count] of Object.entries(p.metrics.failDayHistogram)) { sum += Number(day) * count; n += count; }
      return sum / n;
    };
    const top = meanDays(r.paths[0]);
    for (const p of r.paths) expect(meanDays(p)).toBeLessThanOrEqual(top + 1e-9);
  });
});

describe("A2 invoice financing", () => {
  const path = pathWith(NE, { D4: ["finance_A"] });
  const prep = prepare(NE);
  const cp = compilePath(prep, path);

  it("advances S$6,160 net on the day applied and returns S$1,600 when the customer pays", () => {
    let checked = 0;
    for (let r = 0; r < 300 && checked === 0; r++) {
      const tr = simulate(prep, cp, r, { deterministic: false, record: true, collectEvents: true });
      const fin = tr.events!.flatMap((evs, d) => evs.filter((e) => e.type === "financing").map((e) => ({ d, e })));
      const pay = tr.events!.flatMap((evs, d) => evs.filter((e) => e.type === "collection" && e.refId === "AR-A1").map((e) => ({ d, e })));
      if (fin.length === 1 && pay.length === 1) {
        expect(fin[0].d).toBe(15);
        expect(c2(fin[0].e.amount)).toBe(6160);
        expect(c2(pay[0].e.amount)).toBe(1600);
        expect(c2(traceValue(tr, "financingOutstanding", 15))).toBe(6400);
        expect(c2(traceValue(tr, "financingFees", 15))).toBe(240);
        expect(c2(traceValue(tr, "financingOutstanding", pay[0].d))).toBe(0);
        checked++;
      }
    }
    expect(checked).toBe(1);
  });

  it("does nothing when the invoice is already paid", () => {
    for (let r = 0; r < 300; r++) {
      const tr = simulate(prep, cp, r, { deterministic: false, record: true, collectEvents: true });
      const paidBefore = tr.events!.slice(0, 15).some((evs) => evs.some((e) => e.type === "collection" && e.refId === "AR-A1"));
      if (paidBefore) {
        expect(tr.events!.flat().some((e) => e.type === "financing")).toBe(false);
        expect(finalValue(tr, "financingFees")).toBe(0);
        return;
      }
    }
    throw new Error("no run had Firm A pay before day 15");
  });

  it("the extended accounting identity holds every day in every run", () => {
    const paths = enumeratePaths(prep).filter((_, i) => i % 3 === 0);
    for (const p of paths) {
      const c = compilePath(prep, p);
      for (let r = 0; r < 40; r++) {
        const tr = simulate(prep, c, r, { deterministic: false, record: true, collectEvents: true });
        const net = (d: number) =>
          traceValue(tr, "cash", d) - traceValue(tr, "creditDrawn", d) - traceValue(tr, "accruedInterest", d) -
          traceValue(tr, "payablesOpen", d) - traceValue(tr, "financingOutstanding", d) + traceValue(tr, "receivablesOpen", d);
        const interest = (d: number) => traceValue(tr, "interestPaid", d) + traceValue(tr, "accruedInterest", d);
        const delta = (f: Parameters<typeof traceValue>[1], d: number) => traceValue(tr, f, d) - traceValue(tr, f, d - 1);
        for (let d = 1; d <= tr.H; d++) {
          const sum = (t: string) => tr.events![d].filter((e) => e.type === t).reduce((a, e) => a + e.amount, 0);
          const rhs = delta("revenue", d) - delta("discountsGiven", d) + delta("lateFeeIncome", d) + delta("supplierDiscounts", d) -
            delta("collectionCosts", d) - delta("financingFees", d) - (interest(d) - interest(d - 1)) - sum("recurring") - sum("shock");
          expect(Math.abs(net(d) - net(d - 1) - rhs)).toBeLessThan(0.01);
        }
      }
    }
  });
});

describe("A3 liquidity at the shock", () => {
  it("liquidity = cash0 + inflows - outflows + credit limits for every run", () => {
    for (const s of [NE, loadSample()]) {
      const prep = prepare(s);
      const C = s.creditLines.reduce((a, l) => a + l.limit, 0);
      for (const p of enumeratePaths(prep).filter((_, i) => i % 2 === 0)) {
        const cp = compilePath(prep, p);
        for (let r = 0; r < 60; r++) {
          const tr = simulate(prep, cp, r, { deterministic: false, record: false, collectEvents: false, track: true });
          const l = tr.liq!;
          expect(Math.abs(l.liquidity - (s.business.cash0 + l.inflows - l.outflows + C))).toBeLessThan(0.01);
        }
      }
    }
  });
  it("reports gap and spare against the shock amount; no inflows makes liquidity S$24,500 on the example", () => {
    const r = analyse(quick(NE, 200), { deterministic: false, scenarioName: "t" });
    const d = r.paths.find((p) => p.isDefault)!.liquidity;
    expect(d.safeLiquidity).toBe(24500);
    expect(d.gapAtShock).toBe(5500);
    expect(d.spareAtShock).toBe(0);
    expect(r.defaultGap.gapAtShock).toBe(5500);
    for (const p of r.paths) {
      expect(p.liquidity.gapAtShock * p.liquidity.spareAtShock).toBe(0);
      expect(p.liquidity.safeLiquidity).toBeLessThanOrEqual(p.liquidity.meanLiquidity + 1e-9);
    }
  });
});

describe("A4 strategies", () => {
  const bad = (fn: (raw: any) => void) => {
    const raw = JSON.parse(JSON.stringify(NE));
    fn(raw);
    return () => validateScenario(raw);
  };
  it("refuses an unknown option id, naming the strategy and decision point", () => {
    expect(bad((r) => (r.strategies[1].choices.D2 = ["nonsense"]))).toThrow(/strategies "S1", decision point "D2".*nonsense/);
  });
  it("refuses an unknown decision point", () => {
    expect(bad((r) => (r.strategies[1].choices.D9 = ["resend"]))).toThrow(/strategies "S1".*D9/);
  });
  it("refuses a single-choice point with two ids", () => {
    expect(bad((r) => (r.strategies[1].choices.D2 = ["resend", "late_fee"]))).toThrow(/strategies "S1", decision point "D2"/);
  });
  it("requires S0, and S0 must be the default path", () => {
    expect(bad((r) => (r.strategies = r.strategies.slice(1)))).toThrow(/S0/);
    expect(bad((r) => (r.strategies[0].choices = { D1: ["letter"] }))).toThrow(/strategies "S0".*default path/);
  });
  it("adds BEST only when the best path is not declared; exactly one strategy is recommended", () => {
    const r = analyse(quick(NE, 200), { deterministic: false, scenarioName: "t" });
    expect(r.strategies.filter((x) => x.isRecommended).length).toBe(1);
    const best = r.strategies.find((x) => x.isRecommended)!;
    expect(best.pathId).toBe(r.bestPathId);
    if (best.id === "BEST") expect(r.strategies[r.strategies.length - 1].id).toBe("BEST");
    expect(r.strategies.filter((x) => x.id === "BEST").length).toBeLessThanOrEqual(1);
    const s0 = r.strategies[0];
    expect(s0.id).toBe("S0");
    expect(s0.cost).toBe(0);
    expect(s0.pathId).toBe(r.defaultPathId);
    // a declared strategy that is the best path suppresses BEST
    const only = withFields(NE, (c) => {
      c.strategies = [c.strategies[0], { id: "S9", name: "Best by declaration", description: "", choices: { D1: ["resend"], D2: ["resend"], D3: ["resend"], D4: ["finance_A"] } }];
    });
    const r2 = analyse(quick(only, 200), { deterministic: false, scenarioName: "t" });
    expect(r2.strategies.some((x) => x.id === "BEST")).toBe(r2.bestPathId !== r2.strategies[1].pathId);
  });
});

describe("A5 shock-near-edge scenario", () => {
  const r = analyse(NE, { deterministic: false, scenarioName: "t" });
  const get = (id: string) => r.strategies.find((x) => x.id === id)!;
  it("has 108 paths", () => {
    expect(r.paths.length).toBe(108);
  });
  it("strategy survival falls in the expected bands (S0 35-60%, S1 55-80%, S2 85-97%, S3 >= 98%)", () => {
    expect(get("S0").survivalProb).toBeGreaterThanOrEqual(0.35);
    expect(get("S0").survivalProb).toBeLessThanOrEqual(0.6);
    expect(get("S1").survivalProb).toBeGreaterThanOrEqual(0.55);
    expect(get("S1").survivalProb).toBeLessThanOrEqual(0.8);
    expect(get("S2").survivalProb).toBeGreaterThanOrEqual(0.85);
    expect(get("S2").survivalProb).toBeLessThanOrEqual(0.97);
    expect(get("S3").survivalProb).toBeGreaterThanOrEqual(0.98);
  });
  it("default gap is about S$5,500 and S3 costs S$150-400", () => {
    expect(r.defaultGap.gapAtShock).toBeGreaterThan(5000);
    expect(r.defaultGap.gapAtShock).toBeLessThan(6000);
    expect(get("S3").cost).toBeGreaterThanOrEqual(150);
    expect(get("S3").cost).toBeLessThanOrEqual(400);
  });
  it("S2 costs mostly expected churn", () => {
    // A5 expects S$5,500-7,500 assuming the letter always applies. The agreed rule skips a
    // collection action when Firm A has already paid (about 21% of runs), which lowers it to about
    // S$5,300; the actual number is reported rather than the scenario or the rule being tuned.
    expect(get("S2").cost).toBeGreaterThan(5000);
    expect(get("S2").cost).toBeLessThan(7500);
    expect(get("S2").churnRisk[0]).toMatchObject({ customerId: "A" });
  });
});
