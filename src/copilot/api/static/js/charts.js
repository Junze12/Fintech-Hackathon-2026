// Hand-drawn SVG charts in Fintellect's look (grid, gold dashed reference line, soft band).
// The numbers they show come from the API as strings; Number() here only turns them into pixel
// positions. Tooltips are SVG <title> text nodes. Colours come from CSS classes so both themes work.
import { h, s } from "./dom.js";
import { axisMoney, money } from "./fmt.js";

const WIDE = 760;

function niceStep(range, ticks) {
  const raw = range / ticks || 1;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const f = raw / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
}

function scale(values, includeZero = true) {
  const nums = values.filter((v) => v !== null && v !== undefined && v !== "").map(Number);
  let lo = Math.min(...nums, includeZero ? 0 : Infinity);
  let hi = Math.max(...nums, includeZero ? 0 : -Infinity);
  if (!isFinite(lo) || !isFinite(hi)) [lo, hi] = [0, 1];
  if (lo === hi) [lo, hi] = [lo - 1, hi + 1];
  const step = niceStep(hi - lo, 5);
  return { lo: Math.floor(lo / step) * step, hi: Math.ceil(hi / step) * step, step };
}

/**
 * Line chart with an optional band, reference lines and event markers.
 * opts: {labels, tips?, series: [{name, values, cls}], band?: {lo, hi, cls}, refs?: [{value, label}],
 *        markers?: [{index, label}], height?, yFormat?, title}
 */
export function lineChart(opts) {
  const W = opts.width || WIDE;
  const H = opts.height || 260;
  const pl = 62, pr = 16, pt = 16, pb = 30;
  const n = opts.labels.length;
  const all = [
    ...opts.series.flatMap((x) => x.values),
    ...(opts.band ? [...opts.band.lo, ...opts.band.hi] : []),
    ...(opts.refs || []).map((r) => r.value),
  ];
  const sc = scale(all, opts.includeZero !== false);
  const X = (i) => pl + (n <= 1 ? 0 : (i * (W - pl - pr)) / (n - 1));
  const Y = (v) => pt + ((sc.hi - Number(v)) * (H - pt - pb)) / (sc.hi - sc.lo);
  const fy = opts.yFormat || axisMoney;
  const fv = opts.valueFormat || money;
  const kids = [];

  for (let v = sc.lo; v <= sc.hi + sc.step / 2; v += sc.step) {
    kids.push(s("line", { class: Math.abs(v) < 1e-9 ? "zero" : "gridln", x1: pl, x2: W - pr, y1: Y(v), y2: Y(v) }));
    kids.push(s("text", { class: "ax", x: pl - 8, y: Y(v) + 4, "text-anchor": "end" }, fy(v)));
  }
  const every = Math.max(1, Math.ceil(n / (opts.xTicks || 8)));
  opts.labels.forEach((lab, i) => {
    if ((i % every === 0 && n - 1 - i >= every / 2) || i === n - 1) {
      kids.push(s("text", { class: "ax", x: X(i), y: H - 8, "text-anchor": i === 0 ? "start" : i === n - 1 ? "end" : "middle" }, lab));
    }
  });
  if (opts.band) {
    const top = opts.band.hi.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`);
    const bottom = opts.band.lo.map((v, i) => `${X(i).toFixed(1)},${Y(v).toFixed(1)}`).reverse();
    kids.push(s("polygon", { class: `band ${opts.band.cls || ""}`, points: [...top, ...bottom].join(" ") }));
  }
  for (const r of opts.refs || []) {
    kids.push(s("line", { class: "ref", x1: pl, x2: W - pr, y1: Y(r.value), y2: Y(r.value) }));
    kids.push(s("text", { class: "ref-t", x: W - pr - 4, y: Y(r.value) - 5, "text-anchor": "end" }, r.label));
  }
  for (const x of opts.series) {
    const d = x.values
      .map((v, i) => (v === null || v === undefined ? null : `${X(i).toFixed(1)},${Y(v).toFixed(1)}`))
      .filter(Boolean);
    kids.push(s("polyline", { class: `ln ${x.cls || "fc"}`, points: d.join(" ") }));
  }
  for (const m of opts.markers || []) {
    if (m.index < 0) continue;
    const yv = opts.series[0].values[m.index];
    kids.push(s("line", { class: "mk", x1: X(m.index), x2: X(m.index), y1: pt, y2: H - pb }));
    kids.push(s("circle", { class: "mk-dot", cx: X(m.index), cy: Y(yv), r: 4.5 }, s("title", {}, m.label)));
    const nearEnd = X(m.index) > W - pr - 70;
    kids.push(s("text", { class: "mk-t", x: X(m.index) + (nearEnd ? -5 : 5), y: pt + 10 + (m.row || 0) * 13, "text-anchor": nearEnd ? "end" : "start" }, m.short || m.label));
  }
  // Hover areas with a native tooltip per point
  const slot = n > 1 ? (W - pl - pr) / (n - 1) : W - pl - pr;
  opts.labels.forEach((lab, i) => {
    const lines = [opts.tips ? opts.tips[i] : lab];
    for (const x of opts.series) if (x.values[i] !== null && x.values[i] !== undefined) lines.push(`${x.name}: ${fv(x.values[i])}`);
    if (opts.band) lines.push(`${opts.band.name || "Range"}: ${fv(opts.band.lo[i])} to ${fv(opts.band.hi[i])}`);
    kids.push(s("rect", { class: "hit", x: X(i) - slot / 2, y: pt, width: slot, height: H - pt - pb }, s("title", {}, lines.join("\n"))));
  });
  return h("div", { class: "chart" }, s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.title || "Chart" }, kids));
}

/** Scatter of plans: x = cost (S$), y = survival %. points: [{x, y, label, best}] */
export function scatter(points, opts = {}) {
  const W = opts.width || WIDE;
  const H = opts.height || 220;
  const pl = 52, pr = 16, pt = 14, pb = 34;
  const sx = scale(points.map((p) => p.x));
  const Y = (v) => pt + ((100 - Number(v)) * (H - pt - pb)) / 100;
  const X = (v) => pl + ((Number(v) - sx.lo) * (W - pl - pr)) / (sx.hi - sx.lo);
  const kids = [];
  for (let v = 0; v <= 100; v += 25) {
    kids.push(s("line", { class: "gridln", x1: pl, x2: W - pr, y1: Y(v), y2: Y(v) }));
    kids.push(s("text", { class: "ax", x: pl - 8, y: Y(v) + 4, "text-anchor": "end" }, `${v}%`));
  }
  for (let v = sx.lo; v <= sx.hi + sx.step / 2; v += sx.step) {
    kids.push(s("text", { class: "ax", x: X(v), y: H - 12, "text-anchor": "middle" }, axisMoney(v)));
  }
  if (opts.target !== undefined) {
    kids.push(s("line", { class: "ref", x1: pl, x2: W - pr, y1: Y(opts.target), y2: Y(opts.target) }));
    kids.push(s("text", { class: "ref-t", x: W - pr - 4, y: Y(opts.target) - 5, "text-anchor": "end" }, `Target ${opts.target}%`));
  }
  for (const p of points) {
    kids.push(s("circle", { class: `pt ${p.best ? "best" : ""}`, cx: X(p.x), cy: Y(p.y), r: p.best ? 7 : 5 }, s("title", {}, p.label)));
  }
  kids.push(s("text", { class: "ax", x: W - pr, y: H - 0, "text-anchor": "end" }, "Cost vs doing nothing"));
  return h("div", { class: "chart" }, s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.title || "Plans" }, kids));
}

/**
 * Waterfall as rows: each step already carries its start and end from the API.
 * steps: [{label, kind: "total"|"up"|"down", amount, start, end}]
 */
export function bridge(steps, opts = {}) {
  const sc = scale(steps.flatMap((st) => [st.start, st.end]));
  const P = (v) => ((Number(v) - sc.lo) * 100) / (sc.hi - sc.lo);
  return h(
    "div",
    { class: "bridge", role: "list", "aria-label": opts.title || "Bridge" },
    steps.map((st) => {
      const a = P(st.start), b = P(st.end);
      const bar = h(
        "div",
        { class: "bar" },
        h("i", { class: st.kind, style: { left: `${Math.min(a, b)}%`, width: `${Math.max(Math.abs(b - a), 0.4)}%` } }),
        h("span", { class: "zl", style: { left: `${P(0)}%` } }),
      );
      return h(
        "div",
        { class: `brow ${st.kind === "total" ? "sum" : ""}`, role: "listitem", title: `${st.label}: ${money(st.amount)}` },
        h("span", { class: "lb" }, st.label),
        bar,
        h("span", { class: `v ${Number(st.amount) < 0 ? "neg-t" : ""}` }, st.kind === "total" ? money(st.amount) : `${Number(st.amount) < 0 ? "" : "+"}${money(st.amount)}`),
      );
    }),
  );
}

/** Split a label into lines of at most `width` characters (by words). */
function wrap(text, width) {
  const lines = [];
  for (const word of String(text).split(" ")) {
    const last = lines[lines.length - 1];
    if (last && (last + " " + word).length <= width) lines[lines.length - 1] = last + " " + word;
    else lines.push(word);
  }
  return lines.slice(0, 3);
}

/**
 * Vertical waterfall. Each step already carries its start and end from the API; this only
 * places them. steps: [{label, kind: "total"|"up"|"down"|"margin", amount, start, end}]
 */
export function waterfall(steps, opts = {}) {
  const W = opts.width || WIDE;
  const H = opts.height || 300;
  const pl = 62, pr = 16, pt = 26, pb = 54;
  const sc = scale(steps.flatMap((st) => [st.start, st.end]));
  const Y = (v) => pt + ((sc.hi - Number(v)) * (H - pt - pb)) / (sc.hi - sc.lo);
  const slot = (W - pl - pr) / steps.length;
  const bw = Math.min(90, slot * 0.56);
  const kids = [];
  for (let v = sc.lo; v <= sc.hi + sc.step / 2; v += sc.step) {
    kids.push(s("line", { class: Math.abs(v) < 1e-9 ? "zero" : "gridln", x1: pl, x2: W - pr, y1: Y(v), y2: Y(v) }));
    kids.push(s("text", { class: "ax", x: pl - 8, y: Y(v) + 4, "text-anchor": "end" }, axisMoney(v)));
  }
  steps.forEach((st, i) => {
    const cx = pl + slot * i + slot / 2;
    const top = Math.min(Y(st.start), Y(st.end));
    const height = Math.max(Math.abs(Y(st.start) - Y(st.end)), 1.5);
    kids.push(s("rect", { class: `wf ${st.kind}${st.kind === "total" && Number(st.amount) < 0 ? " below" : ""}`, x: cx - bw / 2, y: top, width: bw, height, rx: 3 }, s("title", {}, `${st.label}: ${money(st.amount)}`)));
    if (i < steps.length - 1) {
      const next = steps[i + 1];
      if (next.kind !== "total") kids.push(s("line", { class: "wf-link", x1: cx + bw / 2, x2: cx + slot - bw / 2, y1: Y(st.end), y2: Y(st.end) }));
    }
    const neg = Number(st.amount) < 0;
    const below = Number(st.end) < Number(st.start) || (st.kind === "total" && neg);
    const labelY = below ? top + height + 15 : top - 7;
    kids.push(s("text", { class: `wf-v ${neg ? "neg" : ""}`, x: cx, y: labelY, "text-anchor": "middle" }, st.kind === "total" ? money(st.amount, 0) : `${neg ? "" : "+"}${money(st.amount, 0)}`));
    wrap(st.label, Math.max(10, Math.floor(slot / 6.5))).forEach((line, k) => {
      kids.push(s("text", { class: "ax strong", x: cx, y: H - pb + 18 + k * 13, "text-anchor": "middle" }, line));
    });
  });
  return h("div", { class: "chart" }, s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opts.title || "Waterfall" }, kids));
}

/** A small horizontal meter: value out of max (both strings or numbers). */
export function meter(value, max, cls = "") {
  const pctv = Number(max) > 0 ? Math.max(0, Math.min(100, (Number(value) * 100) / Number(max))) : 0;
  return h("div", { class: `meter ${cls}` }, h("i", { style: { width: `${pctv}%` } }));
}

/** The largest of several amount strings, for meter scales. */
export function maxOf(values) {
  return Math.max(0, ...values.map(Number));
}
