import { useState } from "react";
import type { Result, Scenario } from "../model/types";
import Comparison from "./Comparison";
import DecisionTree from "./DecisionTree";
import Timeline from "./Timeline";
import { pathOf, strategyOf } from "./answer";
import { SurvivalCurve, VerdictSummary } from "./VerdictBar";

interface Props {
  result: Result;
  scenario: Scenario;
  strategyId: string;
  pinnedPathId: string | null;
  onPin: (pathId: string | null) => void;
}

/** Everything from the old dashboard, collapsed by default. */
export default function Details({ result, scenario, strategyId, pinnedPathId, onPin }: Props) {
  const [open, setOpen] = useState(false);
  const sel = strategyOf(result, strategyId);
  return (
    <section className="details" aria-label="Details">
      <button
        type="button"
        className="details-toggle"
        aria-expanded={open}
        aria-controls="details-body"
        onClick={() => setOpen((o) => !o)}
      >
        Show details: full financials, decision tree, assumptions {open ? "▾" : "▸"}
      </button>
      {open ? (
        <div id="details-body" className="details-body">
          <VerdictSummary result={result} scenario={scenario} />
          <section className="subpanel" aria-labelledby="fin-title">
            <h3 id="fin-title" className="section-title">Financials: {sel.name} vs doing nothing</h3>
            <Comparison result={result} strategyId={strategyId} />
          </section>
          <Timeline result={result} scenario={scenario} pathId={pathOf(result, sel.pathId).id} pinnedPathId={pinnedPathId} />
          <DecisionTree result={result} scenario={scenario} pinnedPathId={pinnedPathId} onPin={onPin} />
          <SurvivalCurve result={result} scenario={scenario} />
        </div>
      ) : null}
    </section>
  );
}
