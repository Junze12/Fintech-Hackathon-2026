import { useEffect, useId, useState } from "react";
import { DEFAULT_FORMULA, FORMULA_FUNCTIONS, FORMULA_VARIABLES, parseFormula } from "../sim/formula";

interface Props {
  value: string | undefined;
  onChange: (formula: string | undefined) => void;
}

/**
 * Edit the formula that scores plans which meet the survival target.
 * The survival target itself stays a hard rule, so a formula cannot trade survival for profit.
 */
export default function ObjectiveEditor({ value, onChange }: Props) {
  const id = useId();
  const [text, setText] = useState(value ?? DEFAULT_FORMULA);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setText(value ?? DEFAULT_FORMULA);
    setError(null);
  }, [value]);

  const edit = (t: string) => {
    setText(t);
    const r = parseFormula(t);
    if (!r.ok) {
      setError(r.message);
      return;
    }
    setError(null);
    onChange(t.trim() === DEFAULT_FORMULA ? undefined : t.trim());
  };

  return (
    <div className="objective">
      <div className="num">
        <label htmlFor={id}>Score for plans that meet the survival target</label>
        <input
          id={id}
          type="text"
          spellCheck={false}
          value={text}
          aria-invalid={error !== null}
          aria-describedby={`${id}-help`}
          className={error ? "invalid mono" : "mono"}
          onChange={(e) => edit(e.target.value)}
        />
        {error ? (
          <span className="field-error" role="alert">
            {error}
          </span>
        ) : null}
      </div>
      <p id={`${id}-help`} className="muted small-text">
        The plan with the highest score wins, but only among plans that reach the survival target. If none does, the
        most survivable plan is chosen instead. Scores use average values over the simulated runs.
      </p>
      <button type="button" className="btn" onClick={() => edit(DEFAULT_FORMULA)} disabled={value === undefined && text === DEFAULT_FORMULA}>
        Reset to default ({DEFAULT_FORMULA})
      </button>
      <details className="card-row">
        <summary>What can I write?</summary>
        <p className="small-text">
          Use numbers, the variables below, <code>+ - * /</code>, brackets, and the functions{" "}
          {FORMULA_FUNCTIONS.map((f) => (
            <code key={f}>{f}() </code>
          ))}
          . A score that cannot be calculated (for example a division by zero) ranks last.
        </p>
        <p className="small-text">
          Example: <code>economicProfit - 0.5 * churnCost</code> counts lost customers one and a half times.
        </p>
        <p className="small-text warn-text">
          Careful: economicProfit already includes discounts, fees and churn cost. Adding them again counts them twice.
        </p>
        <dl className="vars">
          {FORMULA_VARIABLES.map((v) => (
            <div key={v.name}>
              <dt>
                <code>{v.name}</code>
              </dt>
              <dd>{v.description}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}
