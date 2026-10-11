import { describe, expect, it } from "vitest";
import { analyse } from "../src/sim/analyse";
import { ScenarioError, type Scenario } from "../src/model/types";
import { compilePath, prepare, simulate, traceValue, FIELDS } from "../src/sim/engine";
import {
  countPaths,
  enumeratePaths,
  frontierOf,
  nearestRank,
  pickBest,
  profitBridge,
  rankAll,
  subsetsOf,
  type Ranked,
} from "../src/sim/optimise";
import { defaultPath, loadSample, pathWith, withShock } from "./helpers";

function small(s: Scenario, runs = 100): Scenario {
  const c = JSON.parse(JSON.stringify(s)) as Scenario;
  c.meta.runsPerPath = runs;
  c.threshold.runsPerPath = runs;
  return c;
}

const R = (id: string, survivors: number, econ: number, endNet = 0, runs = 100, days = 0): Ranked => ({
  id, survivors, runs, survivalProb: survivors / runs, days, value: econ, econ, endNet,
});

describe("path enumeration", () => {
  it("example has exactly 192 paths with the specified id format", () => {
    const s = loadSample();
    expect(countPaths(s)).toBe(192);
    const paths = enumeratePaths(prepare(s));
    expect(paths.length).toBe(192);
    expect(new Set(paths.map((p) => p.id)).size).toBe(192);
    expect(paths.filter((p) => p.isDefault).map((p) => p.id)).toEqual([
      "D1:none|D2:none|D3:none|D4:pay_due",
    ]);
    expect(paths.some((p) => p.id === "D1:late_fee|D2:letter|D3:offer+price_cut|D4:pay_early")).toBe(true);
  });
  it("subsets: empty first, then by size, then listed order", () => {
    expect(subsetsOf(3)).toEqual([[], [0], [1], [2], [0, 1], [0, 2], [1, 2], [0, 1, 2]]);
  });
  it("refuses more than 5,000 paths and shows the count", () => {
    const s = loadSample();
    for (let i = 0; i < 3; i++) {
      const dp = JSON.parse(JSON.stringify(s.decisionPoints[2]));
      dp.id = `X${i}`;
      dp.order = 10 + i;
      s.decisionPoints.push(dp);
    }
    expect(() => enumeratePaths(prepare(s))).toThrow(ScenarioError);
    expect(() => enumeratePaths(prepare(s))).toThrow(new RegExp(String(countPaths(s))));
  });
});

describe("ranking", () => {
  it("picks highest profit among eligible; ties within tolerance go to survival, endNet, id", () => {
    const items = [R("a", 100, 10), R("b", 96, 500), R("c", 97, 500.5), R("d", 50, 9999)];
    expect(pickBest(items, 0.95, 1).id).toBe("c"); // b and c tie on profit; c survives more
    expect(pickBest([R("b", 96, 500, 5), R("a", 96, 500, 5)], 0.95, 1).id).toBe("a");
    expect(pickBest([R("b", 96, 500, 6), R("a", 96, 500, 5)], 0.95, 1).id).toBe("b");
  });
  it("with no eligible path picks highest survival, then days survived, profit, id (A1.3)", () => {
    const items = [R("a", 40, 100), R("b", 60, 5), R("c", 60, 7), R("d", 60, 7, 1)];
    expect(pickBest(items, 0.95, 1).id).toBe("c"); // b, c, d tie on survival and days; c wins on profit then id
    const byDays = [R("x", 0, 1000, 0, 100, 20), R("y", 0, -50, 0, 100, 41), R("z", 0, 9999, 0, 100, 30)];
    expect(pickBest(byDays, 0.95, 1).id).toBe("y");
  });
  it("rankAll orders eligible first, then by survival", () => {
    const items = [R("x", 10, 1000), R("y", 99, 1), R("z", 97, 5), R("w", 50, 9)];
    expect(rankAll(items, 0.95, 0).map((i) => i.id)).toEqual(["z", "y", "w", "x"]);
  });
  it("frontier keeps paths not beaten on both survival and profit", () => {
    const items = [R("a", 97, 800), R("b", 91, 1400), R("c", 90, 1000), R("d", 97, 800)];
    expect(frontierOf(items).map((i) => i.id).sort()).toEqual(["a", "b", "d"]);
  });
  it("nearest-rank percentiles", () => {
    const v = Float64Array.from({ length: 10 }, (_, i) => i + 1);
    expect(nearestRank(v, 10, 10)).toBe(1);
    expect(nearestRank(v, 10, 50)).toBe(5);
    expect(nearestRank(v, 10, 90)).toBe(9);
  });
  it("profit bridge sums exactly to the rounded difference", () => {
    const base = { survivalProb: 1, economicProfit: 100.004, profit: 0, endNetCash: 0, revenue: 0, grossProfit: 300.333,
      discountsGiven: 10.111, lateFeeIncome: 2.222, supplierDiscounts: 1.001, collectionCosts: 200.003, operatingExpense: 500.5,
      interestExpense: 0.333, financingFees: 12.347, financingOutstanding: 0, daysSurvived: 0, shockExpense: 0, churnCost: 0, peakCreditDrawn: 0, endReceivables: 0, endPayables: 0 };
    const other = { ...base, economicProfit: 5, grossProfit: 100.111, discountsGiven: 3.7 };
    const br = profitBridge(base, other);
    const sum = br.reduce((a, b) => a + b.amount, 0);
    expect(Math.abs(sum - Math.round((base.economicProfit - other.economicProfit) * 100) / 100)).toBeLessThan(0.0001);
    expect(br.length).toBe(10);
  });
});

describe("common random numbers and invariants", () => {
  const s = loadSample();
  const prep = prepare(s);
  const sim = (p: ReturnType<typeof pathWith>, r: number) =>
    simulate(prep, compilePath(prep, p), r, { deterministic: false, record: true, collectEvents: true });

  it("paths identical up to day d have identical snapshots up to day d-1", () => {
    for (let r = 0; r < 20; r++) {
      const a = sim(pathWith(s, { D3: ["offer"], D4: ["pay_early"] }), r);
      const b = sim(pathWith(s, { D3: ["letter", "price_cut"], D4: ["pay_due"] }), r);
      for (let d = 0; d <= 34; d++) for (const f of FIELDS) expect(traceValue(a, f, d)).toBe(traceValue(b, f, d));
      const c = sim(pathWith(s, { D1: ["letter"] }), r);
      const base = sim(defaultPath(s), r);
      for (let d = 0; d <= 9; d++) for (const f of FIELDS) expect(traceValue(c, f, d)).toBe(traceValue(base, f, d));
    }
  });

  it("no double collections or payments, no negatives, credit within limits", () => {
    const limit = s.creditLines.reduce((a, l) => a + l.limit, 0);
    const paths = enumeratePaths(prep).filter((_, i) => i % 7 === 0);
    for (const p of paths) {
      for (let r = 0; r < 15; r++) {
        const tr = sim(p, r);
        const coll = new Map<string, number>();
        const pay = new Map<string, number>();
        tr.events!.flat().forEach((e) => {
          if (e.type === "collection") coll.set(e.refId, (coll.get(e.refId) ?? 0) + 1);
          if (e.type === "payable") pay.set(e.refId, (pay.get(e.refId) ?? 0) + 1);
        });
        for (const n of coll.values()) expect(n).toBe(1);
        for (const n of pay.values()) expect(n).toBe(1);
        for (let d = 0; d <= tr.H; d++) {
          expect(traceValue(tr, "receivablesOpen", d)).toBeGreaterThan(-1e-9);
          expect(traceValue(tr, "payablesOpen", d)).toBeGreaterThan(-1e-9);
          expect(traceValue(tr, "creditDrawn", d)).toBeLessThanOrEqual(limit + 1e-9);
        }
      }
    }
  });

  it("a letter of demand on Firm A pays sooner on average and raises churn cost", () => {
    const s0 = withShock(s, 0);
    const prep0 = prepare(s0);
    const meanDay = (p: ReturnType<typeof pathWith>) => {
      let sum = 0, churned = 0;
      const n = 400;
      for (let r = 0; r < n; r++) {
        const tr = simulate(prep0, compilePath(prep0, p), r, { deterministic: false, record: true, collectEvents: true });
        let day = tr.H + 1;
        tr.events!.forEach((evs, d) => evs.forEach((e) => { if (e.type === "collection" && e.refId === "AR-A1") day = d; }));
        sum += day;
        if (tr.churned.includes(0)) churned++;
      }
      return { mean: sum / n, churned: churned / n };
    };
    const none = meanDay(defaultPath(s0));
    const letter = meanDay(pathWith(s0, { D1: ["letter"] }));
    expect(letter.mean).toBeLessThan(none.mean);
    expect(letter.churned).toBeGreaterThan(none.churned);
  });
});

describe("full analysis", () => {
  const s = small(loadSample());
  const a = analyse(s, { deterministic: false, scenarioName: "t" });

  it("is reproducible: same seed gives identical Result JSON (excluding elapsedMs)", () => {
    const b = analyse(s, { deterministic: false, scenarioName: "t" });
    a.runInfo.elapsedMs = 0;
    b.runInfo.elapsedMs = 0;
    expect(JSON.stringify(b)).toBe(JSON.stringify(a));
  });

  it("S$30,000 shock: every path has survivalProb 0 and a positive extra buffer", () => {
    expect(a.paths.length).toBe(192);
    for (const p of a.paths) expect(p.metrics.survivalProb).toBe(0);
    expect(a.bestMeetsTarget).toBe(false);
    expect(a.threshold.extraBufferForChosenShock).not.toBeNull();
    expect(a.threshold.extraBufferForChosenShock!).toBeGreaterThan(0);
  });

  it("bridge adds up to profit sacrificed; best is ranked first; tree is consistent", () => {
    const sum = a.profitBridge.reduce((x, y) => x + y.amount, 0);
    const best = a.paths[0], def = a.paths.find((p) => p.isDefault)!;
    expect(best.id).toBe(a.bestPathId);
    expect(Math.abs(sum - (best.metrics.economicProfit.mean - def.metrics.economicProfit.mean))).toBeLessThan(0.0101);
    expect(Math.abs(a.profitSacrificed + (best.metrics.economicProfit.mean - def.metrics.economicProfit.mean))).toBeLessThan(0.0101);
    expect(a.tree.nodes.map((n) => n.id)).toEqual(["D1", "D2", "D3", "D4"]);
    expect(a.tree.edges.filter((e) => e.nodeId === "D3").length).toBe(8);
    expect(a.tree.edges.filter((e) => e.onBestPath).length).toBe(4);
    const d3 = a.tree.edges.filter((e) => e.nodeId === "D3").map((e) => e.label);
    expect(d3).toContain("No action");
    expect(d3).toContain("10% off if paid in 2 days + Letter of demand + Cut prices 20%");
  });

  it("daily arrays have horizonDays + 1 entries and the median run has every day", () => {
    const p = a.paths[0];
    for (const k of Object.keys(p.daily) as (keyof typeof p.daily)[]) {
      expect(p.daily[k].p50.length).toBe(91);
      expect(p.daily[k].p10.length).toBe(91);
    }
    expect(p.medianRun.length).toBe(91);
    expect(p.medianRun[40].events.some((e) => e.type === "shock")).toBe(true);
  });

  it("deterministic mode runs once per path", () => {
    const d = analyse(s, { deterministic: true, scenarioName: "t" });
    expect(d.runInfo.deterministic).toBe(true);
    expect(d.runInfo.runsPerPath).toBe(1);
    for (const p of d.paths) expect([0, 1]).toContain(p.metrics.survivalProb);
  });
});

describe("threshold behaviour", () => {
  it("survival never rises as the shock rises and never falls as cash0 rises", () => {
    const s = small(loadSample());
    const a = analyse(s, { deterministic: false, scenarioName: "t" });
    const c = a.threshold.curve;
    for (let i = 1; i < c.length; i++) expect(c[i].survival).toBeLessThanOrEqual(c[i - 1].survival + 0.02);
    const seen: number[] = [];
    for (const cash0 of [15000, 20000, 25000, 30000]) {
      const t = small(loadSample());
      t.business.cash0 = cash0;
      t.shocks[0].amount = 18000;
      const r = analyse(t, { deterministic: false, scenarioName: "t" });
      seen.push(r.paths[0].metrics.survivalProb);
    }
    for (let i = 1; i < seen.length; i++) expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1] - 0.02);
  });

  it("largest survivable shock lies on the grid and survives while the next step does not", () => {
    const s = small(loadSample());
    const a = analyse(s, { deterministic: false, scenarioName: "t" });
    const th = a.threshold;
    expect(th.atLeast).toBe(false);
    expect(th.largestSurvivableShock! % 500).toBe(0);
    expect(th.survivalAtThreshold!).toBeGreaterThanOrEqual(0.95);
    expect(th.survivalAtNextStep!).toBeLessThan(0.95);
  });

  it("atLeast when even maxShock is survivable; null when nothing survives", () => {
    const easy = small(loadSample());
    easy.threshold.maxShock = 5000;
    easy.shocks[0].amount = 1000;
    const e = analyse(easy, { deterministic: false, scenarioName: "t" });
    expect(e.threshold.largestSurvivableShock).toBe(5000);
    expect(e.threshold.atLeast).toBe(true);
    expect(e.threshold.extraBufferForChosenShock).toBe(0);

    const doomed = small(loadSample());
    doomed.business.cash0 = 0;
    doomed.business.creditRepayAbove = 0;
    doomed.payables[0].dueDay = 1; // S$500 bill on day 1
    doomed.creditLines[0].limit = 100;
    doomed.shocks[0].amount = 0;
    const d = analyse(doomed, { deterministic: false, scenarioName: "t" });
    expect(d.threshold.largestSurvivableShock).toBeNull();
    expect(d.threshold.survivalAtThreshold).toBeNull();
  });
});
