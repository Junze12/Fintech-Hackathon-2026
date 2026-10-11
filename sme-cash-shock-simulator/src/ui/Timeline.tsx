import { useEffect, useMemo, useState } from "react";
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
import type { EventType, Result, Scenario, SimEvent } from "../model/types";
import { failDayOf, lastDayOf, pathOf } from "./answer";
import { COLORS, fmtMoney, Money, niceAxis } from "./format";

interface Props {
  result: Result;
  scenario: Scenario;
  /** the path (strategy) whose median run is drawn */
  pathId: string;
  pinnedPathId: string | null;
}

type MarkerKind = "collection" | "outflow" | "invoice" | "credit_draw" | "failure";

const MARKER_OF: Partial<Record<EventType, MarkerKind>> = {
  collection: "collection",
  payable: "outflow",
  recurring: "outflow",
  invoice: "invoice",
  credit_draw: "credit_draw",
};

interface ShapeProps {
  cx?: number;
  cy?: number;
  payload?: { label: string; amount: number; day: number };
}

function markerShape(kind: MarkerKind) {
  return function Marker({ cx = 0, cy = 0, payload }: ShapeProps) {
    const tip = payload ? `Day ${payload.day}: ${payload.label} (${fmtMoney(payload.amount, 2)})` : "";
    let shape: React.ReactNode;
    switch (kind) {
      case "collection":
        shape = <path d={`M${cx},${cy - 6} L${cx + 6},${cy + 5} L${cx - 6},${cy + 5} Z`} fill={COLORS.profit} />;
        break;
      case "outflow":
        shape = <path d={`M${cx},${cy + 6} L${cx + 6},${cy - 5} L${cx - 6},${cy - 5} Z`} fill={COLORS.payables} />;
        break;
      case "invoice":
        shape = <circle cx={cx} cy={cy} r={3} fill={COLORS.revenue} />;
        break;
      case "credit_draw":
        shape = <rect x={cx - 5} y={cy - 5} width={10} height={10} fill={COLORS.credit} />;
        break;
      case "failure":
        shape = (
          <path
            d={`M${cx - 6},${cy - 6} L${cx + 6},${cy + 6} M${cx + 6},${cy - 6} L${cx - 6},${cy + 6}`}
            stroke={COLORS.shock}
            strokeWidth={3}
            fill="none"
          />
        );
        break;
    }
    return (
      <g>
        <title>{tip}</title>
        {shape}
      </g>
    );
  };
}

const SHAPES: Record<MarkerKind, ReturnType<typeof markerShape>> = {
  collection: markerShape("collection"),
  outflow: markerShape("outflow"),
  invoice: markerShape("invoice"),
  credit_draw: markerShape("credit_draw"),
  failure: markerShape("failure"),
};

const LEGEND: { kind: MarkerKind; text: string; glyph: string; color: string }[] = [
  { kind: "collection", text: "Customer pays", glyph: "▲", color: COLORS.profit },
  { kind: "outflow", text: "Bill paid", glyph: "▼", color: COLORS.payables },
  { kind: "invoice", text: "New invoice", glyph: "●", color: COLORS.revenue },
  { kind: "credit_draw", text: "Credit drawn", glyph: "■", color: COLORS.credit },
  { kind: "failure", text: "Failure", glyph: "✖", color: COLORS.shock },
];

export default function Timeline({ result, scenario, pathId, pinnedPathId }: Props) {
  const H = scenario.meta.horizonDays;
  const best = pathOf(result, pathId);
  const pinned = pinnedPathId ? pathOf(result, pinnedPathId) : null;
  const creditLimit = scenario.creditLines.reduce((a, l) => a + l.limit, 0);
  // Lines from a single run stop on the day the run fails (A1.4); the scrubber ends with the longest line.
  const mainEnd = lastDayOf(best.medianRun);
  const pinEnd = pinned ? lastDayOf(pinned.medianRun) : 0;
  const maxDay = Math.max(mainEnd, pinEnd);

  const [dayRaw, setDay] = useState(0);
  const day = Math.min(dayRaw, maxDay);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      setDay((d) => {
        if (d >= maxDay) {
          setPlaying(false);
          return d;
        }
        return d + 1;
      });
    }, 150);
    return () => window.clearInterval(id);
  }, [playing, maxDay]);

  const { data, markers, axis } = useMemo(() => {
    const rows = best.medianRun.map((s, d) => ({
      day: s.day,
      cash: d > mainEnd ? undefined : s.cash,
      band: [best.daily.cash.p10[d], best.daily.cash.p90[d]] as [number, number],
      pinCash: pinned && d <= pinEnd ? pinned.medianRun[d].cash : undefined,
    }));
    const mk: Record<MarkerKind, { day: number; cash: number; label: string; amount: number }[]> = {
      collection: [],
      outflow: [],
      invoice: [],
      credit_draw: [],
      failure: [],
    };
    best.medianRun.forEach((s) => {
      if (s.day > mainEnd) return;
      s.events.forEach((e: SimEvent) => {
        const k = MARKER_OF[e.type];
        if (k) mk[k].push({ day: s.day, cash: s.cash, label: e.label, amount: e.amount });
      });
    });
    let lo = -creditLimit;
    let hi = 0;
    for (const r of rows) {
      lo = Math.min(lo, r.band[0], r.cash ?? Infinity, r.pinCash ?? Infinity);
      hi = Math.max(hi, r.band[1], r.cash ?? -Infinity, r.pinCash ?? -Infinity);
    }
    return { data: rows, markers: mk, axis: niceAxis(lo, hi) };
  }, [best, pinned, creditLimit, mainEnd, pinEnd]);

  const snap = best.medianRun[day];
  const crosses: { day: number; cash: number; label: string; amount: number }[] = [];
  const mainFail = failDayOf(best.medianRun);
  if (mainFail !== null) crosses.push({ day: mainFail, cash: best.medianRun[mainFail].cash, label: "Run fails", amount: best.medianRun[mainFail].cash });
  const pinFail = pinned ? failDayOf(pinned.medianRun) : null;
  if (pinned && pinFail !== null) crosses.push({ day: pinFail, cash: pinned.medianRun[pinFail].cash, label: "Pinned run fails", amount: pinned.medianRun[pinFail].cash });

  return (
    <section className="subpanel" aria-labelledby="p2-title">
      <h3 id="p2-title" className="section-title">Cash timeline with events</h3>
      <p className="muted">
        Median run of the selected option (solid line) with the p10–p90 range of cash across runs (shaded). A line
        stops with a red cross on the day its run fails.
      </p>
      <h3 className="chart-title" id="cash-title">Cash by day</h3>
      <div className="chart tall" role="img" aria-labelledby="cash-title">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="day"
              type="number"
              domain={[0, H]}
              label={{ value: "Day", position: "insideBottom", offset: -16 }}
            />
            <YAxis
              domain={axis.domain}
              ticks={axis.ticks}
              allowDataOverflow
              tickFormatter={(v: number) => fmtMoney(v)}
              label={{ value: "Cash (S$)", angle: -90, position: "insideLeft", offset: -4 }}
              width={72}
            />
            <Tooltip
              formatter={(v: unknown, name: string) =>
                Array.isArray(v)
                  ? [`${fmtMoney(v[0] as number, 2)} to ${fmtMoney(v[1] as number, 2)}`, "p10–p90 cash"]
                  : [fmtMoney(v as number, 2), name]
              }
              labelFormatter={(d: number) => `Day ${d}`}
            />
            {scenario.shocks.map((k) => (
              <ReferenceArea
                key={k.id}
                x1={k.announceDay}
                x2={k.dueDay}
                fill={COLORS.shock}
                fillOpacity={0.12}
                stroke={COLORS.shock}
                strokeOpacity={0.4}
                label={{ value: "Shock window", position: "insideTop", fill: COLORS.shock, fontSize: 11 }}
              />
            ))}
            <ReferenceLine y={0} stroke="#9CA3AF" />
            <ReferenceLine
              y={-creditLimit}
              stroke="#9CA3AF"
              strokeDasharray="5 4"
              label={{ value: "Credit limit", position: "insideBottomRight", fill: "var(--muted)", fontSize: 11 }}
            />
            <Area
              type="monotone"
              dataKey="band"
              name="p10–p90 cash"
              stroke="none"
              fill={COLORS.cash}
              fillOpacity={0.2}
              isAnimationActive={false}
            />
            {pinned ? (
              <Line
                type="monotone"
                dataKey="pinCash"
                name="Pinned plan (median)"
                stroke={COLORS.pinned}
                strokeDasharray="6 4"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ) : null}
            <Line
              type="monotone"
              dataKey="cash"
              name="Cash (median run)"
              stroke={COLORS.cash}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            {(Object.keys(markers) as MarkerKind[]).map((k) => (
              <Scatter key={k} data={markers[k]} dataKey="cash" shape={SHAPES[k]} isAnimationActive={false} legendType="none" />
            ))}
            <Scatter data={crosses} dataKey="cash" shape={SHAPES.failure} isAnimationActive={false} legendType="none" />
            <ReferenceLine x={day} stroke="var(--text)" strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <ul className="legend" aria-label="Event marker key">
        {LEGEND.map((l) => (
          <li key={l.kind}>
            <span style={{ color: l.color }} aria-hidden="true">{l.glyph}</span> {l.text}
          </li>
        ))}
      </ul>

      <div className="scrubber">
        <button
          type="button"
          className="btn"
          onClick={() => {
            if (!playing && day >= maxDay) setDay(0);
            setPlaying((p) => !p);
          }}
          aria-pressed={playing}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <label htmlFor="day-slider" className="scrub-label">Day {day}</label>
        <input
          id="day-slider"
          type="range"
          min={0}
          max={maxDay}
          step={1}
          value={day}
          onChange={(e) => {
            setPlaying(false);
            setDay(Number(e.target.value));
          }}
          aria-valuetext={`Day ${day}`}
        />
      </div>

      <div className="event-card" aria-live="polite">
        <div className="event-grid">
          <div><span className="muted">Day</span><b>{snap.day}</b></div>
          <div><span className="muted">Cash</span><b><Money v={snap.cash} dec={2} /></b></div>
          <div><span className="muted">Credit drawn</span><b>{fmtMoney(snap.creditDrawn, 2)}</b></div>
          <div><span className="muted">Receivables</span><b>{fmtMoney(snap.receivablesOpen, 2)}</b></div>
          <div><span className="muted">Payables</span><b>{fmtMoney(snap.payablesOpen, 2)}</b></div>
        </div>
        {snap.events.length === 0 ? (
          <p className="muted">No events on this day.</p>
        ) : (
          <ul className="events">
            {snap.events.map((e, i) => (
              <li key={i}>
                <span className="evt-type">{e.type.replace("_", " ")}</span> {e.label}
                {e.amount !== 0 ? <> — <Money v={e.amount} dec={2} /></> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
