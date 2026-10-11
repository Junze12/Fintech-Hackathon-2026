import type { Result, Scenario, TreeEdge } from "../model/types";
import { COLORS, fmtMoney, fmtPct } from "./format";
import { planSentence } from "../model/plan";

interface Props {
  result: Result;
  scenario: Scenario;
  pinnedPathId: string | null;
  onPin: (pathId: string | null) => void;
}

const COL_GAP = 220; // distance between columns
const BOX_W = 176;
const BOX_H = 36;
const BOX_GAP = 8;
const PAD_X = 12;
const TOP = 44;
const ACCENT = "#2563EB";
const GREY = "#9CA3AF";

function clip(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export default function DecisionTree({ result, scenario, pinnedPathId, onPin }: Props) {
  const nodes = result.tree.nodes;
  const frontier = new Set(result.frontierPathIds);
  const cols = nodes.map((n) => ({ node: n, edges: result.tree.edges.filter((e) => e.nodeId === n.id) }));
  const maxCount = Math.max(...cols.map((c) => c.edges.length));
  const height = TOP + maxCount * (BOX_H + BOX_GAP) + 8;
  const width = PAD_X * 2 + (cols.length - 1) * COL_GAP + BOX_W;

  const colX = (i: number) => PAD_X + i * COL_GAP;
  const boxY = (j: number) => TOP + j * (BOX_H + BOX_GAP);
  const stackMid = (n: number) => TOP + (n * (BOX_H + BOX_GAP) - BOX_GAP) / 2;
  const junctionX = (i: number) => colX(i) - (COL_GAP - BOX_W) / 2;

  type Line = { d: string; best: boolean; key: string };
  const lines: Line[] = [];
  for (let i = 0; i + 1 < cols.length; i++) {
    const jx = junctionX(i + 1);
    const jy = stackMid(cols[i + 1].edges.length);
    cols[i].edges.forEach((e, j) => {
      const x0 = colX(i) + BOX_W;
      const y0 = boxY(j) + BOX_H / 2;
      const mx = (x0 + jx) / 2;
      lines.push({ key: `a${i}-${j}`, best: e.onBestPath, d: `M${x0},${y0} C${mx},${y0} ${mx},${jy} ${jx},${jy}` });
    });
    cols[i + 1].edges.forEach((e, j) => {
      const x1 = colX(i + 1);
      const y1 = boxY(j) + BOX_H / 2;
      const mx = (x1 + jx) / 2;
      lines.push({ key: `b${i}-${j}`, best: e.onBestPath, d: `M${jx},${jy} C${mx},${jy} ${mx},${y1} ${x1},${y1}` });
    });
  }

  const pinnedPath = pinnedPathId ? result.paths.find((p) => p.id === pinnedPathId) : null;

  const box = (e: TreeEdge, i: number, j: number) => {
    const pinned = pinnedPathId !== null && e.bestPathId === pinnedPathId;
    const best = e.onBestPath;
    const full = best || pinned;
    const x = colX(i);
    const y = boxY(j);
    const star = frontier.has(e.bestPathId);
    const activate = () => onPin(pinned ? null : e.bestPathId);
    return (
      <g
        key={`${e.nodeId}:${e.optionId}`}
        role="button"
        tabIndex={0}
        aria-pressed={pinned}
        aria-label={`${e.label}. Survival ${fmtPct(e.survivalProb)}, economic profit ${fmtMoney(e.economicProfit)}.${best ? " On the best plan." : ""}${star ? " On the frontier." : ""}`}
        opacity={full ? 1 : 0.3}
        style={{ cursor: "pointer" }}
        onClick={activate}
        onKeyDown={(ev) => {
          if (ev.key === "Enter" || ev.key === " ") {
            ev.preventDefault();
            activate();
          }
        }}
      >
        <title>{`${e.label} — ${fmtPct(e.survivalProb)} survive, ${fmtMoney(e.economicProfit, 2)} economic profit`}</title>
        <rect
          x={x}
          y={y}
          width={BOX_W}
          height={BOX_H}
          rx={8}
          fill="var(--card)"
          stroke={pinned ? COLORS.pinned : best ? ACCENT : GREY}
          strokeWidth={best && !pinned ? 3 : 1}
          strokeDasharray={pinned ? "5 3" : undefined}
        />
        <text x={x + 8} y={y + 14} fontSize={11} fontWeight={best ? 700 : 400} fill="var(--text)">
          {clip(e.label, 25)}
        </text>
        <text x={x + 8} y={y + 29} fontSize={10} fill={e.economicProfit < 0 ? COLORS.shock : "var(--muted)"}>
          {fmtPct(e.survivalProb)} · {fmtMoney(e.economicProfit)}
        </text>
        {star ? (
          <text x={x + BOX_W - 16} y={y + 14} fontSize={12} fill={COLORS.credit} aria-hidden="true">
            ★
          </text>
        ) : null}
      </g>
    );
  };

  return (
    <section className="subpanel" aria-labelledby="p4-title">
      <h3 id="p4-title" className="section-title">Decision tree</h3>
      <p className="muted">
        Each box shows the chance of surviving and the average economic profit of the best plan that takes that
        option. The best plan is outlined in blue; ★ marks plans on the survival/profit frontier. Click a box to
        compare.
      </p>
      {pinnedPath ? (
        <div className="chip" role="status">
          <span>Comparing: {planSentence(scenario, pinnedPath.choices)}</span>
          <button type="button" className="chip-x" onClick={() => onPin(null)} aria-label="Clear comparison">
            ×
          </button>
        </div>
      ) : null}
      <div className="tree-scroll">
        <svg width={width} height={height} role="group" aria-label="Decision tree">
          <title>Decision tree: one column per decision point</title>
          {cols.map((c, i) => (
            <text key={c.node.id} x={colX(i)} y={22} fontSize={12} fontWeight={600} fill="var(--text)">
              {clip(`Day ${c.node.day} · ${c.node.label}`, 28)}
            </text>
          ))}
          {lines
            .filter((l) => !l.best)
            .map((l) => (
              <path key={l.key} d={l.d} fill="none" stroke={GREY} strokeWidth={1} opacity={0.3} />
            ))}
          {lines
            .filter((l) => l.best)
            .map((l) => (
              <path key={l.key} d={l.d} fill="none" stroke={ACCENT} strokeWidth={3} />
            ))}
          {cols.map((c, i) => c.edges.map((e, j) => box(e, i, j)))}
        </svg>
      </div>
      <div className="row">
        <button type="button" className="btn" onClick={() => onPin(null)} disabled={pinnedPathId === null}>
          Reset
        </button>
      </div>
    </section>
  );
}
