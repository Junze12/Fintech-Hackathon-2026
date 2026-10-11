import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Customized,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Result, Scenario } from "../model/types";
import { chosenShock, gapBridge, pathOf, strategyOf, type Bar as BridgeBar } from "./answer";
import { COLORS, fmtMoney, niceAxis } from "./format";

interface Props {
  result: Result;
  scenario: Scenario;
  strategyId: string;
}

const GREEN = COLORS.profit;
const RED = COLORS.shock;
const BLUE = COLORS.cash;
const GREY = COLORS.pinned;

function fillOf(b: BridgeBar): string {
  if (b.kind === "total") return BLUE;
  if (b.kind === "margin") return "url(#hatch)";
  return b.value >= 0 ? GREEN : RED;
}

const signed = (v: number) => `${v >= 0 ? "+" : "-"}${fmtMoney(Math.abs(v))}`;

/** Wraps a long category label onto up to three short lines. */
function Tick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const words = (payload?.value ?? "").split(" ");
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    if ((cur + " " + w).trim().length > 13 && cur) {
      lines.push(cur);
      cur = w;
    } else cur = (cur + " " + w).trim();
  }
  if (cur) lines.push(cur);
  return (
    <text x={x} y={(y ?? 0) + 12} textAnchor="middle" fontSize={11} fill="var(--text)">
      {lines.map((l, i) => (
        <tspan key={i} x={x} dy={i === 0 ? 0 : 13}>
          {l}
        </tspan>
      ))}
    </text>
  );
}

/** Red "Short" fill above the last bar and the "spare" label, drawn with the chart's own scales. */
function Annotations(props: Record<string, unknown>) {
  const { xAxisMap, yAxisMap, gap, spare, shock, worst } = props as {
    xAxisMap?: Record<string, { scale: ((v: string) => number) & { bandwidth?: () => number } }>;
    yAxisMap?: Record<string, { scale: (v: number) => number }>;
    gap: number;
    spare: number;
    shock: number;
    worst: number;
  };
  const xa = xAxisMap && Object.values(xAxisMap)[0];
  const ya = yAxisMap && Object.values(yAxisMap)[0];
  if (!xa || !ya) return null;
  const x0 = xa.scale("Worst likely position");
  const bw = xa.scale.bandwidth ? xa.scale.bandwidth() : 40;
  if (gap > 0) {
    const yTop = ya.scale(shock);
    const yBot = ya.scale(worst);
    return (
      <g>
        <rect x={x0} y={yTop} width={bw} height={Math.max(0, yBot - yTop)} fill={RED} fillOpacity={0.25} />
        <text x={x0 + bw / 2} y={(yTop + yBot) / 2} textAnchor="middle" dominantBaseline="middle" fontSize={12} fontWeight={700} fill={RED}>
          Short {fmtMoney(gap)}
        </text>
      </g>
    );
  }
  if (spare > 0) {
    return (
      <text x={x0 + bw / 2} y={ya.scale(worst) - 24} textAnchor="middle" fontSize={12} fontWeight={700} fill={GREEN}>
        {fmtMoney(spare)} spare
      </text>
    );
  }
  return null;
}

export default function GapBridge({ result, scenario, strategyId }: Props) {
  const shock = chosenShock(scenario);
  const D = shock.dueDay;
  const target = Math.round(scenario.objective.survivalTarget * 100);
  const sel = strategyOf(result, strategyId);
  const L = pathOf(result, sel.pathId).liquidity;
  const L0 = pathOf(result, strategyOf(result, "S0").pathId).liquidity;
  const bridge = gapBridge(result, scenario, strategyId);
  const shown = bridge.bars.filter((b) => !b.hidden);

  if (!bridge.adds) {
    console.error("Bridge does not add up", { reached: bridge.reached, worst: bridge.worst });
  }

  const data = shown.map((b) => ({
    ...b,
    range: [Math.min(b.from, b.to), Math.max(b.from, b.to)] as [number, number],
  }));
  let lo = 0;
  let hi = shock.amount;
  for (const d of data) {
    lo = Math.min(lo, d.range[0]);
    hi = Math.max(hi, d.range[1]);
  }
  const { domain, ticks } = niceAxis(lo, hi + (hi - lo) * 0.08);

  const tooltip = ({ active, payload }: { active?: boolean; payload?: { payload: (typeof data)[number] }[] }) => {
    if (!active || !payload || payload.length === 0) return null;
    const b = payload[0].payload;
    return (
      <div className="tooltip">
        <b>{b.label}</b>
        <div>{b.kind === "total" ? fmtMoney(b.value) : signed(b.value)}</div>
        {b.key === "plan" ? (
          <ul>
            <li>Financing advances net of fees: {signed(L.meanFinancingNet - L0.meanFinancingNet)}</li>
            <li>Extra customer payments: {signed(L.meanCollections - L0.meanCollections)}</li>
            <li>Action costs paid: {signed(-(L.meanActionCosts - L0.meanActionCosts))}</li>
          </ul>
        ) : null}
      </div>
    );
  };

  return (
    <section className="panel" aria-labelledby="bridge-title">
      <h2 id="bridge-title">Cash you can reach on day {D}</h2>
      <p className="muted small-text">Plan shown: {sel.name}</p>
      {!bridge.adds ? (
        <div className="banner" role="alert">
          Bridge does not add up: engine bug ({fmtMoney(bridge.reached, 2)} vs {fmtMoney(bridge.worst, 2)})
        </div>
      ) : null}
      <div className="chart bridge" role="img" aria-labelledby="bridge-title" aria-describedby="bridge-caption">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 28, right: 210, bottom: 40, left: 8 }}>
            <defs>
              <pattern id="hatch" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
                <rect width="7" height="7" fill={GREY} fillOpacity={0.18} />
                <line x1="0" y1="0" x2="0" y2="7" stroke={GREY} strokeWidth="3" />
              </pattern>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="label" interval={0} tick={<Tick />} height={52} />
            <YAxis
              domain={domain}
              ticks={ticks}
              tickFormatter={(v: number) => fmtMoney(v)}
              width={74}
              label={{ value: "Cash (S$)", angle: -90, position: "insideLeft", offset: -2 }}
            />
            <Tooltip content={tooltip as never} />
            <ReferenceLine y={0} stroke="#9CA3AF" />
            <ReferenceLine
              y={shock.amount}
              stroke={RED}
              strokeWidth={2}
              strokeDasharray="6 4"
              label={{ value: `Needed on day ${D}: ${fmtMoney(shock.amount)}`, position: "right", fill: RED, fontSize: 12, fontWeight: 600 }}
            />
            <Bar dataKey="range" isAnimationActive={false} maxBarSize={72}>
              {data.map((b) => (
                <Cell key={b.key} fill={fillOf(b)} stroke={b.kind === "margin" ? GREY : undefined} />
              ))}
              <LabelList
                dataKey="range"
                position="top"
                content={
                  ((p: Record<string, unknown>) => {
                    const { x, y, width, index } = p as { x: number; y: number; width: number; index: number };
                    const b = data[index];
                    return (
                      <text x={x + width / 2} y={y - 6} textAnchor="middle" fontSize={12} fontWeight={600} fill="var(--text)">
                        {b.kind === "total" ? fmtMoney(b.value) : signed(b.value)}
                      </text>
                    );
                  }) as never
                }
              />
            </Bar>
            <Customized component={<Annotations gap={L.gapAtShock} spare={L.spareAtShock} shock={shock.amount} worst={L.safeLiquidity} />} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p id="bridge-caption" className="caption">
        Worst likely position = the level you stay above in {target}% of simulated runs.
      </p>
    </section>
  );
}
