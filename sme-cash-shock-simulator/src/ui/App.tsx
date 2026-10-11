import { useEffect, useMemo, useState } from "react";
import { ScenarioError, validateScenario, type Scenario } from "../model/types";
import CashCompare from "./CashCompare";
import Controls, { type ScenarioChoice } from "./Controls";
import Details from "./Details";
import GapBridge from "./GapBridge";
import Headline from "./Headline";
import OptionsTable from "./OptionsTable";
import PaymentCard from "./PaymentCard";
import { recommended } from "./answer";
import { overallPct, useEngine } from "./useEngine";

// Every file in src/model/scenarios/ is offered in the scenario picker.
const files = import.meta.glob("../model/scenarios/*.json", { eager: true, import: "default" }) as Record<string, unknown>;

interface Entry {
  key: string;
  label: string;
  scenario: Scenario | null;
  error: string | null;
}

const ENTRIES: Entry[] = Object.entries(files)
  .map(([path, raw]) => {
    const key = path.split("/").pop()!;
    try {
      const scenario = validateScenario(raw);
      return { key, label: scenario.name ?? key, scenario, error: null };
    } catch (e) {
      return { key, label: key, scenario: null, error: `${key}: ${e instanceof ScenarioError ? e.message : String(e)}` };
    }
  })
  .sort((a, b) => a.key.localeCompare(b.key));

const DEFAULT_KEY = "shock-near-edge.json";
const LOADED_KEY = "__loaded";

function Skeleton({ title }: { title: string }) {
  return (
    <section className="panel" aria-busy="true" aria-label={`${title} (loading)`}>
      <h2>{title}</h2>
      <div className="skeleton" style={{ height: 24, width: "40%" }} />
      <div className="skeleton" style={{ height: 120, marginTop: 12 }} />
    </section>
  );
}

export default function App() {
  const initial = ENTRIES.find((e) => e.key === DEFAULT_KEY && e.scenario) ?? ENTRIES.find((e) => e.scenario)!;
  const [scenario, setScenario] = useState<Scenario>(initial.scenario!);
  const [selectedKey, setSelectedKey] = useState(initial.key);
  const [loaded, setLoaded] = useState<{ name: string; scenario: Scenario } | null>(null);
  const [scenarioName, setScenarioName] = useState(initial.label);
  const [deterministic, setDeterministic] = useState(false);
  const [pinned, setPinned] = useState<string | null>(null);
  const [chosen, setChosen] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);

  const { state: engine, run } = useEngine();
  const { result, ranScenario } = engine;

  // Run once on first load; afterwards only when the user asks (Run button, picking or loading a scenario).
  useEffect(() => {
    run(initial.scenario!, false, initial.label);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const validationError = useMemo(() => {
    try {
      validateScenario(scenario);
      return null;
    } catch (e) {
      return e instanceof ScenarioError ? e.message : String(e);
    }
  }, [scenario]);

  const stale = useMemo(
    () => ranScenario === null || deterministic !== engine.ranDeterministic || JSON.stringify(scenario) !== JSON.stringify(ranScenario),
    [scenario, ranScenario, deterministic, engine.ranDeterministic],
  );

  const choices: ScenarioChoice[] = [
    ...ENTRIES.filter((e) => e.scenario).map((e) => ({ key: e.key, label: e.label })),
    ...(loaded ? [{ key: LOADED_KEY, label: `Loaded file: ${loaded.name}` }] : []),
  ];

  const startWith = (s: Scenario, name: string) => {
    setScenario(s);
    setScenarioName(name);
    setPinned(null);
    setChosen("");
    setLoadError(null);
    run(s, deterministic, name);
  };

  const bannerErrors = [
    loadError,
    engine.error,
    ...ENTRIES.filter((e) => e.error).map((e) => e.error),
  ].filter((x): x is string => !!x);

  const shown = result && ranScenario ? { result, scenario: ranScenario } : null;
  const selectedId = shown
    ? shown.result.strategies.some((s) => s.id === chosen)
      ? chosen
      : recommended(shown.result).id
    : "";
  const pinnedId = shown && pinned && shown.result.paths.some((p) => p.id === pinned) ? pinned : null;
  const pct = overallPct(engine.stage, engine.pct);

  return (
    <div className="app">
      <header className="top">
        <p className="eyebrow">SME Cash Shock Simulator</p>
      </header>

      {bannerErrors.length > 0 ? (
        <div className="banner" role="alert">
          <span>{bannerErrors.join(" | ")}</span>
          {loadError ? (
            <button type="button" className="chip-x" onClick={() => setLoadError(null)} aria-label="Dismiss error">
              ×
            </button>
          ) : null}
        </div>
      ) : null}

      {engine.running ? (
        <div className="progress" role="progressbar" aria-label="Simulation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div className="progress-bar" style={{ width: `${pct}%` }} />
          <span className="progress-text">
            Simulating ({engine.stage?.replace("_", " ")}) {pct}%
          </span>
        </div>
      ) : null}

      <div className="layout">
        <main className={`results ${engine.running && shown ? "dim" : ""}`} aria-busy={engine.running}>
          {shown ? (
            <>
              <Headline result={shown.result} scenario={shown.scenario} />
              <GapBridge result={shown.result} scenario={shown.scenario} strategyId={selectedId} />
              <OptionsTable result={shown.result} scenario={shown.scenario} selectedId={selectedId} onSelect={setChosen} />
              <CashCompare result={shown.result} scenario={shown.scenario} strategyId={selectedId} />
              <PaymentCard result={shown.result} scenario={shown.scenario} strategyId={selectedId} />
              <Details result={shown.result} scenario={shown.scenario} strategyId={selectedId} pinnedPathId={pinnedId} onPin={setPinned} />
            </>
          ) : (
            <>
              <Skeleton title="Answer" />
              <Skeleton title="Cash you can reach" />
              <Skeleton title="Your options" />
            </>
          )}
        </main>
        <aside className="sidebar">
          <Controls
            scenario={scenario}
            onChange={setScenario}
            deterministic={deterministic}
            onDeterministic={setDeterministic}
            scenarioName={scenarioName}
            choices={choices}
            selectedKey={selectedKey}
            onPick={(key) => {
              setSelectedKey(key);
              if (key === LOADED_KEY && loaded) startWith(loaded.scenario, loaded.name);
              else {
                const e = ENTRIES.find((x) => x.key === key);
                if (e?.scenario) startWith(e.scenario, e.label);
              }
            }}
            onLoad={(s, fileName) => {
              setLoaded({ name: fileName, scenario: s });
              setSelectedKey(LOADED_KEY);
              startWith(s, s.name ?? fileName);
            }}
            onError={setLoadError}
            onRun={() => run(scenario, deterministic, scenarioName)}
            running={engine.running}
            stale={stale}
            validationError={validationError}
          />
        </aside>
      </div>
    </div>
  );
}
