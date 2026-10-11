import type { ReactNode } from "react";

export const COLORS = {
  cash: "#2563EB",
  profit: "#16A34A",
  revenue: "#7C3AED",
  receivables: "#0891B2",
  payables: "#EA580C",
  credit: "#F59E0B",
  shock: "#DC2626",
  pinned: "#6B7280",
} as const;

/** "S$1,234" (dec = 0) or "S$1,234.56" (dec = 2); negatives get a leading minus: "-S$1,234". */
export function fmtMoney(x: number, dec = 0): string {
  const rounded = Number(Math.abs(x).toFixed(dec));
  const body = rounded.toLocaleString("en-US", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
  return `${x < 0 && rounded !== 0 ? "-" : ""}S$${body}`;
}

/** A round axis: ticks at 1, 2, 2.5 or 5 times a power of ten, covering [lo, hi]. */
export function niceAxis(lo: number, hi: number, target = 5): { domain: [number, number]; ticks: number[] } {
  const range = Math.max(hi - lo, 1);
  const raw = range / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw)!;
  const a = Math.floor(lo / step) * step;
  const b = Math.ceil(hi / step) * step;
  const ticks: number[] = [];
  for (let v = a; v <= b + step / 2; v += step) ticks.push(Math.round(v * 100) / 100);
  return { domain: [a, b], ticks };
}

/** Probability (0-1) as a percent with 1 decimal. */
export function fmtPct(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

/** Money as text, in red when negative. */
export function Money({ v, dec = 0 }: { v: number; dec?: number }): ReactNode {
  const neg = v < 0 && Number(Math.abs(v).toFixed(dec)) !== 0;
  return <span className={neg ? "neg" : undefined}>{fmtMoney(v, dec)}</span>;
}
