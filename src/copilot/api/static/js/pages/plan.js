// Cash plan: will cash last (16a), where the gap comes from, every plan compared and the best one
// (16b), financing for what's left (4c). Data: /api/stress (without its own plan search),
// /api/plans and /api/dashboard (financing). The inputs are query parameters; nothing is saved.
import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { lineChart, waterfall } from "../charts.js";
import { date, day, money, pct } from "../fmt.js";
import { badge, cardWith, clamp, field, loading, moneyCell, more, panelMessage, sumrow, table, term } from "../ui.js";

const DEFAULTS = { target_pct: "95", shock_amount: "0", shock_date: "", chase_on_time_pct: "50", customer_loss_pct: "0" };
let inputs = { ...DEFAULTS };
let scoringOpen = false;

function form(rerender, error) {
  const f = {
    target_pct: field("target_pct", "Survival target", inputs.target_pct, { suf: "%", hint: "80 to 99", inputmode: "numeric" }),
    shock_amount: field("shock_amount", "Extra cash shock", inputs.shock_amount, { pre: "S$", hint: "A one-off payment or loss to test", inputmode: "decimal" }),
    shock_date: field("shock_date", "Shock date", inputs.shock_date, { type: "date", hint: "Empty = the riskiest day" }),
    chase_on_time_pct: field("chase_on_time_pct", "Chance a chased invoice is paid on time", inputs.chase_on_time_pct, { suf: "%", inputmode: "numeric" }),
    customer_loss_pct: field("customer_loss_pct", "Chance of losing a chased customer", inputs.customer_loss_pct, { suf: "%", inputmode: "numeric" }),
  };
  const submit = (ev) => {
    ev.preventDefault();
    inputs = Object.fromEntries(Object.entries(f).map(([k, x]) => [k, x.input.value.trim()]));
    rerender();
  };
  return h(
    "form",
    { on: { submit } },
    h(
      "div",
      { class: "form" },
      Object.values(f).map((x) => x.el),
      h("div", { class: "acts" }, h("button", { class: "btn pri", type: "submit" }, "Update"), h("button", { class: "btn ghost", type: "button", on: { click: () => { inputs = { ...DEFAULTS }; rerender(); } } }, "Reset to defaults")),
    ),
    error ? h("p", { class: "ferr", role: "alert" }, error) : null,
    h("p", { class: "note", style: { "margin-top": "10px" } }, "What-if inputs for this page only. Nothing is saved or applied."),
  );
}

/** Jun Ze's badge; the server decides the verdict (meets target / at least 50% / below 50%). */
const VERDICT = { survives: ["pos", "✔ Survives"], at_risk: ["warn", "▲ At risk"], fails: ["neg", "✖ Fails"] };
// No badge (rather than a broken page) if the server is older than this page.
const verdictBadge = (v) => (VERDICT[v] ? h("div", { class: "verdict" }, badge(...VERDICT[v])) : null);

function headline(st, best) {
  const short = st.meets_target
    ? st.headline.line1
    : `Without action you'll be ${money(st.bridge.gap)} short on ${date(st.bridge.day)} in a bad run.`;
  const plan = best
    ? `Best plan: ${best.actions.length} step${best.actions.length === 1 ? "" : "s"}, ${pct(best.survival_pct)} of runs stay above zero, costing ${money(best.cost_vs_nothing)}.`
    : null;
  return h(
    "section",
    { class: `card ${st.meets_target ? "tint-good" : "tint-warn"}` },
    h("div", { class: "card-h" }, h("div", { class: "t" }, h("h2", {}, "Will cash last?"), h("p", {}, `${st.runs.toLocaleString("en")} simulated runs to ${date(st.horizon_end)}; only the timing of customer payments is random`))),
    h(
      "div",
      { class: "grid g3" },
      h("div", {}, h("div", { class: "eyebrow" }, term("Doing nothing", "survival")), h("div", { class: "big-n" }, pct(st.survival_pct)), h("p", { class: "note" }, `of runs stay above ${money(st.floor, 0)} (target ${st.target_pct}%)`), verdictBadge(st.verdict)),
      best ? h("div", {}, h("div", { class: "eyebrow" }, term("With the best plan", "best_plan")), h("div", { class: "big-n" }, pct(best.survival_pct)), h("p", { class: "note" }, `costs ${money(best.cost_vs_nothing)} vs doing nothing`), verdictBadge(best.verdict)) : h("div", {}),
      h("div", {}, h("div", { class: "eyebrow" }, term("Extra cash needed to hit the target", "extra_buffer")), h("div", { class: "big-n" }, money(st.extra_buffer)), h("p", { class: "note" }, st.largest_survivable_shock ? `Largest extra shock you can absorb: ${money(st.largest_survivable_shock)}` : "Without action, no extra shock is survivable")),
    ),
    h("div", { style: { "margin-top": "16px" } }, h("p", { class: "headline" }, short), plan ? h("p", { class: "headline" }, plan) : null),
  );
}

/** The shock curve only carries information when survival changes with the shock size. */
function curveCard(st) {
  if (new Set(st.curve.map((c) => c.survival_pct)).size < 2) return null;
  return cardWith(
    "tone-forecast",
    "How much shock can you take?",
    "Share of runs that stay above the floor, by the size of an extra one-off payment or loss",
    null,
    lineChart({
      title: "Survival by shock size",
      labels: st.curve.map((c) => money(c.shock, 0)),
      series: [{ name: "Survival", values: st.curve.map((c) => c.survival_pct), cls: "brand" }],
      refs: [{ value: String(st.target_pct), label: `Target ${st.target_pct}%` }],
      yFormat: (v) => `${v}%`,
      valueFormat: pct,
      xTicks: 6,
      height: 240,
    }),
  );
}

function planCell(row, best) {
  if (row.recommended && best) {
    return h("td", {}, h("span", { class: "cn" }, badge("pos", "best plan")), h("ol", { class: "steps" }, best.actions.map((a) => h("li", {}, a))));
  }
  return h("td", {}, clamp(row.name, 2, "cn"));
}

function optionsTable(pl) {
  // Best plan, then the other plans that meet the target, then the rest (API order within each).
  const rows = [
    ...pl.table.filter((r) => r.recommended),
    ...pl.table.filter((r) => !r.recommended && r.meets_target),
    ...pl.table.filter((r) => !r.recommended && !r.meets_target),
  ];
  return table(
    ["Plan", { text: term("Survival", "survival"), cls: "n" }, term("Target", "target"), { text: term("Cost", "plan_cost"), cls: "n" }, { text: term(`Short on ${day(pl.risk_day)}`, "short_on"), cls: "n" }],
    rows.map((r) =>
      h(
        "tr",
        { class: r.recommended ? "best" : "" },
        planCell(r, pl.best),
        h("td", { class: "n" }, pct(r.survival_pct)),
        h("td", {}, r.meets_target ? badge("pos", "meets target") : badge("neu", "below target")),
        moneyCell(r.cost_vs_nothing),
        moneyCell(r.gap_on_risk_day),
      ),
    ),
  );
}

function bestPlan(pl) {
  const b = pl.best;
  if (!b) return h("p", { class: "note" }, "No plan reaches the target.");
  const line = b.credit_line;
  const daily = pl.best_daily || [];
  return [
    h("ol", { class: "list" }, b.actions.map((a) => h("li", {}, a))),
    h(
      "div",
      { class: "split even", style: { "margin-top": "16px" } },
      h(
        "div",
        {},
        sumrow("Survival with this plan", pct(b.survival_pct), "big"),
        sumrow("Lowest likely cash", `${money(b.low_point)} on ${date(b.low_point_date)}`),
        line ? sumrow(term("Credit line limit", "credit_line"), money(line.limit)) : null,
        line ? sumrow("Still drawn at the end (typical / 1 run in 10)", `${money(line.drawn_at_end_p50)} / ${money(line.drawn_at_end_p90)}`) : null,
        b.loan ? sumrow("Loan", `${b.loan.name || b.loan.product_id}: ${money(b.loan.amount)}`) : null,
      ),
      h(
        "div",
        {},
        h("div", { class: "eyebrow", style: { "margin-bottom": "4px" } }, "What it costs"),
        (pl.cost_bridge || []).filter((c) => c.kind !== "total").map((c) => sumrow(c.label, money(c.amount))),
        sumrow("Total vs doing nothing", money(b.cost_vs_nothing), "big"),
      ),
    ),
    daily.length
      ? h(
          "div",
          { style: { "margin-top": "16px" } },
          h("div", { class: "legend" }, h("span", {}, h("i", { class: "sw ln fc" }), "Forecast without action"), h("span", {}, h("i", { class: "sw band-b" }), "Cash with the plan (P10–P90)"), h("span", {}, h("i", { class: "sw brand" }), "With the plan (typical)")),
          lineChart({
            title: "Cash with the best plan",
            labels: daily.map((d) => day(d.date)),
            tips: daily.map((d) => date(d.date)),
            series: [
              { name: "Without action", values: daily.map((d) => d.forecast), cls: "fc thin" },
              { name: "With plan (P50)", values: daily.map((d) => d.p50), cls: "brand" },
            ],
            band: { lo: daily.map((d) => d.p10), hi: daily.map((d) => d.p90), name: "With plan P10–P90", cls: "brand" },
            height: 230,
          }),
        )
      : null,
    h("p", { class: "disclaimer" }, pl.disclaimer),
  ];
}

function financing(fin) {
  const v = fin.value;
  const need = v.need && v.need.need;
  const facts = need
    ? h(
        "div",
        { class: "facts" },
        h("div", {}, h("span", {}, term("Amount to borrow", "funding_need")), h("b", {}, money(need.amount))),
        h("div", {}, h("span", {}, "From"), h("b", {}, date(need.draw_date))),
        h("div", {}, h("span", {}, "For"), h("b", {}, `${need.duration_is_lower_bound ? "at least " : ""}${need.duration_days} days`)),
      )
    : h("p", { class: "note" }, "No borrowing needed: the steps without borrowing close the gap.");
  const steps = v.need && v.need.plan_steps && v.need.plan_steps.length
    ? h("div", { style: { "margin-bottom": "12px" } }, h("div", { class: "eyebrow" }, "Assumes these steps first"), h("ol", { class: "steps" }, v.need.plan_steps.map((x) => h("li", {}, x))))
    : null;
  const quotes = (v.ranked || []).map((r) =>
    h(
      "tr",
      { class: r.rank === 1 ? "best" : "" },
      h("td", {}, h("span", { class: "cn" }, r.quote.product_name, r.rank === 1 ? " " : null, r.rank === 1 ? badge("pos", "best fit") : null), h("span", { class: "cs" }, r.quote.lender)),
      moneyCell(r.quote.amount),
      h("td", { class: "n" }, `${r.quote.term_months} mo`),
      moneyCell(r.quote.total_cost),
      h("td", { class: "n" }, pct(r.quote.eir_pct)),
    ),
  );
  const notEligible = (v.eligibility || []).filter((e) => !e.eligible);
  return cardWith(
    "tone-fin",
    "Financing for the gap that's left",
    "Only for what the steps without borrowing don't cover",
    null,
    facts,
    steps,
    quotes.length ? table(["Product", { text: "Borrow", cls: "n" }, { text: "Term", cls: "n" }, { text: term("Total cost", "total_cost"), cls: "n" }, { text: term("Effective rate", "eir"), cls: "n" }], quotes) : null,
    notEligible.length
      ? more(`Not eligible (${notEligible.length})`, h("ul", { class: "steps" }, notEligible.map((e) => h("li", {}, `${e.product_name} (${e.lender}): ${e.reasons.join("; ")}`))))
      : null,
    h("p", { class: "disclaimer" }, v.disclaimer),
  );
}

export default {
  key: "plan",
  nav: "Cash plan",
  icon: "plan",
  title: "Cash plan",
  subtitle: "How likely is a cash shortfall, and which actions close the gap at the lowest cost?",
  endpoints: ["/api/stress", "/api/plans", "/api/dashboard"],
  async render(root, ctx) {
    const rerender = () => this.render(root, ctx);
    mount(root, loading("Simulating the next 13 weeks and comparing every plan… this takes a few seconds."));
    const q = { ...inputs };
    let st, pl, dash;
    try {
      [st, pl, dash] = await Promise.all([
        api("/api/stress", { query: { target_pct: q.target_pct, shock_amount: q.shock_amount, shock_date: q.shock_date, best_plan: "false" } }),
        api("/api/plans", { query: q }),
        api("/api/dashboard"),
      ]);
    } catch (e) {
      if (!ctx.isCurrent()) return;
      mount(root, cardWith("", "What-if inputs", null, null, form(rerender, e.message)));
      return;
    }
    if (!ctx.isCurrent()) return;
    const error = !st.ok ? st.message : !pl.ok ? pl.message : null;
    if (error) {
      mount(root, cardWith("", "What-if inputs", null, null, form(rerender, error)));
      return;
    }
    const sv = st.data.value;
    const pv = pl.data.value;
    mount(
      root,
      headline(sv, pv.best),
      cardWith(
        "tone-risk",
        term("Where the gap comes from", "gap_bridge"),
        `Cash today, what goes out and comes in up to ${date(sv.bridge.day)} (the riskiest day), and a margin for a bad run`,
        null,
        waterfall(sv.bridge.steps, { title: "Gap bridge" }),
        h("div", { class: "facts", style: { "margin-top": "8px", "margin-bottom": "0" } }, h("div", {}, h("span", {}, "Worst likely balance"), h("b", {}, money(sv.bridge.worst_likely))), h("div", {}, h("span", {}, "Gap to close"), h("b", {}, money(sv.bridge.gap)))),
      ),
      curveCard(sv),
      cardWith(
        "tone-plan",
        "Options compared",
        `${pv.plans_compared} plans scored on the same ${pv.runs.toLocaleString("en")} runs; the best one reaches the target at the lowest cost`,
        null,
        optionsTable(pv),
        more("How plans are scored", h("ul", { class: "steps" }, pv.assumptions.map((a) => h("li", {}, a))), scoringOpen, (o) => { scoringOpen = o; }),
      ),
      cardWith("tone-plan tint-good", term("Best plan", "best_plan"), null, null, bestPlan(pv)),
      cardWith("", "What-if inputs", null, null, form(rerender, null)),
      dash.panels.financing.ok ? financing(dash.panels.financing.data) : panelMessage(dash.panels.financing.message),
    );
  },
};
