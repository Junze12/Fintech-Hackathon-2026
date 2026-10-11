import { useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Result, Scenario } from "../model/types";
import { failDayOf, pathOf, strategyOf } from "./answer";
import { COLORS, fmtMoney, niceAxis } from "./format";

interface Props {
  result: Result;
  scenario: Scenario;
  strategyId: string;
}

interface CrossProps {
  cx?: number;
  cy?: number;
}
/** Red cross marking the day a single-run line fails. */
function FailCross({ cx = 0, cy = 0 }: CrossProps) {
  return (
    <g>
      <title>Run fails here</title>
      <path d={`M${cx - 6},${cy - 6} L${cx + 6},${cy + 6} M${cx + 6},${cy - 6} L${cx - 6},${cy + 6}`} stroke={COLORS.shock} strokeWidth={3} fill="none" />
    </g>
  );
}

export default function CashCompare({ result, scenario, strategyId }: Props) {
  const sel = strategyOf(result, strategyId);
  const selPath = pathOf(result, sel.pathId);
  const basePath = pathOf(result, strategyOf(result, "S0").pathId);
  const isBase = strategyId === "S0";
  const H = scenario.meta.horizonDays;

  const { data, crosses, axis } = useMemo(() => {
    const selFail = failDayOf(selPath.medianRun);
    const baseFail = failDayOf(basePath.medianRun);
    let lo = 0;
    let hi = 0;
    const rows = selPath.medianRun.map((s, d) => {
      const selCash = selFail !== null && d > selFail ? undefined : s.cash;
      const baseCash = baseFail !== null && d > baseFail ? undefined : basePath.medianRun[d].cash;
      const band: [number, number] = [selPath.daily.cash.p10[d], selPath.daily.cash.p90[d]];
      for (const v of [band[0], band[1], selCash, baseCash]) {
        if (v === undefined) continue;
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
      return { day: d, sel: selCash, base: isBase ? undefined : baseCash, band };
    });
    const x: { day: number; cash: number }[] = [];
    if (selFail !== null) x.push({ day: selFail, cash: selPath.medianRun[selFail].cash });
    if (!isBase && baseFail !== null) x.push({ day: baseFail, cash: basePath.medianRun[baseFail].cash });
    return { data: rows, crosses: x, axis: niceAxis(lo, hi) };
  }, [selPath, basePath, isBase]);

  return (
    <section className="panel" aria-labelledby="cash-compare-title">
      <h2 id="cash-compare-title">{isBase ? "Cash over time: doing nothing" : `${sel.name} vs doing nothing`}</h2>
      <ul className="legend" aria-label="Chart key">
        <li><span className="swatch" style={{ background: COLORS.cash }} aria-hidden="true" /> {sel.name}</li>
        {!isBase ? <li><span className="swatch dashed" aria-hidden="true" /> Do nothing</li> : null}
        <li><span style={{ color: COLORS.shock }} aria-hidden="true">✖</span> Run fails</li>
        <li><span className="swatch band" aria-hidden="true" /> p10–p90 range</li>
      </ul>
      <div className="chart" role="img" aria-labelledby="cash-compare-title">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis dataKey="day" type="number" domain={[0, H]} label={{ value: "Day", position: "insideBottom", offset: -16 }} />
            <YAxis domain={axis.domain} ticks={axis.ticks} allowDataOverflow tickFormatter={(v: number) => fmtMoney(v)} width={72} label={{ value: "Cash (S$)", angle: -90, position: "insideLeft", offset: -4 }} />
            <Tooltip
              formatter={(v: unknown, name: string) =>
                Array.isArray(v)
                  ? [`${fmtMoney(v[0] as number, 2)} to ${fmtMoney(v[1] as number, 2)}`, name]
                  : [fmtMoney(v as number, 2), name]
              }
              labelFormatter={(d: number) => `Day ${d}`}
            />
            {scenario.shocks.map((k) => (
              <ReferenceArea key={k.id} x1={k.announceDay} x2={k.dueDay} fill={COLORS.shock} fillOpacity={0.12} stroke={COLORS.shock} strokeOpacity={0.4} label={{ value: "Shock window", position: "insideTop", fill: COLORS.shock, fontSize: 11 }} />
            ))}
            <ReferenceLine y={0} stroke="#9CA3AF" />
            <Area type="monotone" dataKey="band" name={`${sel.name}: p10–p90`} stroke="none" fill={COLORS.cash} fillOpacity={0.15} isAnimationActive={false} />
            {!isBase ? (
              <Line type="monotone" dataKey="base" name="Do nothing" stroke={COLORS.pinned} strokeWidth={1.5} strokeDasharray="6 4" dot={false} connectNulls={false} isAnimationActive={false} />
            ) : null}
            <Line type="monotone" dataKey="sel" name={sel.name} stroke={COLORS.cash} strokeWidth={2.5} dot={false} connectNulls={false} isAnimationActive={false} />
            <Scatter data={crosses} dataKey="cash" shape={FailCross as never} isAnimationActive={false} legendType="none" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
