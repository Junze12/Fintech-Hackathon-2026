import sample from "../src/model/scenarios/hand-drawn.json";
import nearEdge from "../src/model/scenarios/shock-near-edge.json";
import { validateScenario, type Path, type Scenario } from "../src/model/types";
import { compilePath, prepare, simulate, traceValue, type Trace } from "../src/sim/engine";

export function loadSample(): Scenario {
  return validateScenario(JSON.parse(JSON.stringify(sample)));
}

export function loadNearEdge(): Scenario {
  return validateScenario(JSON.parse(JSON.stringify(nearEdge)));
}

export function withShock(s: Scenario, amount: number): Scenario {
  const c = JSON.parse(JSON.stringify(s)) as Scenario;
  c.shocks[0].amount = amount;
  return c;
}

export function defaultPath(s: Scenario): Path {
  const choices: Record<string, string[]> = {};
  for (const dp of s.decisionPoints) {
    choices[dp.id] = dp.kind === "single" ? [dp.options.find((o) => o.isDefault)!.actionId] : [];
  }
  return { id: "default", choices, isDefault: true };
}

export function pathWith(s: Scenario, over: Record<string, string[]>): Path {
  const p = defaultPath(s);
  return { id: "custom", choices: { ...p.choices, ...over }, isDefault: false };
}

export function run(
  s: Scenario,
  path: Path,
  runIdx = 0,
  deterministic = true,
  collectEvents = false,
): Trace {
  const prep = prepare(s);
  return simulate(prep, compilePath(prep, path), runIdx, { deterministic, record: true, collectEvents });
}

export { traceValue };

export function withFields(s: Scenario, fn: (c: Scenario) => void): Scenario {
  const c = JSON.parse(JSON.stringify(s)) as Scenario;
  fn(c);
  return c;
}

/** Small-run copy of a scenario, for tests that run the whole analysis. */
export function quick(s: Scenario, runs = 200): Scenario {
  return withFields(s, (c) => {
    c.meta.runsPerPath = runs;
    c.threshold.runsPerPath = runs;
  });
}
