import type { Metrics, Result } from "../model/types";
import { pathOf, strategyOf } from "./answer";
import { COLORS, fmtMoney, Money } from "./format";

type Row = { label: string; get: (m: Metrics) => number; lowerIsBetter: boolean };

const ROWS: Row[] = [
  { label: "Revenue", get: (m) => m.revenue, lowerIsBetter: false },
  { label: "Gross profit", get: (m) => m.grossProfit, lowerIsBetter: false },
  { label: "Profit", get: (m) => m.profit.mean, lowerIsBetter: false },
  { label: "Economic profit", get: (m) => m.economicProfit.mean, lowerIsBetter: false },
  { label: "Discounts given", get: (m) => m.discountsGiven, lowerIsBetter: true },
  { label: "Financing fees", get: (m) => m.financingFees, lowerIsBetter: true },
  { label: "Interest expense", get: (m) => m.interestExpense, lowerIsBetter: true },
  { label: "Churn cost", get: (m) => m.churnCost, lowerIsBetter: true },
  { label: "End receivables", get: (m) => m.endReceivables, lowerIsBetter: false },
  { label: "Peak credit drawn", get: (m) => m.peakCreditDrawn, lowerIsBetter: true },
];

/** Metric | selected strategy | do nothing | change, with the change coloured by whether it helps the owner. */
export default function Comparison({ result, strategyId }: { result: Result; strategyId: string }) {
  const sel = strategyOf(result, strategyId);
  const a = pathOf(result, sel.pathId).metrics;
  const b = pathOf(result, strategyOf(result, "S0").pathId).metrics;
  return (
    <div className="table-scroll">
      <table className="options">
        <caption className="sr-only">Financial results: {sel.name} against doing nothing</caption>
        <thead>
          <tr>
            <th scope="col">Metric (average over runs)</th>
            <th scope="col">{sel.name}</th>
            <th scope="col">Do nothing</th>
            <th scope="col">Change</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((r) => {
            const x = r.get(a);
            const y = r.get(b);
            const d = x - y;
            const better = r.lowerIsBetter ? d < 0 : d > 0;
            const worse = r.lowerIsBetter ? d > 0 : d < 0;
            const color = Math.abs(d) < 0.005 ? undefined : better ? COLORS.profit : worse ? COLORS.shock : undefined;
            return (
              <tr key={r.label}>
                <th scope="row">{r.label}</th>
                <td><Money v={x} /></td>
                <td><Money v={y} /></td>
                <td style={{ color, fontWeight: 600 }}>
                  {Math.abs(d) < 0.005 ? "—" : `${d > 0 ? "+" : "-"}${fmtMoney(Math.abs(d))}`}
                  {color ? <span className="sr-only">{better ? " (better)" : " (worse)"}</span> : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
