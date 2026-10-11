import { useMemo, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Metrics, Result } from "../model/types";
import { COLORS, fmtMoney, Money } from "./format";

interface Props {
  result: Result;
  pinnedPathId: string | null;
}

function Tile({ label, v, range }: { label: string; v: number; range?: { p10: number; p90: number } }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value"><Money v={v} /></div>
      {range ? (
        <div className="tile-sub">
          p10–p90: <Money v={range.p10} /> to <Money v={range.p90} />
        </div>
      ) : null}
    </div>
  );
}

const axisMoney = (v: number) => fmtMoney(v);
const tipMoney = (v: unknown, name: string): [string, string] =>
  Array.isArray(v)
    ? [`${fmtMoney(v[0] as number, 2)} to ${fmtMoney(v[1] as number, 2)}`, name]
    : [fmtMoney(v as number, 2), name];

export default function Financials({ result, pinnedPathId }: Props) {
  const best = result.paths.find((p) => p.id === result.bestPathId)!;
  const def = result.paths.find((p) => p.id === result.defaultPathId)!;
  const pinned = pinnedPathId ? result.paths.find((p) => p.id === pinnedPathId) ?? null : null;
  const [view, setView] = useState<"all" | "survivors">("all");
  const survivorsOk = best.metricsSurvivorsOnly !== null;
  const m: Metrics = view === "survivors" && best.metricsSurvivorsOnly ? best.metricsSurvivorsOnly : best.metrics;

  const rows = useMemo(
    () =>
      best.daily.cash.p50.map((_, d) => ({
        day: d,
        rev: best.daily.revenue.p50[d],
        prof: best.daily.profit.p50[d],
        profBand: [best.daily.profit.p10[d], best.daily.profit.p90[d]] as [number, number],
        rec: best.daily.receivablesOpen.p50[d],
        pay: best.daily.payablesOpen.p50[d],
        cash: best.daily.cash.p50[d],
        credit: best.daily.creditDrawn.p50[d],
        pinRev: pinned?.daily.revenue.p50[d],
        pinProf: pinned?.daily.profit.p50[d],
        pinRec: pinned?.daily.receivablesOpen.p50[d],
        pinPay: pinned?.daily.payablesOpen.p50[d],
        pinCash: pinned?.daily.cash.p50[d],
        pinCredit: pinned?.daily.creditDrawn.p50[d],
      })),
    [best, pinned],
  );

  // Waterfall layout: running totals only position the bars; every amount comes from the Result.
  const waterfall = useMemo(() => {
    const bars: { name: string; range: [number, number]; amount: number; kind: "total" | "up" | "down" }[] = [];
    const start = def.metrics.economicProfit.mean;
    bars.push({ name: "Do-nothing plan", range: [Math.min(0, start), Math.max(0, start)], amount: start, kind: "total" });
    let run = start;
    for (const b of result.profitBridge) {
      if (Math.abs(b.amount) < 1) continue;
      const next = run + b.amount;
      bars.push({ name: b.item, range: [Math.min(run, next), Math.max(run, next)], amount: b.amount, kind: b.amount >= 0 ? "up" : "down" });
      run = next;
    }
    const end = best.metrics.economicProfit.mean;
    bars.push({ name: "Best plan", range: [Math.min(0, end), Math.max(0, end)], amount: end, kind: "total" });
    return bars;
  }, [result, best, def]);

  const dayAxis = { dataKey: "day", type: "number" as const, domain: [0, rows.length - 1] as [number, number] };
  const pinNote = pinned ? " Dashed grey: pinned plan." : "";

  return (
    <section className="panel" aria-labelledby="p3-title">
      <h2 id="p3-title">3 · Financial dashboard</h2>
      <div className="toggle" role="group" aria-label="Which runs the tiles summarise">
        <button type="button" className={`seg ${view === "all" ? "on" : ""}`} aria-pressed={view === "all"} onClick={() => setView("all")}>
          All runs
        </button>
        <button
          type="button"
          className={`seg ${view === "survivors" ? "on" : ""}`}
          aria-pressed={view === "survivors"}
          disabled={!survivorsOk}
          title={survivorsOk ? undefined : "No run survived"}
          onClick={() => setView("survivors")}
        >
          Surviving runs only
        </button>
      </div>

      <div className="tiles tiles-3">
        <Tile label="Revenue" v={m.revenue} />
        <Tile label="Gross profit" v={m.grossProfit} />
        <Tile label="Profit" v={m.profit.mean} range={m.profit} />
        <Tile label="Economic profit" v={m.economicProfit.mean} range={m.economicProfit} />
        <Tile label="End receivables" v={m.endReceivables} />
        <Tile label="End payables" v={m.endPayables} />
        <Tile label="Peak credit drawn" v={m.peakCreditDrawn} />
        <Tile label="Discounts given" v={m.discountsGiven} />
        <Tile label="Interest expense" v={m.interestExpense} />
      </div>

      <div className="charts-2">
        <div>
          <h3 className="chart-title" id="ca-title">Revenue and profit to date</h3>
          <div className="chart" role="img" aria-labelledby="ca-title">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={rows} margin={{ top: 8, right: 12, bottom: 28, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
                <XAxis {...dayAxis} label={{ value: "Day", position: "insideBottom", offset: -16 }} />
                <YAxis tickFormatter={axisMoney} width={68} label={{ value: "S$", angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={tipMoney} labelFormatter={(d: number) => `Day ${d}`} />
                <Legend verticalAlign="top" height={24} />
                <ReferenceLine y={0} stroke="#9CA3AF" />
                <Area type="monotone" dataKey="profBand" name="Profit p10–p90" stroke="none" fill={COLORS.profit} fillOpacity={0.18} isAnimationActive={false} />
                <Line type="monotone" dataKey="rev" name="Revenue (p50)" stroke={COLORS.revenue} dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="prof" name="Profit (p50)" stroke={COLORS.profit} dot={false} strokeWidth={2} isAnimationActive={false} />
                {pinned ? <Line type="monotone" dataKey="pinRev" name="Pinned revenue" stroke={COLORS.pinned} strokeDasharray="6 4" dot={false} isAnimationActive={false} /> : null}
                {pinned ? <Line type="monotone" dataKey="pinProf" name="Pinned profit" stroke={COLORS.pinned} strokeDasharray="2 3" dot={false} isAnimationActive={false} /> : null}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="chart-title" id="cb-title">Money owed to you vs bills</h3>
          <div className="chart" role="img" aria-labelledby="cb-title">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 28, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
                <XAxis {...dayAxis} label={{ value: "Day", position: "insideBottom", offset: -16 }} />
                <YAxis tickFormatter={axisMoney} width={68} label={{ value: "S$", angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={tipMoney} labelFormatter={(d: number) => `Day ${d}`} />
                <Legend verticalAlign="top" height={24} />
                <Line type="stepAfter" dataKey="rec" name="Receivables (p50)" stroke={COLORS.receivables} dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="stepAfter" dataKey="pay" name="Payables (p50)" stroke={COLORS.payables} dot={false} strokeWidth={2} isAnimationActive={false} />
                {pinned ? <Line type="stepAfter" dataKey="pinRec" name="Pinned receivables" stroke={COLORS.pinned} strokeDasharray="6 4" dot={false} isAnimationActive={false} /> : null}
                {pinned ? <Line type="stepAfter" dataKey="pinPay" name="Pinned payables" stroke={COLORS.pinned} strokeDasharray="2 3" dot={false} isAnimationActive={false} /> : null}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="chart-title" id="cc-title">Cash and credit</h3>
          <div className="chart" role="img" aria-labelledby="cc-title">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 28, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
                <XAxis {...dayAxis} label={{ value: "Day", position: "insideBottom", offset: -16 }} />
                <YAxis tickFormatter={axisMoney} width={68} label={{ value: "S$", angle: -90, position: "insideLeft" }} />
                <Tooltip formatter={tipMoney} labelFormatter={(d: number) => `Day ${d}`} />
                <Legend verticalAlign="top" height={24} />
                <ReferenceLine y={0} stroke="#9CA3AF" />
                <Line type="monotone" dataKey="cash" name="Cash (p50)" stroke={COLORS.cash} dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="credit" name="Credit drawn (p50)" stroke={COLORS.credit} dot={false} strokeWidth={2} isAnimationActive={false} />
                {pinned ? <Line type="monotone" dataKey="pinCash" name="Pinned cash" stroke={COLORS.pinned} strokeDasharray="6 4" dot={false} isAnimationActive={false} /> : null}
                {pinned ? <Line type="monotone" dataKey="pinCredit" name="Pinned credit" stroke={COLORS.pinned} strokeDasharray="2 3" dot={false} isAnimationActive={false} /> : null}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div>
          <h3 className="chart-title" id="cd-title">What survival cost</h3>
          <div className="chart" role="img" aria-labelledby="cd-title">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={waterfall} margin={{ top: 8, right: 12, bottom: 52, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
                <XAxis dataKey="name" interval={0} angle={-30} textAnchor="end" height={60} tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={axisMoney} width={68} label={{ value: "Economic profit (S$)", angle: -90, position: "insideLeft", offset: -2 }} />
                <Tooltip
                  formatter={(_v: unknown, _n: string, item: { payload?: { amount: number; kind: string } }) => [
                    `${item.payload && item.payload.amount >= 0 ? "+" : ""}${fmtMoney(item.payload?.amount ?? 0, 2)}`,
                    item.payload?.kind === "total" ? "Economic profit" : "Change",
                  ]}
                />
                <ReferenceLine y={0} stroke="#9CA3AF" />
                <Bar dataKey="range" isAnimationActive={false}>
                  {waterfall.map((b, i) => (
                    <Cell key={i} fill={b.kind === "total" ? COLORS.cash : b.kind === "up" ? COLORS.profit : COLORS.shock} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="muted small-text">Blue: totals · green: gain · red: loss.{pinNote}</p>
        </div>
      </div>
    </section>
  );
}
