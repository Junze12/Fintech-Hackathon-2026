import { describe, expect, it } from "vitest";
import type { WorkerRequest, WorkerResponse } from "../src/sim/worker";
import { loadSample } from "./helpers";

describe("worker protocol", () => {
  it("answers a run request with progress then the Result JSON, and reports bad fields", async () => {
    const out: WorkerResponse[] = [];
    const g = globalThis as unknown as Record<string, unknown>;
    g.self = { postMessage: (m: WorkerResponse) => out.push(m), onmessage: null };
    await import("../src/sim/worker");
    const self_ = g.self as { onmessage: (e: { data: WorkerRequest }) => void };

    const s = loadSample();
    s.meta.runsPerPath = 100;
    s.threshold.runsPerPath = 100;
    self_.onmessage({ data: { type: "run", id: 7, scenario: s, deterministic: false, scenarioName: "w" } });
    const stages = out.filter((m) => m.type === "progress").map((m) => (m as { stage: string }).stage);
    for (const st of ["main", "shock_search", "buffer_search", "curve", "done"]) expect(stages).toContain(st);
    const done = out.find((m) => m.type === "result") as Extract<WorkerResponse, { type: "result" }>;
    expect(done.id).toBe(7);
    expect(done.result.scenarioName).toBe("w");
    expect(JSON.parse(JSON.stringify(done.result)).paths.length).toBe(192);

    out.length = 0;
    const bad = JSON.parse(JSON.stringify(s));
    delete bad.business.grossMargin;
    self_.onmessage({ data: { type: "run", id: 8, scenario: bad, deterministic: false, scenarioName: "w" } });
    expect(out).toHaveLength(1);
    expect(out[0]).toMatchObject({ type: "error", id: 8 });
    expect((out[0] as { message: string }).message).toMatch(/business\.grossMargin/);
  });
});
