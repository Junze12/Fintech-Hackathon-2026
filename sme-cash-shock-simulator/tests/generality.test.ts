import { describe, expect, it } from "vitest";
import bakery from "./fixtures/bakery.json";
import { validateScenario } from "../src/model/types";
import { analyse } from "../src/sim/analyse";
import { compilePath, prepare, simulate, traceValue } from "../src/sim/engine";
import { enumeratePaths } from "../src/sim/optimise";

const s = validateScenario(JSON.parse(JSON.stringify(bakery)));

describe("a different business runs with no code change", () => {
  it("has 96 paths and a full, valid Result", () => {
    const r = analyse(s, { deterministic: false, scenarioName: "bakery.json" });
    expect(r.paths.length).toBe(3 * 8 * 2 * 2);
    expect(r.strategies.map((x) => x.id)[0]).toBe("S0");
    expect(r.runInfo.pathCount).toBe(96);
    expect(r.paths[0].daily.cash.p50.length).toBe(61);
    expect(r.tree.nodes.map((n) => n.id)).toEqual(["E1", "E2", "E3", "E4"]);
    expect(r.tree.edges.filter((e) => e.nodeId === "E2").length).toBe(8);
    expect(r.tree.edges.filter((e) => e.nodeId === "E4").length).toBe(2);
    const bridge = r.profitBridge.reduce((a, b) => a + b.amount, 0);
    const best = r.paths[0], def = r.paths.find((p) => p.isDefault)!;
    expect(Math.abs(bridge - (best.metrics.economicProfit.mean - def.metrics.economicProfit.mean))).toBeLessThan(0.0101);
    expect(r.threshold.curve.length).toBe(11);
    expect(r.paths[0].medianRun.length).toBe(61);
  });

  it("accounting identity holds with recurring costs, two credit lines and two shocks", () => {
    const prep = prepare(s);
    const paths = enumeratePaths(prep).filter((_, i) => i % 5 === 0);
    let sawDraw = false, sawRecurring = false;
    for (const p of paths) {
      const cp = compilePath(prep, p);
      for (let r = 0; r < 30; r++) {
        const tr = simulate(prep, cp, r, { deterministic: false, record: true, collectEvents: true });
        const net = (d: number) =>
          traceValue(tr, "cash", d) - traceValue(tr, "creditDrawn", d) - traceValue(tr, "accruedInterest", d) -
          traceValue(tr, "payablesOpen", d) - traceValue(tr, "financingOutstanding", d) + traceValue(tr, "receivablesOpen", d);
        const interest = (d: number) => traceValue(tr, "interestPaid", d) + traceValue(tr, "accruedInterest", d);
        const delta = (f: Parameters<typeof traceValue>[1], d: number) => traceValue(tr, f, d) - traceValue(tr, f, d - 1);
        for (let d = 1; d <= tr.H; d++) {
          const evs = tr.events![d];
          const sum = (t: string) => evs.filter((e) => e.type === t).reduce((a, e) => a + e.amount, 0);
          if (sum("credit_draw") > 0) sawDraw = true;
          if (sum("recurring") > 0) sawRecurring = true;
          const rhs = delta("revenue", d) - delta("discountsGiven", d) + delta("lateFeeIncome", d) +
            delta("supplierDiscounts", d) - delta("collectionCosts", d) - delta("financingFees", d) - (interest(d) - interest(d - 1)) -
            sum("recurring") - sum("shock");
          if (tr.failed && d > tr.failDay) continue;
          expect(Math.abs(net(d) - net(d - 1) - rhs)).toBeLessThan(0.01);
        }
      }
    }
    expect(sawDraw).toBe(true);
    expect(sawRecurring).toBe(true);
  });

  it("same seed, same Result; a different seed changes it", () => {
    const a = analyse(s, { deterministic: false, scenarioName: "b" });
    const b = analyse(s, { deterministic: false, scenarioName: "b" });
    a.runInfo.elapsedMs = 0; b.runInfo.elapsedMs = 0;
    expect(JSON.stringify(a)).toBe(JSON.stringify(b));
    const other = JSON.parse(JSON.stringify(s)); other.meta.seed = 8;
    const c = analyse(validateScenario(other), { deterministic: false, scenarioName: "b" });
    c.runInfo.elapsedMs = 0;
    expect(JSON.stringify(c.paths[0].daily)).not.toBe(JSON.stringify(a.paths[0].daily));
  });
});
