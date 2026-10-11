import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { Result, Scenario } from "../model/types";
import { COLORS, fmtMoney, fmtPct, Money } from "./format";
import { planSentence } from "../model/plan";

interface Props {
  result: Result;
  scenario: Scenario;
}

function Tile({ label, children, sub }: { label: string; children: React.ReactNode; sub?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{children}</div>
      {sub ? <div className="tile-sub">{sub}</div> : null}
    </div>
  );
}

export function VerdictSummary({ result, scenario }: Props) {
  const best = result.paths.find((p) => p.id === result.bestPathId)!;
  const p = best.metrics.survivalProb;
  const target = scenario.objective.survivalTarget;
  const th = result.threshold;
  const shock = scenario.shocks.find((k) => k.id === scenario.threshold.shockIdToScale)!;

  const badge =
    p >= target
      ? { cls: "ok", text: `Survives — ${fmtPct(p)} of runs survive` }
      : p >= 0.5
        ? { cls: "warn", text: `At risk — ${fmtPct(p)} of runs survive` }
        : { cls: "bad", text: `Fails — ${fmtPct(p)} of runs survive` };

  const largest =
    th.largestSurvivableShock === null
      ? "None"
      : `${th.atLeast ? "≥ " : ""}${fmtMoney(th.largestSurvivableShock)}`;
  const largestSub =
    th.survivalAtThreshold === null
      ? "Target not met even with no shock"
      : `Survival there ${fmtPct(th.survivalAtThreshold)}` +
        (th.survivalAtNextStep === null
          ? ""
          : `; one step higher ${fmtPct(th.survivalAtNextStep)}`);
  const buffer =
    th.extraBufferForChosenShock === null
      ? `More than ${fmtMoney(scenario.threshold.maxExtraBuffer)}`
      : fmtMoney(th.extraBufferForChosenShock);

  return (
    <section className="subpanel" aria-labelledby="p1-title">
      <h3 id="p1-title" className="section-title">Verdict at a glance</h3>
      <div className="verdict-head">
        <span className={`badge ${badge.cls}`} role="status">
          <span aria-hidden="true">{badge.cls === "ok" ? "✔" : badge.cls === "warn" ? "▲" : "✖"}</span>{" "}
          {badge.text}
        </span>
        <span className="muted">
          Chosen shock: {fmtMoney(shock.amount)} due day {shock.dueDay}
        </span>
      </div>
      {!result.bestMeetsTarget ? (
        <p className="note">
          No plan meets the {Math.round(target * 100)}% target; showing the plan with the highest survival.
        </p>
      ) : null}

      <div className="tiles">
        <Tile label="Largest survivable shock" sub={largestSub}>
          {largest}
        </Tile>
        <Tile label="Extra buffer needed" sub="For the chosen shock">
          {buffer}
        </Tile>
        <Tile label="Profit sacrificed" sub="Do-nothing plan vs best plan">
          <Money v={result.profitSacrificed} />
        </Tile>
        <Tile label="Expected churn cost" sub="Margin lost after the horizon">
          <Money v={best.metrics.churnCost} />
        </Tile>
      </div>

      <p className="plan">
        <strong>Best plan.</strong> {planSentence(scenario, best.choices)}
      </p>
    </section>
  );
}

export function SurvivalCurve({ result, scenario }: Props) {
  const target = scenario.objective.survivalTarget;
  const th = result.threshold;
  const shock = scenario.shocks.find((k) => k.id === scenario.threshold.shockIdToScale)!;
  return (
    <section className="subpanel" aria-labelledby="curve-title">
      <h3 className="chart-title" id="curve-title">
        Survival curve: chance of surviving as the shock grows
      </h3>
      <div className="chart small" role="img" aria-labelledby="curve-title">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={th.curve} margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="shock"
              type="number"
              domain={[0, scenario.threshold.maxShock]}
              tickFormatter={(v: number) => fmtMoney(v)}
              label={{ value: "Shock amount (S$)", position: "insideBottom", offset: -16 }}
            />
            <YAxis
              domain={[0, 1]}
              tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
              label={{ value: "Survival", angle: -90, position: "insideLeft" }}
            />
            <Tooltip
              formatter={(v: number) => [fmtPct(v), "Survival"]}
              labelFormatter={(v: number) => `Shock ${fmtMoney(v)}`}
            />
            <ReferenceLine
              y={target}
              stroke="var(--muted)"
              strokeDasharray="5 4"
              label={{ value: `Target ${Math.round(target * 100)}%`, position: "insideBottomRight", fill: "var(--muted)" }}
            />
            <ReferenceLine
              x={shock.amount}
              stroke={COLORS.shock}
              strokeDasharray="5 4"
              label={{ value: "Chosen shock", position: "insideTopRight", fill: COLORS.shock }}
            />
            <Line type="monotone" dataKey="survival" stroke={COLORS.cash} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
