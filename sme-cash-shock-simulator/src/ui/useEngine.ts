import { useCallback, useEffect, useRef, useState } from "react";
import { ScenarioError, validateScenario, type Result, type Scenario } from "../model/types";
import type { Stage } from "../sim/analyse";
import type { WorkerRequest, WorkerResponse } from "../sim/worker";

export interface EngineState {
  result: Result | null;
  /** the scenario the current result was computed from (panels read this, not the edited draft) */
  ranScenario: Scenario | null;
  ranDeterministic: boolean;
  running: boolean;
  stage: Stage | null;
  pct: number;
  error: string | null;
}

const STAGE_ORDER: Stage[] = ["main", "shock_search", "buffer_search", "curve", "done"];
/** Overall progress, weighting the main run most (it is the longest stage). */
export function overallPct(stage: Stage | null, pct: number): number {
  if (stage === null) return 0;
  const weights = [0.55, 0.2, 0.15, 0.1];
  const i = STAGE_ORDER.indexOf(stage);
  if (stage === "done") return 100;
  let done = 0;
  for (let k = 0; k < i; k++) done += weights[k];
  return Math.round((done + (weights[i] * pct) / 100) * 100);
}

/**
 * Runs the engine in a worker when asked (`run`). The previous result stays on screen while a
 * new one is computed; an invalid scenario reports its error and does not run.
 */
export function useEngine() {
  const [state, setState] = useState<EngineState>({
    result: null,
    ranScenario: null,
    ranDeterministic: false,
    running: false,
    stage: null,
    pct: 0,
    error: null,
  });
  const workerRef = useRef<Worker | null>(null);
  const jobRef = useRef(0);

  const run = useCallback((scenario: Scenario, deterministic: boolean, scenarioName: string) => {
    let valid: Scenario;
    try {
      valid = validateScenario(scenario);
    } catch (e) {
      setState((s) => ({ ...s, running: false, error: e instanceof ScenarioError ? e.message : String(e) }));
      return;
    }
    workerRef.current?.terminate();
    const worker = new Worker(new URL("../sim/worker.ts", import.meta.url), { type: "module" });
    workerRef.current = worker;
    const id = ++jobRef.current;
    setState((s) => ({ ...s, running: true, stage: "main", pct: 0, error: null }));
    worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      const m = e.data;
      if (m.id !== jobRef.current) return;
      if (m.type === "progress") {
        setState((s) => ({ ...s, stage: m.stage, pct: m.pct }));
      } else if (m.type === "result") {
        setState({
          result: m.result,
          ranScenario: valid,
          ranDeterministic: deterministic,
          running: false,
          stage: "done",
          pct: 100,
          error: null,
        });
        worker.terminate();
      } else {
        setState((s) => ({ ...s, running: false, error: m.message }));
        worker.terminate();
      }
    };
    worker.onerror = (ev) => {
      setState((s) => ({ ...s, running: false, error: ev.message || "Engine worker failed" }));
    };
    const req: WorkerRequest = { type: "run", id, scenario: valid, deterministic, scenarioName };
    worker.postMessage(req);
  }, []);

  useEffect(
    () => () => {
      workerRef.current?.terminate();
    },
    [],
  );

  return { state, run };
}
