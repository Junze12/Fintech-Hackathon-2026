import { describe, expect, it } from "vitest";
import { validateScenario } from "../src/model/types";
import { analyse } from "../src/sim/analyse";
import { FORMULA_VARIABLES, parseFormula } from "../src/sim/formula";
import { loadNearEdge, quick, withFields } from "./helpers";

const ev = (src: string, vars: Record<string, number> = {}) => {
  const r = parseFormula(src);
  if (!r.ok) throw new Error(r.message);
  return r.evaluate(vars);
};

describe("formula parser", () => {
  it("evaluates arithmetic with precedence, brackets, unary minus and functions", () => {
    expect(ev("1 + 2 * 3")).toBe(7);
    expect(ev("(1 + 2) * 3")).toBe(9);
    expect(ev("-2 * -3")).toBe(6);
    expect(ev("10 / 4 - 1")).toBe(1.5);
    expect(ev("max(1, 5, 3) + min(4, 2) + abs(-7)")).toBe(14);
    expect(ev("1.5e2 + .5")).toBe(150.5);
  });
  it("reads variables", () => {
    expect(ev("economicProfit - 0.5 * churnCost", { economicProfit: 1000, churnCost: 200 })).toBe(900);
  });
  it("reports the used variables", () => {
    const r = parseFormula("profit - churnCost * 2 + profit");
    expect(r.ok && r.used.sort()).toEqual(["churnCost", "profit"]);
  });
  it("names the bad term in each kind of error", () => {
    const msg = (s: string) => {
      const r = parseFormula(s);
      return r.ok ? "ok" : r.message;
    };
    expect(msg("profitt + 1")).toMatch(/Unknown variable "profitt"/);
    expect(msg("sqrt(4)")).toMatch(/Unknown function "sqrt"/);
    expect(msg("max(1)")).toMatch(/max needs at least two/);
    expect(msg("abs(1, 2)")).toMatch(/abs takes exactly one/);
    expect(msg("(1 + 2")).toMatch(/Missing "\)"/);
    expect(msg("1 + ")).toMatch(/ends too early/);
    expect(msg("1 $ 2")).toMatch(/Unexpected character "\$" at position 3/);
    expect(msg("1 2")).toMatch(/Unexpected "2" at position 3/);
    expect(msg("")).toMatch(/empty/);
    expect(msg("* 3")).toMatch(/Unexpected "\*"/);
  });
  it("a score that cannot be calculated ranks last", () => {
    expect(ev("1 / 0")).toBe(-1e18);
    expect(ev("profit / endPayables", { profit: 5, endPayables: 0 })).toBe(-1e18);
  });
  it("every listed variable parses", () => {
    for (const v of FORMULA_VARIABLES) expect(parseFormula(v.name).ok).toBe(true);
  });
});

describe("objective.valueFormula in a scenario", () => {
  it("is refused at load with a message naming the bad term", () => {
    const raw = JSON.parse(JSON.stringify(loadNearEdge()));
    raw.objective.valueFormula = "economicProfit - nonsense";
    expect(() => validateScenario(raw)).toThrow(/objective\.valueFormula: Unknown variable "nonsense"/);
  });

  it("changes which plan wins among plans that meet the target; survival stays a hard rule", () => {
    const base = quick(loadNearEdge());
    const withFormula = withFields(base, (c) => (c.objective.valueFormula = "-(collectionCosts + churnCost + financingFees + discountsGiven)"));
    const a = analyse(withFormula, { deterministic: false, scenarioName: "t" });
    const cost = (p: (typeof a.paths)[number]) => p.metrics.collectionCosts + p.metrics.churnCost + p.metrics.financingFees + p.metrics.discountsGiven;
    const eligible = a.paths.filter((p) => p.metrics.survivalProb >= 0.95);
    expect(eligible.length).toBeGreaterThan(0);
    const best = a.paths[0];
    expect(best.metrics.survivalProb).toBeGreaterThanOrEqual(0.95);
    for (const p of eligible) expect(cost(best)).toBeLessThanOrEqual(cost(p) + 1.0 + 0.01);
    // default formula text behaves like no formula
    const same = analyse(withFields(base, (c) => (c.objective.valueFormula = "economicProfit")), { deterministic: false, scenarioName: "t" });
    const none = analyse(base, { deterministic: false, scenarioName: "t" });
    expect(same.bestPathId).toBe(none.bestPathId);
  });
});
