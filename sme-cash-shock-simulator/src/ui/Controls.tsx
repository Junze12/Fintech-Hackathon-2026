import { useEffect, useId, useRef, useState } from "react";
import { ScenarioError, validateScenario, type CollectionAction, type Scenario } from "../model/types";
import { fmtMoney } from "./format";
import ObjectiveEditor from "./ObjectiveEditor";

export interface ScenarioChoice {
  key: string;
  label: string;
}

interface Props {
  scenario: Scenario;
  onChange: (next: Scenario) => void;
  deterministic: boolean;
  onDeterministic: (v: boolean) => void;
  scenarioName: string;
  choices: ScenarioChoice[];
  selectedKey: string;
  onPick: (key: string) => void;
  onLoad: (s: Scenario, fileName: string) => void;
  onError: (message: string) => void;
  onRun: () => void;
  running: boolean;
  /** inputs changed since the last run */
  stale: boolean;
  /** why the current inputs cannot run, or null */
  validationError: string | null;
}

interface NumFieldProps {
  label: string;
  value: number;
  min?: number;
  max?: number;
  int?: boolean;
  gt?: number; // value must be strictly greater than this
  compact?: boolean;
  onCommit: (v: number) => void;
}

/** Number input that validates against the field's allowed range and only commits valid values. */
function NumField({ label, value, min, max, int, gt, compact, onCommit }: NumFieldProps) {
  const id = useId();
  const [text, setText] = useState(String(value));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setText(String(value));
    setError(null);
  }, [value]);

  const check = (t: string): string | null => {
    const n = Number(t);
    if (t.trim() === "" || !Number.isFinite(n)) return `${label}: enter a number`;
    if (int && !Number.isInteger(n)) return `${label}: must be a whole number`;
    if (gt !== undefined && !(n > gt)) return `${label}: must be greater than ${gt}`;
    if (min !== undefined && n < min) return `${label}: must be at least ${min}`;
    if (max !== undefined && n > max) return `${label}: must be at most ${max}`;
    return null;
  };

  return (
    <span className={compact ? "num compact" : "num"}>
      {compact ? null : <label htmlFor={id}>{label}</label>}
      <input
        id={id}
        type="text"
        inputMode="decimal"
        value={text}
        aria-label={compact ? label : undefined}
        aria-invalid={error !== null}
        aria-describedby={error ? `${id}-err` : undefined}
        className={error ? "invalid" : undefined}
        onChange={(e) => {
          const t = e.target.value;
          setText(t);
          const err = check(t);
          setError(err);
          if (err === null) onCommit(Number(t));
        }}
      />
      {error ? (
        <span id={`${id}-err`} className="field-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}

function TextField({ label, value, onCommit }: { label: string; value: string; onCommit: (v: string) => void }) {
  const id = useId();
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  const empty = text.trim() === "";
  return (
    <span className="num">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        value={text}
        aria-invalid={empty}
        className={empty ? "invalid" : undefined}
        onChange={(e) => {
          setText(e.target.value);
          if (e.target.value.trim() !== "") onCommit(e.target.value);
        }}
      />
      {empty ? (
        <span className="field-error" role="alert">
          {label}: cannot be empty
        </span>
      ) : null}
    </span>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
}) {
  const id = useId();
  return (
    <div className="slider">
      <label htmlFor={id}>
        {label}: <b>{format(value)}</b>
      </label>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format(value)}
      />
    </div>
  );
}

/** First id of the form prefix1, prefix2, ... not already used. */
function freshId(prefix: string, used: string[]): string {
  for (let n = 1; ; n++) if (!used.includes(`${prefix}${n}`)) return `${prefix}${n}`;
}

export default function Controls({
  scenario: s,
  onChange,
  deterministic,
  onDeterministic,
  scenarioName,
  choices,
  selectedKey,
  onPick,
  onLoad,
  onError,
  onRun,
  running,
  stale,
  validationError,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const H = s.meta.horizonDays;
  const update = (fn: (draft: Scenario) => void) => {
    const draft = JSON.parse(JSON.stringify(s)) as Scenario;
    fn(draft);
    onChange(draft);
  };
  const shockIdx = s.shocks.findIndex((k) => k.id === s.threshold.shockIdToScale);
  const shock = s.shocks[shockIdx];
  const collections = s.actions
    .map((a, i) => ({ a, i }))
    .filter((x): x is { a: CollectionAction; i: number } => x.a.type === "collection");

  const readFile = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text());
      onLoad(validateScenario(parsed), file.name);
    } catch (e) {
      onError(
        e instanceof ScenarioError
          ? `${file.name}: ${e.message}`
          : e instanceof SyntaxError
            ? `${file.name}: not valid JSON (${e.message})`
            : String(e),
      );
    }
  };

  const download = () => {
    const blob = new Blob([JSON.stringify(s, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = scenarioName.endsWith(".json") ? scenarioName : "scenario.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const shockOrderError =
    shock.announceDay > shock.dueDay ? `The shock must be announced on or before the day it is due (day ${shock.dueDay}).` : null;

  return (
    <section className="panel controls" aria-labelledby="p5-title">
      <h2 id="p5-title">Controls and assumptions</h2>

      <div className="run-box">
        <button type="button" className="btn primary" onClick={onRun} disabled={running || validationError !== null}>
          {running ? "Running…" : "Run simulator"}
        </button>
        {stale && !running ? <span className="stale">Inputs changed. Press Run to update the results.</span> : null}
        {validationError ? (
          <div className="field-error" role="alert">
            Cannot run: {validationError}
          </div>
        ) : null}
      </div>

      <div className="num">
        <label htmlFor="scenario-picker">Scenario</label>
        <select id="scenario-picker" value={selectedKey} onChange={(e) => onPick(e.target.value)}>
          {choices.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <p className="muted small-text">
        Showing: <b>{scenarioName}</b>. Edits wait for you to press Run.
      </p>

      <h3>Shock and cash</h3>
      <Slider
        label={`${shock.label}: amount`}
        value={shock.amount}
        min={0}
        max={s.threshold.maxShock}
        step={1000}
        format={(v) => fmtMoney(v)}
        onChange={(v) => update((d) => void (d.shocks[shockIdx].amount = v))}
      />
      <Slider
        label="Shock announced on day"
        value={shock.announceDay}
        min={1}
        max={H}
        step={1}
        format={(v) => String(v)}
        onChange={(v) => update((d) => void (d.shocks[shockIdx].announceDay = v))}
      />
      <Slider
        label="Shock due on day"
        value={shock.dueDay}
        min={1}
        max={H}
        step={1}
        format={(v) => String(v)}
        onChange={(v) => update((d) => void (d.shocks[shockIdx].dueDay = v))}
      />
      {shockOrderError ? (
        <div className="field-error" role="alert">
          {shockOrderError}
        </div>
      ) : null}
      <Slider
        label="Starting cash"
        value={s.business.cash0}
        min={0}
        max={200000}
        step={1000}
        format={(v) => fmtMoney(v)}
        onChange={(v) => update((d) => void (d.business.cash0 = v))}
      />

      <h3>Customers and revenue</h3>
      {s.customers.map((c, i) => (
        <details key={c.id} className="card-row">
          <summary>
            {c.name} <span className="muted">({c.orders.length} order line{c.orders.length === 1 ? "" : "s"})</span>
          </summary>
          <div className="fields two">
            <TextField label="Name" value={c.name} onCommit={(v) => update((d) => void (d.customers[i].name = v))} />
            <Check label="Key client" checked={c.keyClient} onChange={(v) => update((d) => void (d.customers[i].keyClient = v))} />
            <NumField label="Expected days to pay" value={c.meanDaysToPay} min={1} onCommit={(v) => update((d) => void (d.customers[i].meanDaysToPay = v))} />
            <NumField label="Invoice due after (days)" value={c.dueDays} min={0} int onCommit={(v) => update((d) => void (d.customers[i].dueDays = v))} />
            <NumField label="Order every (days)" value={c.orderCycleDays} min={1} int onCommit={(v) => update((d) => void (d.customers[i].orderCycleDays = v))} />
            <NumField label="First order on day" value={c.firstOrderDay} min={1} int onCommit={(v) => update((d) => void (d.customers[i].firstOrderDay = v))} />
            <NumField label="Offer acceptance α" value={c.offerAcceptance.alpha} gt={0} onCommit={(v) => update((d) => void (d.customers[i].offerAcceptance.alpha = v))} />
            <NumField label="Offer acceptance β" value={c.offerAcceptance.beta} gt={0} onCommit={(v) => update((d) => void (d.customers[i].offerAcceptance.beta = v))} />
          </div>
          <Check
            label="Early-payment discount"
            checked={c.earlyPayDiscount !== null}
            onChange={(on) => update((d) => void (d.customers[i].earlyPayDiscount = on ? { rate: 0.02, windowDays: 30 } : null))}
          />
          {c.earlyPayDiscount ? (
            <div className="fields two">
              <NumField label="Discount rate (0–1)" value={c.earlyPayDiscount.rate} min={0} max={1} onCommit={(v) => update((d) => void (d.customers[i].earlyPayDiscount!.rate = v))} />
              <NumField label="Window (days after invoice)" value={c.earlyPayDiscount.windowDays} min={0} int onCommit={(v) => update((d) => void (d.customers[i].earlyPayDiscount!.windowDays = v))} />
            </div>
          ) : null}

          <h4>Revenue: order lines each cycle</h4>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Unit price</th>
                  <th scope="col">Qty</th>
                  <th scope="col">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {c.orders.map((o, j) => (
                  <tr key={j}>
                    <td>
                      <input
                        aria-label={`${c.name} order line ${j + 1} item`}
                        className="text-in"
                        value={o.item}
                        onChange={(e) => update((d) => void (d.customers[i].orders[j].item = e.target.value))}
                      />
                    </td>
                    <td><NumField compact label={`${c.name} ${o.item} unit price`} value={o.unitPrice} min={0} onCommit={(v) => update((d) => void (d.customers[i].orders[j].unitPrice = v))} /></td>
                    <td><NumField compact label={`${c.name} ${o.item} quantity per cycle`} value={o.qtyPerCycle} min={0} onCommit={(v) => update((d) => void (d.customers[i].orders[j].qtyPerCycle = v))} /></td>
                    <td>
                      <button type="button" className="icon-btn" aria-label={`Remove ${o.item} from ${c.name}`} onClick={() => update((d) => void d.customers[i].orders.splice(j, 1))}>
                        ×
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="row">
            <button
              type="button"
              className="btn"
              onClick={() =>
                update((d) => void d.customers[i].orders.push({ item: "New item", unitPrice: 100, qtyPerCycle: 1 }))
              }
            >
              Add order line
            </button>
            <button type="button" className="btn danger" onClick={() => update((d) => void d.customers.splice(i, 1))}>
              Remove customer
            </button>
          </div>
        </details>
      ))}
      <div className="row">
        <button
          type="button"
          className="btn"
          onClick={() =>
            update((d) => {
              const id = freshId("C", d.customers.map((x) => x.id));
              d.customers.push({
                id,
                name: `New customer ${id}`,
                keyClient: false,
                meanDaysToPay: 30,
                dueDays: 30,
                earlyPayDiscount: null,
                offerAcceptance: { alpha: 1, beta: 1 },
                orderCycleDays: 30,
                firstOrderDay: 30,
                orders: [],
              });
            })
          }
        >
          Add customer
        </button>
      </div>

      <h3>Suppliers and bills</h3>
      {s.payables.map((p, i) => (
        <details key={p.id} className="card-row">
          <summary>
            {p.label} <span className="muted">({fmtMoney(p.amount)} due day {p.dueDay})</span>
          </summary>
          <div className="fields two">
            <TextField label="Name" value={p.label} onCommit={(v) => update((d) => void (d.payables[i].label = v))} />
            <NumField label="Amount (S$)" value={p.amount} gt={0} onCommit={(v) => update((d) => void (d.payables[i].amount = v))} />
            <NumField label="Due on day" value={p.dueDay} min={1} max={H} int onCommit={(v) => update((d) => void (d.payables[i].dueDay = v))} />
          </div>
          <Check label="Counts as an operating expense" checked={p.affectsProfit} onChange={(v) => update((d) => void (d.payables[i].affectsProfit = v))} />
          <Check
            label="Discount for paying early"
            checked={p.earlyPayDiscount !== null}
            onChange={(on) => update((d) => void (d.payables[i].earlyPayDiscount = on ? { rate: 0.05, byDay: Math.max(1, p.dueDay - 10) } : null))}
          />
          {p.earlyPayDiscount ? (
            <div className="fields two">
              <NumField label="Discount rate (0–1)" value={p.earlyPayDiscount.rate} min={0} max={1} onCommit={(v) => update((d) => void (d.payables[i].earlyPayDiscount!.rate = v))} />
              <NumField label="Pay by day" value={p.earlyPayDiscount.byDay} min={1} max={H} int onCommit={(v) => update((d) => void (d.payables[i].earlyPayDiscount!.byDay = v))} />
            </div>
          ) : null}
          <div className="row">
            <button type="button" className="btn danger" onClick={() => update((d) => void d.payables.splice(i, 1))}>
              Remove bill
            </button>
          </div>
        </details>
      ))}
      <div className="row">
        <button
          type="button"
          className="btn"
          onClick={() =>
            update((d) => {
              const id = freshId("AP-", d.payables.map((x) => x.id));
              d.payables.push({
                id,
                label: `New bill ${id}`,
                amount: 1000,
                dueDay: Math.min(H, 30),
                affectsProfit: true,
                earlyPayDiscount: null,
              });
            })
          }
        >
          Add supplier bill
        </button>
      </div>

      <h3>Collection actions</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Action</th>
              <th scope="col">Pay × </th>
              <th scope="col">Cost</th>
              <th scope="col">Late fee/mo</th>
              <th scope="col">Churn</th>
              <th scope="col">Churn (key)</th>
            </tr>
          </thead>
          <tbody>
            {collections.map(({ a, i }) => (
              <tr key={a.id}>
                <th scope="row">{a.label}</th>
                <td><NumField compact label={`${a.label} pay probability multiplier`} value={a.payProbMultiplier} min={0} onCommit={(v) => update((d) => void ((d.actions[i] as CollectionAction).payProbMultiplier = v))} /></td>
                <td><NumField compact label={`${a.label} cash cost`} value={a.cashCost} min={0} onCommit={(v) => update((d) => void ((d.actions[i] as CollectionAction).cashCost = v))} /></td>
                <td><NumField compact label={`${a.label} late fee rate per month`} value={a.lateFeeRatePerMonth} min={0} onCommit={(v) => update((d) => void ((d.actions[i] as CollectionAction).lateFeeRatePerMonth = v))} /></td>
                <td><NumField compact label={`${a.label} churn probability`} value={a.churnProb} min={0} max={1} onCommit={(v) => update((d) => void ((d.actions[i] as CollectionAction).churnProb = v))} /></td>
                <td><NumField compact label={`${a.label} churn probability, key client`} value={a.churnProbKeyClient} min={0} max={1} onCommit={(v) => update((d) => void ((d.actions[i] as CollectionAction).churnProbKeyClient = v))} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Business</h3>
      <div className="fields">
        <NumField label="Gross margin (0–1)" value={s.business.grossMargin} min={0} max={1} onCommit={(v) => update((d) => void (d.business.grossMargin = v))} />
        <NumField label="Price elasticity" value={s.priceElasticity} min={0} onCommit={(v) => update((d) => void (d.priceElasticity = v))} />
        <NumField label="Repay credit above (S$)" value={s.business.creditRepayAbove} min={0} onCommit={(v) => update((d) => void (d.business.creditRepayAbove = v))} />
      </div>

      <h3>Objective</h3>
      <div className="fields">
        <NumField label="Survival target (0–1)" value={s.objective.survivalTarget} min={0} max={1} onCommit={(v) => update((d) => void (d.objective.survivalTarget = v))} />
        <NumField label="Churn months after end" value={s.objective.churnHorizonMonthsAfterEnd} min={0} onCommit={(v) => update((d) => void (d.objective.churnHorizonMonthsAfterEnd = v))} />
      </div>
      <ObjectiveEditor
        value={s.objective.valueFormula}
        onChange={(f: string | undefined) =>
          update((d) => {
            if (f === undefined) delete d.objective.valueFormula;
            else d.objective.valueFormula = f;
          })
        }
      />

      <h3>Mode and files</h3>
      <Check label="Deterministic (one fixed-rule run per plan)" checked={deterministic} onChange={onDeterministic} />
      <div className="row">
        <button type="button" className="btn" onClick={() => fileRef.current?.click()}>
          Load scenario JSON
        </button>
        <button type="button" className="btn" onClick={download}>
          Download scenario JSON
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) void readFile(f);
          }}
        />
      </div>
    </section>
  );
}
