// Books check: reconciliation exceptions (15), receivables / payables ageing (8), recorded
// adjustments, saved forecast assumptions and payments waiting for a label (13).
// Data: /api/reconciliation, /api/dashboard (ageing), /api/adjustments. Read-only: fixes go
// through the chat, where the owner confirms them.
import { api } from "../api.js";
import { h, icon, mount } from "../dom.js";
import { maxOf, meter } from "../charts.js";
import { date, label, money, month } from "../fmt.js";
import { badge, cardWith, clamp, kpi, loading, moneyCell, panelMessage, seg, SEVERITY_TONE, table, term, warnings } from "../ui.js";

const LEVELS = [["low", "All"], ["medium", "Medium and high"], ["high", "High only"]];
let minSeverity = "low";

function exceptionsTable(v) {
  if (!v.exceptions.length) return h("p", { class: "note" }, "Nothing to check at this level.");
  return table(
    [term("Severity", "severity"), "What", { text: "At stake", cls: "n" }, "Why, and what to do"],
    v.exceptions.map((x) =>
      h(
        "tr",
        {},
        h("td", {}, badge(SEVERITY_TONE[x.severity] || "neu", x.severity)),
        h("td", {}, h("span", { class: "cn" }, label(x.kind)), h("span", { class: "cs" }, [x.date ? date(x.date) : null, x.counterparty_name].filter(Boolean).join(" · "))),
        moneyCell(x.amount),
        h("td", { class: "why" }, clamp(x.reason, 2), h("span", { class: "next" }, icon("send", 13), x.next_step)),
      ),
    ),
  );
}

function ageingCard(title, a) {
  const max = maxOf(a.buckets.map((b) => b.amount));
  return cardWith(
    "tone-check",
    title,
    `${money(a.total)} unpaid on ${date(a.as_of)}, ${money(a.overdue)} overdue`,
    null,
    h("div", { class: "bridge" }, a.buckets.map((b) => h("div", { class: "brow" }, h("span", { class: "lb" }, `${b.label} (${b.count})`), meter(b.amount, max, b.bucket === "not_due" ? "" : "neg"), h("span", { class: "v" }, money(b.amount))))),
    a.oldest_overdue.length
      ? h(
          "div",
          { style: { "margin-top": "12px" } },
          table(
            ["Oldest overdue", "Due", { text: "Days", cls: "n" }, { text: "Unpaid", cls: "n" }],
            a.oldest_overdue.map((d) => h("tr", {}, h("td", {}, h("span", { class: "cn" }, d.number), h("span", { class: "cs" }, d.counterparty_name)), h("td", {}, date(d.due_date)), h("td", { class: "n" }, String(d.days_overdue)), moneyCell(d.outstanding))),
          ),
        )
      : null,
  );
}

function adjustmentsCard(adj) {
  if (!adj) return null;
  const open = Array.isArray(adj.open_months) ? adj.open_months.map(month).join(", ") : adj.open_months.none;
  return cardWith(
    "tone-doc",
    "Adjustments and saved assumptions",
    `Months open for adjustments: ${open}. Drafting, applying or undoing happens in the chat with a confirmation code.`,
    null,
    adj.adjustments.length
      ? table(
          ["Adjustment", "Month", "Status", "Reason given"],
          adj.adjustments.map((a) => h("tr", {}, h("td", {}, h("span", { class: "cn" }, a.description), h("span", { class: "cs" }, a.id)), h("td", {}, month(a.month)), h("td", {}, badge(a.status === "applied" ? "pos" : "neu", a.status)), h("td", {}, a.reason))),
        )
      : h("p", { class: "note" }, "No adjustments recorded."),
    h("div", { class: "eyebrow", style: { margin: "16px 0 6px" } }, "Saved forecast assumptions"),
    adj.saved_assumptions.length
      ? table(
          ["Assumption", "Detail", "Status", "Reason given"],
          adj.saved_assumptions.map((a) =>
            h("tr", {}, h("td", {}, label(a.kind)), h("td", {}, [a.customer, a.days !== null ? `${a.days} days` : null, a.category, a.monthly_amount !== null ? `${money(a.monthly_amount)} a month` : null, a.start ? `from ${date(a.start)}` : null].filter(Boolean).join(" · ")), h("td", {}, badge(a.status === "active" ? "pos" : "neu", a.status)), h("td", {}, a.reason)),
          ),
        )
      : h("p", { class: "note" }, "No saved assumptions."),
    h("div", { class: "eyebrow", style: { margin: "16px 0 6px" } }, "Payments waiting for a label"),
    adj.uncategorised_payments.length
      ? table(
          ["Payment", "Date", { text: "Amount", cls: "n" }, "Bank description"],
          adj.uncategorised_payments.map((t) => h("tr", {}, h("td", {}, t.transaction_id), h("td", {}, date(t.date)), moneyCell(t.amount), h("td", {}, t.description))),
        )
      : h("p", { class: "note" }, "None in the open months."),
  );
}

export default {
  key: "books",
  nav: "Books check",
  icon: "check",
  title: "Books check",
  subtitle: "Do the books match the bank and supplier statements? Unpaid invoices and bills by age, and your recorded corrections.",
  endpoints: ["/api/reconciliation", "/api/dashboard", "/api/adjustments"],
  async render(root, ctx) {
    mount(root, loading());
    const [rec, dash, adj] = await Promise.all([api("/api/reconciliation", { query: { min_severity: minSeverity } }), api("/api/dashboard"), api("/api/adjustments")]);
    if (!ctx.isCurrent()) return;
    ctx.setPending(dash.pending);
    const ageing = dash.panels.ageing.ok ? dash.panels.ageing.data : null;
    const pick = (v) => {
      minSeverity = v;
      this.render(root, ctx);
    };
    let recBlock;
    if (rec.ok) {
      const v = rec.data.value;
      recBlock = [
        h(
          "div",
          { class: "grid g4" },
          kpi("alert", term("High severity", "severity"), String(v.counts.high), `${money(v.amount_by_severity.high)} at stake`, v.counts.high ? "neg" : ""),
          kpi("alert", "Medium severity", String(v.counts.medium), `${money(v.amount_by_severity.medium)} at stake`, v.counts.medium ? "warn" : ""),
          kpi("check", "Low severity", String(v.counts.low), `${money(v.amount_by_severity.low)} at stake`),
          kpi("doc", "Transactions", String(v.checked.transactions), `Checked, plus ${v.checked.invoices} invoices, ${v.checked.bills} bills and ${v.checked.statement_lines} supplier statement lines`),
        ),
        cardWith("tone-risk", "Things to check", `As of ${date(v.as_of)}; highest first`, seg(LEVELS, minSeverity, pick, "Severity"), exceptionsTable(v), warnings(rec.data.warnings)),
      ];
    } else {
      recBlock = panelMessage(rec.message);
    }
    mount(
      root,
      recBlock,
      ageing ? h("div", { class: "split even" }, ageingCard("Customer invoices by age", ageing.receivables.value), ageingCard("Supplier bills by age", ageing.payables.value)) : panelMessage(dash.panels.ageing.message),
      adj.ok ? adjustmentsCard(adj.data) : panelMessage(adj.message),
    );
  },
};
