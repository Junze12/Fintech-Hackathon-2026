import type { Result, Scenario } from "../model/types";
import { chosenShock } from "./answer";
import { COLORS, fmtMoney, fmtPct } from "./format";

interface Props {
  result: Result;
  scenario: Scenario;
  selectedId: string;
  onSelect: (id: string) => void;
}

function SurvivalBar({ p, target }: { p: number; target: number }) {
  const color = p >= target ? COLORS.profit : p >= 0.5 ? COLORS.credit : COLORS.shock;
  const word = p >= target ? "meets target" : p >= 0.5 ? "below target" : "likely to fail";
  return (
    <div className="surv">
      <span className="surv-num">{fmtPct(p)}</span>
      <div className="surv-track" role="img" aria-label={`${fmtPct(p)} chance of surviving, ${word}`}>
        <div className="surv-fill" style={{ width: `${p * 100}%`, background: color }} />
        <div className="surv-tick" style={{ left: `${target * 100}%` }} title={`Target ${fmtPct(target)}`} />
      </div>
    </div>
  );
}

/** One row per strategy; clicking (or pressing Enter on) a row selects it. */
export default function OptionsTable({ result, scenario, selectedId, onSelect }: Props) {
  const D = chosenShock(scenario).dueDay;
  const target = scenario.objective.survivalTarget;
  return (
    <section className="panel" aria-labelledby="options-title">
      <h2 id="options-title">Your options</h2>
      <div className="table-scroll">
        <table className="options">
          <thead>
            <tr>
              <th scope="col">Option</th>
              <th scope="col">Chance of surviving</th>
              <th scope="col">Cost vs doing nothing</th>
              <th scope="col">Still short on day {D}</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {result.strategies.map((st) => {
              const selected = st.id === selectedId;
              return (
                <tr
                  key={st.id}
                  className={selected ? "selected" : undefined}
                  aria-selected={selected}
                  onClick={() => onSelect(st.id)}
                >
                  <td>
                    <button type="button" className="row-btn" aria-pressed={selected} onClick={() => onSelect(st.id)}>
                      <span className="opt-name">{st.name}</span>
                      {st.isRecommended ? <span className="pill">Recommended</span> : null}
                      <span className="opt-desc">{st.description}</span>
                    </button>
                  </td>
                  <td>
                    <SurvivalBar p={st.survivalProb} target={target} />
                  </td>
                  <td>{st.id === "S0" ? "—" : st.cost < 0 ? `Gains ${fmtMoney(-st.cost)}` : fmtMoney(st.cost)}</td>
                  <td>
                    {st.gapAtShock > 0 ? (
                      <span style={{ color: COLORS.shock, fontWeight: 600 }}>{fmtMoney(st.gapAtShock)}</span>
                    ) : (
                      <span style={{ color: COLORS.profit, fontWeight: 600 }}>Covered</span>
                    )}
                  </td>
                  <td>
                    {st.churnRisk.length === 0
                      ? "None"
                      : st.churnRisk.map((c) => (
                          <div key={c.customerId}>
                            {fmtPct(c.prob)} chance of losing {c.customerName}
                          </div>
                        ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
