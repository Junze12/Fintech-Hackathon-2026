/// <reference lib="webworker" />
import { ScenarioError, validateScenario, type Result } from "../model/types";
import { analyse, type Stage } from "./analyse";

// Messages between the page and the engine worker. The worker takes a scenario as plain JSON
// and answers with the Result object (the JSON contract) so any client can drive it.

export type WorkerRequest = {
  type: "run";
  id: number;
  scenario: unknown;
  deterministic: boolean;
  scenarioName: string;
};

export type WorkerResponse =
  | { type: "progress"; id: number; stage: Stage; pct: number }
  | { type: "result"; id: number; result: Result }
  | { type: "error"; id: number; message: string };

const ctx = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const msg = e.data;
  if (msg.type !== "run") return;
  try {
    const scenario = validateScenario(msg.scenario);
    let lastPost = 0;
    const result = analyse(
      scenario,
      { deterministic: msg.deterministic, scenarioName: msg.scenarioName },
      (stage, pct) => {
        const now = Date.now();
        if (pct < 100 && now - lastPost < 40) return;
        lastPost = now;
        ctx.postMessage({ type: "progress", id: msg.id, stage, pct } satisfies WorkerResponse);
      },
    );
    ctx.postMessage({ type: "result", id: msg.id, result } satisfies WorkerResponse);
  } catch (err) {
    const message =
      err instanceof ScenarioError || err instanceof Error ? err.message : String(err);
    ctx.postMessage({ type: "error", id: msg.id, message } satisfies WorkerResponse);
  }
};
