import type { Result, Scenario } from "../model/types";
import { pathOf, strategyOf } from "./answer";
import { fmtPct } from "./format";

/** How each customer pays: simulated results for the selected strategy next to the inputs behind them. */
export default function PaymentCard({ result, scenario, strategyId }: { result: Result; scenario: Scenario; strategyId: string }) {
  const sel = strategyOf(result, strategyId);
  const stats = pathOf(result, sel.pathId).customerStats;
  return (
    <section className="panel" aria-labelledby="pay-title">
      <h2 id="pay-title">How your customers pay</h2>
      <p className="muted small-text">
        Simulated for: {sel.name}. Each unpaid invoice has a daily chance of being paid, about 1 ÷ the expected days to
        pay, raised by any collection action you take. Offer acceptance and churn are also chance events.
      </p>
      <div className="table-scroll">
        <table className="options">
          <thead>
            <tr>
              <th scope="col">Customer</th>
              <th scope="col">Expected days to pay (input)</th>
              <th scope="col">Average days to pay (simulated)</th>
              <th scope="col">Invoices paid within the horizon</th>
              <th scope="col">Paid by due date</th>
              <th scope="col">Chance of taking a discount offer</th>
              <th scope="col">Chance of losing them</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((c, i) => (
              <tr key={c.customerId}>
                <th scope="row">{c.customerName}</th>
                <td>{scenario.customers[i].meanDaysToPay}</td>
                <td>{c.avgDaysToPay === null ? "—" : c.avgDaysToPay.toFixed(1)}</td>
                <td>{fmtPct(c.paidShare)}</td>
                <td>{c.paidByDueShare === null ? "—" : fmtPct(c.paidByDueShare)}</td>
                <td>{fmtPct(c.offerAcceptProb)}</td>
                <td>{fmtPct(c.churnProb)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
