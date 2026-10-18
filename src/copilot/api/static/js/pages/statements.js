// Statements: accrual P&L, balance sheet and cash flow (chunk 12) with recorded adjustments
// (chunk 13). Data: /api/statements. The month list comes from the last-12-months response.
import { api } from "../api.js";
import { h, mount } from "../dom.js";
import { date, label, money, month, num, share } from "../fmt.js";
import { card, cardWith, loading, moneyCell, seg, table, term, warnings, download } from "../ui.js";

const PERIODS = [["month", "Month"], ["quarter", "Quarter"], ["ytd", "Year to date"], ["last_12_months", "Last 12 months"]];
const VIEWS = [["with_adjustments", "With adjustments"], ["as_imported", "As imported"]];
let sel = { period: "month", month: "", view: "with_adjustments" };
let months = null;

const WORKING = {
  receivables: "Customer invoices unpaid",
  inventory: "Stock",
  payables: "Supplier bills unpaid",
  gst_payable: "GST owed",
  cpf_payable: "CPF owed",
  unmatched_customer_receipts: "Customer payments not yet matched",
  unmatched_supplier_payments: "Supplier payments not yet matched",
};
// Lines with a glossary entry get an (i) icon.
const TERM_FOR = {
  receivables: "receivables", inventory: "stock", payables: "payables", gst_payable: "gst", cpf_payable: "cpf",
  unmatched_customer_receipts: "unmatched", unmatched_supplier_payments: "unmatched", accrued_costs: "accrued",
  retained_earnings: "retained", owner_drawings: "drawings", depreciation: "depreciation",
};
const lab = (key, text) => (TERM_FOR[key] ? term(text, TERM_FOR[key]) : text);
const OPEX = { payroll: "Payroll", rent: "Rent", utilities: "Utilities", software: "Software", other: "Other costs", depreciation: "Depreciation" };

function line(text, v, cls = "line") {
  return h("tr", { class: cls }, h("td", {}, text), moneyCell(v));
}
function group(text) {
  return h("tr", { class: "grp" }, h("td", { colspan: 2 }, text));
}

function pnl(p, r) {
  return table(
    ["", { text: "Amount", cls: "n" }],
    [
      line("Sales", p.revenue, ""),
      line("Cost of sales", p.cost_of_sales),
      line(term("Gross profit", "gross_profit"), p.gross_profit, "sub"),
      group("Operating costs"),
      Object.entries(p.operating_expenses).map(([k, v]) => line(lab(k, OPEX[k] || label(k)), v)),
      line("Total operating costs", p.total_operating_expenses, "sub"),
      line(term("Operating profit", "operating_profit"), p.operating_profit, "sub"),
      line("Other income", p.other_income),
      line("Interest", p.interest),
      line(term("Net profit", "net_profit"), p.net_profit, "total"),
      h("tr", { class: "ratio" }, h("td", {}, term("Gross / operating / net margin", "net_margin")), h("td", { class: "n" }, `${share(r.gross_margin)} / ${share(r.operating_margin)} / ${share(r.net_margin)}`)),
    ],
  );
}

function balanceSheet(b) {
  const L = (k, t) => line(lab(k, t), b[k]);
  return table(
    ["", { text: `At ${date(b.as_of)}`, cls: "n" }],
    [
      group("Assets"),
      L("cash", "Cash"),
      L("receivables", "Customer invoices unpaid"),
      L("inventory", "Stock"),
      L("unmatched_supplier_payments", "Supplier payments not yet matched"),
      L("fixed_assets_net", "Equipment and vehicles (after depreciation)"),
      line("Total assets", b.total_assets, "sub"),
      group("Liabilities"),
      L("payables", "Supplier bills unpaid"),
      L("gst_payable", "GST owed"),
      L("cpf_payable", "CPF owed"),
      L("unmatched_customer_receipts", "Customer payments not yet matched"),
      L("accrued_costs", "Accrued costs"),
      L("loans_due_within_12_months", "Loans due within 12 months"),
      L("loans_due_after_12_months", "Loans due after 12 months"),
      L("other_borrowings", "Other borrowings"),
      line("Total liabilities", b.total_liabilities, "sub"),
      group("Equity"),
      L("share_capital", "Share capital"),
      L("retained_earnings", "Retained earnings"),
      L("owner_drawings", "Owner drawings"),
      line("Total equity", b.total_equity, "total"),
    ],
  );
}

function cashFlow(c) {
  return table(
    ["", { text: "Amount", cls: "n" }],
    [
      line("Net profit", c.net_profit, ""),
      line(term("Add back depreciation", "depreciation"), c.add_depreciation),
      group(term("Working capital", "working_capital")),
      Object.entries(c.working_capital).map(([k, v]) => line(lab(k, WORKING[k] || label(k)), v)),
      line("Cash from operations", c.operating, "sub"),
      line("Investing", c.investing, "sub"),
      line("Loan principal repaid", c.financing_loan_principal),
      line("New borrowing", c.new_borrowing),
      line(term("Owner drawings", "drawings"), c.owner_drawings),
      line("Cash from financing", c.financing, "sub"),
      line("Net change in cash", c.net_change, "sub"),
      line("Opening cash", c.opening_cash),
      line("Closing cash", c.closing_cash, "total"),
    ],
  );
}

function checks(c) {
  return h(
    "div",
    {},
    h("div", { class: `check ${c.balanced ? "ok" : "bad"}` }, c.balanced ? "Balance sheet balances" : "Balance sheet does not balance", ` (difference ${money(c.balance_sheet_difference)})`),
    h("div", { class: `check ${c.cash_matches_bank ? "ok" : "bad"}` }, c.cash_matches_bank ? "Closing cash equals the bank" : "Closing cash differs from the bank", ` (difference ${money(c.closing_cash_minus_bank)})`),
  );
}

function adjustmentsCard(adj) {
  if (!adj || !adj.applied || !adj.applied.length) return null;
  return card(
    term("Recorded adjustments in this period", "adjustments"),
    `Net profit as imported ${money(adj.net_profit_as_imported)}; with adjustments ${money(adj.net_profit_with_adjustments)}`,
    table(
      ["Adjustment", "Month", "Reason given"],
      adj.applied.map((a) => h("tr", {}, h("td", {}, h("span", { class: "cn" }, a.description), h("span", { class: "cs" }, `${label(a.kind)} · ${a.id}`)), h("td", {}, month(a.month)), h("td", {}, a.reason))),
    ),
  );
}

function assetsAndLoans(v) {
  const assets = v.fixed_assets || [];
  const loans = v.loans || [];
  if (!assets.length && !loans.length) return null;
  return h(
    "div",
    { class: "split even" },
    card(
      "Equipment and vehicles",
      "Cost, depreciation so far and book value",
      table(
        ["Asset", "Bought", { text: "Cost", cls: "n" }, { text: "Book value", cls: "n" }],
        assets.map((a) => h("tr", {}, h("td", {}, a.name), h("td", {}, date(a.acquired_on)), moneyCell(a.cost), moneyCell(a.net_book_value))),
      ),
    ),
    card(
      "Loans",
      "Balance at the end of the period",
      table(
        ["Lender", { text: "Rate", cls: "n" }, { text: "Balance", cls: "n" }, { text: "Due in 12 months", cls: "n" }],
        loans.map((l) => h("tr", {}, h("td", {}, h("span", { class: "cn" }, l.lender), h("span", { class: "cs" }, l.id)), h("td", { class: "n" }, `${num(l.interest_rate_pct)}%`), moneyCell(l.balance), moneyCell(l.due_within_12_months))),
      ),
    ),
  );
}

export default {
  key: "statements",
  nav: "Statements",
  icon: "doc",
  title: "Financial statements",
  subtitle: "Profit and loss, balance sheet and cash flow on an accrual basis, built from your books.",
  endpoints: ["/api/statements"],
  async render(root, ctx) {
    mount(root, loading());
    if (!months) {
      const all = await api("/api/statements", { query: { period: "last_12_months", statement: "pnl" } });
      if (all.ok) months = all.data.value.months;
    }
    const res = await api("/api/statements", { query: { period: sel.period, month: sel.month, view: sel.view } });
    if (!ctx.isCurrent()) return;
    const pick = (k, v) => {
      sel = { ...sel, [k]: v };
      this.render(root, ctx);
    };
    const monthSelect = months
      ? h(
          "label",
          { class: "select" },
          h(
            "select",
            { "aria-label": "Month", on: { change: (ev) => pick("month", ev.target.value) } },
            h("option", { value: "", selected: sel.month === "" }, "Latest complete month"),
            months.slice().reverse().map((m) => h("option", { value: m, selected: sel.month === m }, month(m))),
          ),
        )
      : null;
    const controls = h(
      "div",
      { class: "ctl" },
      seg(PERIODS, sel.period, (v) => pick("period", v), "Period"),
      monthSelect,
      seg(VIEWS, sel.view, (v) => pick("view", v), "View"),
      res.ok ? download("/api/export/statements.xlsx", { period: sel.period, month: sel.month, view: sel.view }, "Download Excel") : null,
    );
    if (!res.ok) {
      mount(root, controls, cardWith("", "Statements not available", res.message, null));
      return;
    }
    const v = res.data.value;
    mount(
      root,
      controls,
      h(
        "p",
        { class: "note" },
        `${label(v.period)}: ${date(v.start)} to ${date(v.end)} · `,
        v.basis === "accrual" ? term("accrual basis", "basis_accrual") : `${v.basis} basis`,
        ` · ${v.view === "as_imported" ? "as imported (no adjustments)" : "with recorded adjustments"} · `,
        term(`current ratio ${num(v.ratios.current_ratio)}`, "current_ratio"),
      ),
      h(
        "div",
        { class: "split even" },
        cardWith("tone-doc", term("Profit and loss", "pnl"), "Accrual basis", null, pnl(v.pnl, v.ratios)),
        cardWith("tone-cash", term("Cash flow", "cash_flow"), term("Indirect method", "indirect"), null, cashFlow(v.cash_flow)),
      ),
      cardWith("tone-doc", term("Balance sheet", "balance_sheet"), null, null, balanceSheet(v.balance_sheet), checks(v.checks)),
      assetsAndLoans(v),
      adjustmentsCard(v.adjustments),
      warnings(res.data.warnings),
    );
  },
};
