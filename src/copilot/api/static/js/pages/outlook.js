// Outlook: Worst / Expected / Best switch (14a), drivers with sources, 3-year figures, sales vs
// break-even line (14b), and the valuation card. Data: /api/model (all cases) and /api/valuation
// (all cases + 36 monthly break-even points). Switching the case only changes which of the
// already-returned cases is shown; valuation inputs are query parameters, nothing is saved.
import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { lineChart } from "../charts.js";
import { cap, date, isNeg, money, month, num, share } from "../fmt.js";
import { badge, cardWith, clamp, field, loading, moneyCell, more, seg, sumrow, table, term } from "../ui.js";

const CASES = [["worst", "Worst", "worst"], ["expected", "Expected", "expected"], ["best", "Best", "best"]];
const VAL_DEFAULTS = { discount_rate_pct: "", terminal_growth_pct: "", ebitda_multiple: "", owner_salary_monthly: "" };
let picked = "expected";
const DRIVER_TERMS = { sales_growth_pct: "sales_growth", cost_of_sales_pct: "cost_of_sales_pct", owner_drawings: "drawings" };
let valInputs = { ...VAL_DEFAULTS };

/** "measured: sales S$... vs ..." -> a short tag plus the detail in small text. */
function sourceCell(source) {
  const text = String(source || "");
  const i = text.indexOf(":");
  const head = (i > 0 ? text.slice(0, i) : text).trim();
  const detail = i > 0 ? text.slice(i + 1).trim() : "";
  const [tone, tag] = /^measured/i.test(head)
    ? ["info", "Measured"]
    : /assumption/i.test(head)
      ? ["warn", "Our assumption"]
      : /^saved/i.test(head)
        ? ["pos", "Saved by you"]
        : ["neu", head];
  return h("td", {}, h("span", { class: "src-tag" }, badge(tone, tag)), detail ? clamp(detail, 1, "cs") : null);
}

function driversTable(drivers) {
  return table(
    [term("Driver", "driver"), ...CASES.map(([k, t]) => ({ text: t, cls: `n ${k === picked ? "sel" : ""}` })), "Where it comes from"],
    drivers.map((d) =>
      h(
        "tr",
        {},
        h("td", {}, h("span", { class: "cn" }, DRIVER_TERMS[d.key] ? term(d.label, DRIVER_TERMS[d.key]) : d.label), h("span", { class: "cs" }, d.unit)),
        CASES.map(([k]) => h("td", { class: `n ${k === picked ? "sel" : ""}` }, d[k] === null || d[k] === undefined ? "—" : num(d[k]))),
        sourceCell(d.source),
      ),
    ),
  );
}

function yearsTable(model, c) {
  const last = model.actual_last_12_months;
  const cols = [["Last 12 months", h("span", { class: "cs" }, "actual")], ...c.years.map((y) => [`Year ${y.year}`, h("span", { class: "cs" }, y.months)])];
  const row = (label, get, cls = "") => h("tr", { class: cls }, h("td", {}, label), get(last, null), c.years.map((y) => get(y.pnl, y)));
  const m = (key) => (p) => moneyCell(p[key]);
  return table(
    ["", ...cols.map((t) => ({ text: t, cls: "n two-line" }))],
    [
      row("Sales", m("revenue")),
      row(term("Gross profit", "gross_profit"), m("gross_profit")),
      row("Operating costs", m("total_operating_expenses")),
      row(term("Operating profit", "operating_profit"), m("operating_profit"), "sub"),
      row(term("Net profit", "net_profit"), m("net_profit"), "total"),
      h("tr", {}, h("td", {}, "Cash at year end"), h("td", { class: "n muted" }, "—"), c.years.map((y) => moneyCell(y.balance_sheet.cash))),
    ],
    "yt",
  );
}

function breakEvenChart(be) {
  const pts = be.monthly;
  return [
    h("div", { class: "legend" }, h("span", {}, h("i", { class: "sw ln fc" }), "Projected monthly sales"), h("span", {}, h("i", { class: "sw ln gold" }), "Break-even sales")),
    lineChart({
      title: "Monthly sales vs break-even",
      labels: pts.map((p) => month(p.month)),
      series: [
        { name: "Sales", values: pts.map((p) => p.sales), cls: "fc" },
        { name: "Break-even", values: pts.map((p) => p.break_even_sales), cls: "gold" },
      ],
      xTicks: 4,
      height: 280,
      width: 460,
      includeZero: false,
    }),
    h("p", { class: "note" }, be.status),
  ];
}

function valuationForm(inputs, rerender, error) {
  const byKey = Object.fromEntries(inputs.map((i) => [i.key, i]));
  const mk = (key, pre, suf) => field(`v_${key}`, byKey[key] ? byKey[key].label : key, valInputs[key] || (byKey[key] ? byKey[key].value : ""), { pre, suf, hint: byKey[key] ? cap(byKey[key].source) : "", inputmode: "decimal" });
  const f = {
    discount_rate_pct: mk("discount_rate_pct", null, "%"),
    terminal_growth_pct: mk("terminal_growth_pct", null, "%"),
    ebitda_multiple: mk("ebitda_multiple", null, "×"),
    owner_salary_monthly: mk("owner_salary_monthly", "S$", "/month"),
  };
  const submit = (ev) => {
    ev.preventDefault();
    valInputs = Object.fromEntries(Object.entries(f).map(([k, x]) => [k, x.input.value.trim()]));
    rerender();
  };
  return h(
    "form",
    { on: { submit } },
    h("div", { class: "form four" }, Object.values(f).map((x) => x.el), h("div", { class: "acts" }, h("button", { class: "btn pri", type: "submit" }, "Update"), h("button", { class: "btn ghost", type: "button", on: { click: () => { valInputs = { ...VAL_DEFAULTS }; rerender(); } } }, "Reset to defaults"))),
    error ? h("p", { class: "ferr", role: "alert" }, error) : null,
  );
}

/** The reason's first clause ("Free cash flow in year 3 is -S$48,104.67"); full text on hover. */
function shortReason(text) {
  const t = String(text || "");
  const i = t.indexOf(":");
  return i > 0 ? t.slice(0, i) : t;
}

function valueCell(x) {
  if (x.equity_value !== null && x.equity_value !== undefined) return h("td", { class: "n" }, h("b", {}, money(x.equity_value, 0)));
  return h("td", { class: "nm", title: x.not_meaningful || "" }, "Not meaningful", h("small", {}, shortReason(x.not_meaningful)));
}

function answer(c) {
  const dcf = c.dcf.equity_value;
  const mult = c.multiple.equity_value;
  const x = `${num(c.multiple.multiple)}× year-1 EBITDA`;
  if (dcf && mult) return [`${c.name} case: about ${money(dcf, 0)} by discounted cash flow, or ${money(mult, 0)} at ${x}.`, null];
  if (dcf) return [`${c.name} case: about ${money(dcf, 0)} by discounted cash flow.`, `A multiple of EBITDA isn't meaningful: ${shortReason(c.multiple.not_meaningful)}.`];
  if (mult) return [`${c.name} case: about ${money(mult, 0)} at ${x}.`, `Discounted cash flow isn't meaningful: ${shortReason(c.dcf.not_meaningful)}.`];
  return [`${c.name} case: no meaningful value.`, c.dcf.not_meaningful];
}

let howOpen = false;

function valuationCard(val, rerender, error, notes) {
  const v = val.valuation;
  const c = v.cases[picked];
  const [main, why] = answer(c);
  const sens = Object.entries(c.sensitivity).map(([key, rows]) =>
    h(
      "tr",
      {},
      h("td", {}, (v.inputs.find((i) => i.key === key) || { label: key }).label),
      rows.map((r) => h("td", { class: "n" }, h("span", { class: "cs" }, num(r.input)), r.equity_value === null ? "Not meaningful" : money(r.equity_value, 0))),
    ),
  );
  const how = [
    h("p", { class: "note" }, "Discounted cash flow: the cash the business is projected to generate over 3 years plus a value for the years after, discounted back to today. Multiple: year-1 EBITDA (profit before interest, tax and depreciation) times a typical small-firm multiple. Both then add cash and subtract loans."),
    h(
      "div",
      { class: "split even" },
      h(
        "div",
        {},
        h("div", { class: "eyebrow", style: { "margin-bottom": "6px" } }, `${c.name} case: free cash flow`),
        table(
          ["", ...c.years.map((y) => ({ text: `Year ${y.year}`, cls: "n" }))],
          [
            h("tr", {}, h("td", {}, term("Free cash flow", "free_cash_flow")), c.years.map((y) => moneyCell(y.free_cash_flow))),
            h("tr", {}, h("td", {}, "Worth today"), c.years.map((y) => moneyCell(y.present_value))),
          ],
          "yt",
        ),
        c.dcf.terminal_share ? h("p", { class: "note", style: { "margin-top": "8px" } }, `${share(c.dcf.terminal_share, 0)} of the DCF value comes after year 3.`) : null,
      ),
      h(
        "div",
        {},
        h("div", { class: "eyebrow", style: { "margin-bottom": "6px" } }, `Cash and loans on ${date(v.bridge.as_of)}`),
        sumrow("Cash", money(v.bridge.cash)),
        sumrow("Loans", money(v.bridge.loans)),
        v.bridge.loan_list.map((l) => sumrow(`· ${l.lender} (${l.id})`, money(l.balance_at_start))),
        sumrow("Book equity (balance sheet)", money(v.book_equity)),
      ),
    ),
    h("div", { class: "eyebrow" }, `If an input changes (${c.name} case, equity value)`),
    table(["Input", "Lower", "Default", "Higher"], sens),
    h("div", { class: "eyebrow" }, "Change the inputs"),
    valuationForm(v.inputs, rerender, error),
    (notes || []).filter((n) => n !== v.disclaimer).map((n) => h("p", { class: "note" }, n)),
  ];
  return cardWith(
    "tone-value",
    term("What the business could be worth", "equity_value"),
    "An estimate from the projection, not a price",
    null,
    h("p", { class: "answer" }, main, why ? h("span", { class: "muted" }, why) : null),
    h(
      "div",
      { style: { "margin-top": "14px" } },
      table(
        ["Case", { text: term("Discounted cash flow", "dcf"), cls: "n" }, { text: term(`Multiple (${num(c.multiple.multiple)}× EBITDA)`, "ebitda_multiple"), cls: "n" }],
        CASES.map(([k, t]) => h("tr", { class: k === picked ? "best" : "" }, h("td", {}, h("span", { class: "cn" }, t)), valueCell(v.cases[k].dcf), valueCell(v.cases[k].multiple))),
      ),
    ),
    more("How this is estimated", how, howOpen || Boolean(error), (o) => { howOpen = o; }),
    h("p", { class: "disclaimer" }, v.disclaimer),
  );
}

export default {
  key: "outlook",
  nav: "Outlook",
  icon: "outlook",
  title: "Outlook",
  subtitle: "Three years ahead in a worst, expected and best case: profit, break-even and an estimated value.",
  endpoints: ["/api/model", "/api/valuation"],
  async render(root, ctx) {
    const rerender = () => this.render(root, ctx);
    mount(root, loading());
    const [modelRes, valRes] = await Promise.all([api("/api/model", { query: { case: "all" } }), api("/api/valuation", { query: { case: "all", ...valInputs } })]);
    if (!ctx.isCurrent()) return;
    if (!modelRes.ok) {
      mount(root, cardWith("", "Model not available", modelRes.message, null));
      return;
    }
    const model = modelRes.data.value;
    let val = valRes.ok ? valRes.data.value : null;
    let valError = valRes.ok ? null : valRes.message;
    if (!val) {
      // Out-of-range inputs: show the server's reason and the default valuation
      valInputs = { ...VAL_DEFAULTS };
      const again = await api("/api/valuation", { query: { case: "all" } });
      if (!ctx.isCurrent()) return;
      val = again.ok ? again.data.value : null;
      valError = valError || again.message;
    }
    const draw = () => {
      const c = model.cases[picked];
      const be = val ? val.break_even.cases[picked] : null;
      mount(
        root,
        h("div", { class: "ctl" }, seg(CASES, picked, (k) => { picked = k; draw(); }, "Case"), h("span", { class: "note" }, `Opens from the balance sheet of ${date(model.starts_from)}; ${model.basis} basis`)),
        h(
          "div",
          { class: "grid g4" },
          [
            ["Net profit, year 1", money(c.outlook.net_profit_by_year[0], 0), isNeg(c.outlook.net_profit_by_year[0])],
            ["Cash at end of year 1", money(c.outlook.cash_end_of_year[0], 0), isNeg(c.outlook.cash_end_of_year[0])],
            ["Lowest month-end cash", `${money(c.outlook.lowest_cash, 0)}`, isNeg(c.outlook.lowest_cash), month(c.outlook.lowest_cash_month)],
            ["First month below zero", c.outlook.first_month_below_zero ? month(c.outlook.first_month_below_zero) : "Never", Boolean(c.outlook.first_month_below_zero)],
          ].map(([lab, v, bad, foot]) => h("div", { class: "card kpi" }, h("div", { class: "kpi-h" }, lab), h("div", { class: `kpi-v ${bad ? "neg" : ""}` }, v), foot ? h("div", { class: "kpi-f" }, foot) : null)),
        ),
        cardWith("tone-forecast", term("What drives each case", "cases"), "Expected comes from your books; Worst and Best are a fixed step away", null, driversTable(model.drivers)),
        cardWith("tone-forecast", `${c.name} case: profit and cash by year`, null, null, yearsTable(model, c), more("About these figures", model.notes.map((n) => h("p", { class: "note" }, n)))),
        val
          ? h(
              "div",
              { class: "split even" },
              cardWith("tone-forecast", `${c.name} case: sales vs break-even`, "Break-even = monthly operating costs ÷ gross margin", be && be.first_month_reached ? badge("pos", `reached ${month(be.first_month_reached)}`) : badge("neg", `${be.months_below} months below`), breakEvenChart(be)),
              cardWith(
                "tone-cash",
                term("Break-even today", "break_even"),
                "Two bases: cash (last 3 months) and accrual (last 12 months)",
                null,
                ["today_cash", "today_accrual"].map((k) => {
                  const t = val.break_even[k];
                  return h("div", { style: { "margin-bottom": "12px" } }, h("div", { class: "eyebrow" }, `${t.basis} basis, ${date(t.period_start)} to ${date(t.period_end)}`), sumrow("Break-even sales a month", money(t.break_even_monthly_sales), "big"), sumrow("Average sales a month", money(t.avg_monthly_sales)), sumrow("Headroom", money(t.headroom)), sumrow("Gross margin", share(t.gross_margin)));
                }),
              ),
            )
          : null,
        val ? valuationCard(val, rerender, valError, valRes.ok ? valRes.data.warnings : []) : cardWith("", "Valuation not available", valError, null),
      );
    };
    draw();
  },
};
