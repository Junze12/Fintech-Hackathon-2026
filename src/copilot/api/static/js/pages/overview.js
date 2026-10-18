// Overview: KPI tiles, one cash chart (13-week forecast + P10-P90 band + floor + events),
// ranked alerts and how customers pay. Data: /api/dashboard and /api/stress.
import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { lineChart } from "../charts.js";
import { date, day, isNeg, isZero, money, num, pct, share } from "../fmt.js";
import { badge, cardWith, clamp, kpi, loading, moneyCell, panelMessage, SEVERITY_TONE, table, term, warnings, download } from "../ui.js";

function panel(p) {
  return p && p.ok ? p.data : null;
}

function cashChart(stress, forecast, alerts) {
  if (!stress) return panelMessage("The stress test isn't available for this sign-in.");
  const daily = stress.daily;
  const dates = daily.map((d) => d.date);
  const markers = [];
  const seen = new Set();
  for (const a of alerts ? alerts.alerts.value : []) {
    const i = dates.indexOf(a.event_date);
    if (i >= 0 && !seen.has(a.event_date)) {
      seen.add(a.event_date);
      markers.push({ index: i, label: `${day(a.event_date)}: ${a.title}`, short: day(a.event_date), row: markers.length % 2 });
    }
  }
  if (forecast) {
    const i = dates.indexOf(forecast.low_point.date);
    if (i >= 0 && !seen.has(forecast.low_point.date)) markers.push({ index: i, label: `Lowest point ${day(forecast.low_point.date)}: ${money(forecast.low_point.balance)}`, short: `Low ${day(forecast.low_point.date)}`, row: markers.length % 2 });
  }
  const refs = [];
  const floor = alerts ? alerts.floor : null;
  if (floor && !isZero(floor)) refs.push({ value: floor, label: `Your floor ${money(floor, 0)}` });
  return [
    h(
      "div",
      { class: "legend" },
      h("span", {}, h("i", { class: "sw ln fc" }), "Forecast"),
      h("span", {}, h("i", { class: "sw band" }), term("Likely range (P10–P90 of 2,000 runs)", "band")),
      refs.length ? h("span", {}, h("i", { class: "sw dash" }), term("Cash floor", "cash_floor")) : null,
      h("span", {}, h("i", { class: "sw neg" }), "Alert dates"),
    ),
    lineChart({
      title: "Cash balance, next 13 weeks",
      labels: dates.map(day),
      tips: dates.map(date),
      series: [{ name: "Forecast", values: daily.map((d) => d.forecast), cls: "fc" }],
      band: { lo: daily.map((d) => d.p10), hi: daily.map((d) => d.p90), name: "P10–P90" },
      refs,
      markers,
      height: 280,
    }),
  ];
}

function customersCard(ageing, concentration) {
  if (!ageing) return panelMessage("Customer payment data isn't available for this sign-in.");
  const rows = ageing.customers.map((c) =>
    h(
      "tr",
      {},
      h("td", {}, h("span", { class: "cn" }, c.name), h("span", { class: "cs" }, `${c.paid_invoices_matched} paid invoices matched`)),
      h("td", { class: "n" }, `${num(c.avg_days_late)} days`),
      h("td", { class: "n" }, c.paid_by_due_pct === null ? "—" : pct(c.paid_by_due_pct)),
      moneyCell(c.outstanding),
      h("td", { class: `n ${isZero(c.overdue) ? "" : "neg"}` }, money(c.overdue)),
    ),
  );
  const top = concentration && concentration.largest;
  return [
    table(["Customer", { text: term("Avg. days late", "days_late"), cls: "n" }, { text: term("Paid by due date", "paid_by_due"), cls: "n" }, { text: "Unpaid", cls: "n" }, { text: term("Overdue", "overdue"), cls: "n" }], rows),
    top ? h("p", { class: "note", style: { "margin-top": "10px" } }, `Largest customer: ${top.name}, ${share(top.share)} of invoiced sales last quarter.`) : null,
  ];
}

function alertsList(alerts) {
  if (!alerts) return panelMessage("Alerts aren't available for this sign-in.");
  if (!alerts.alerts.value.length) return h("p", { class: "note" }, "No alerts. Cash stays above your floor for the next 13 weeks.");
  return h(
    "div",
    { class: "alerts" },
    alerts.alerts.value.map((a) => h("div", { class: `alert sev-${SEVERITY_TONE[a.severity] || "neu"}` }, badge(SEVERITY_TONE[a.severity] || "neu", a.severity), h("div", {}, h("b", {}, a.title), clamp(a.message, 1)))),
  );
}

export default {
  key: "overview",
  nav: "Overview",
  icon: "home",
  title: "Overview",
  subtitle: "How is the business doing, and will cash last the next 13 weeks?",
  endpoints: ["/api/dashboard", "/api/stress"],
  async render(root, ctx) {
    mount(root, loading());
    const [dash, stressRes] = await Promise.all([api("/api/dashboard"), api("/api/stress", { query: { best_plan: "false" } })]);
    if (!ctx.isCurrent()) return;
    ctx.setPending(dash.pending);
    const p = dash.panels;
    const cash = panel(p.cash);
    const forecast = panel(p.forecast);
    const alerts = panel(p.alerts);
    const metrics = panel(p.metrics);
    const ageing = panel(p.ageing);
    const health = panel(p.health);
    const stress = stressRes.ok ? stressRes.data.value : null;

    const low = forecast && forecast.value.low_point;
    const runway = metrics && metrics.runway.value;
    const recv = ageing && ageing.receivables.value;
    const tiles = h(
      "div",
      { class: "grid g4" },
      cash ? kpi("cash", term("Cash today", "cash_today"), money(cash.value.total), cash.value.accounts.map((a) => `${a.name} ${money(a.balance)}`).join(" · ")) : kpi("cash", term("Cash today", "cash_today"), "—", p.cash.message),
      low ? kpi("alert", term("Lowest point", "lowest_point"), money(low.balance), `In the next 13 weeks: ${date(low.date)} (week ${low.week})`, isNeg(low.balance) ? "neg" : "") : kpi("alert", term("Lowest point", "lowest_point"), "—", p.forecast.message),
      stress ? kpi("chart", term("Chance cash lasts", "survival"), pct(stress.survival_pct), stress.failures.runs_failing ? `Share of ${stress.runs.toLocaleString("en")} runs that never go below zero (target ${stress.target_pct}%). Failures start most often ${day(stress.failures.most_likely_day)}` : `Share of ${stress.runs.toLocaleString("en")} runs that never go below zero (target ${stress.target_pct}%)`, stress.meets_target ? "" : "warn") : kpi("chart", term("Chance cash lasts", "survival"), "—", stressRes.message),
      recv ? kpi("overdue", term("Overdue invoices", "overdue"), money(recv.overdue), `${share(recv.overdue_share)} of ${money(recv.total)} customers owe`, isZero(recv.overdue) ? "" : "neg") : kpi("overdue", term("Overdue invoices", "overdue"), "—", p.ageing.message),
    );

    const period = metrics ? metrics.period.value : null;
    const wc = metrics ? metrics.working_capital.value : null;
    const be = health ? health.break_even.value : null;
    const dscr = health ? health.debt_service_cover.value : null;
    const strip = metrics
      ? cardWith(
          "tone-cash",
          "Key measures",
          `${date(dash.metrics_period.start)} to ${date(dash.metrics_period.end)}; margins on cash basis, days on invoice basis`,
          null,
          h(
            "div",
            { class: "health" },
            [
              [term("Gross margin", "gross_margin"), share(period.gross_margin), "Sales minus cost of goods"],
              [term("Operating margin", "operating_margin"), share(period.operating_margin), "After running costs"],
              [term("Runway", "runway"), runway && runway.months !== null ? `${num(runway.months)} months` : "—", runway ? runway.status : ""],
              [term("Days to get paid (DSO)", "dso"), `${num(wc.dso)} days`, `Days to pay suppliers: ${num(wc.dpo)}`],
              [term("Debt cover (DSCR)", "dscr"), dscr && dscr.dscr !== null ? `${num(dscr.dscr)}×` : "—", "Cash available / loan repayments"],
              [term("Break-even sales", "break_even"), be && be.break_even_monthly_sales ? money(be.break_even_monthly_sales) : "—", be ? `a month; headroom ${money(be.headroom)}` : ""],
            ].map(([lab, val, hint]) => h("div", { class: "hi" }, h("span", { class: "lab" }, lab), h("span", { class: "val" }, val), h("span", { class: "hint" }, hint))),
          ),
          warnings(runway && runway.months !== null && low && isNeg(low.balance) ? ["Runway averages the last 3 months, so it can look long while a single large bill still takes the account below zero within weeks: see the chart."] : []),
        )
      : panelMessage(p.metrics.message);

    mount(
      root,
      tiles,
      cardWith("tone-forecast", term("Cash over the next 13 weeks", "forecast"), stress ? `Forecast from ${date(stress.as_of)} to ${date(stress.horizon_end)}; the band shows where 80% of simulated customer-payment timings land` : "", forecast ? download("/api/export/forecast.xlsx", null, "Download forecast") : null, cashChart(stress, forecast && forecast.value, alerts)),
      strip,
      cardWith("tone-people", "How your customers pay", "Average days paid after the due date, and how often they pay on time", null, customersCard(recv, metrics && metrics.concentration.value)),
      cardWith("tone-risk", "Alerts", "Most urgent first", null, alertsList(alerts)),
    );
  },
};
