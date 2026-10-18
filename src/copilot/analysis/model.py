"""3-year monthly financial model in three cases: Worst, Expected, Best (chunk 14a).

Starts from the latest month-end accrual balance sheet (statements.py, with the owner's applied
adjustments) and projects 36 months of P&L, balance sheet and cash flow. Pure and read-only:
nothing is saved, and every request rebuilds the model.

Six drivers. Expected comes from the books (each driver says where); Worst and Best are a fixed
step away. A request may override an Expected value; Worst and Best are then re-derived.
  sales growth per year        last 6 vs previous 6 months, annualised    -10 / +10 points
  cost of sales %              last 12 months                             +3 / -3 points
  cost increase per year       3%, our assumption (from year 2)           5% / 2%
  customer delay (days late)   saved assumption, else measured            +15 days / on terms
  owner drawings per month     0                                          same in all cases
  planned events               none                                       same in all cases

Timing is shared with the 13-week forecast (forecast.receipt_date / bill_payment_date): open
invoices are expected at due date + the customer's delay, open bills are paid on their due date.
New invoices and bills go out on each counterparty's usual days (forecast._pattern).

Double entry, as in statements.py: every amount is rounded to cents before it is posted and
moves a pair of lines. Cash on the balance sheet is the direct cash path (money actually in and
out); the cash-flow statement is built indirectly from profit. Two checks every month:
balance sheet difference 0.00, indirect minus direct cash 0.00.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from copilot.analysis.statements import (
    CASH_OPEX,
    BalanceSheet,
    CashFlow,
    MonthStatements,
    ProfitAndLoss,
    Ratios,
    _depreciation_to,
    _ratios,
    _sum_cash_flow,
    _sum_pnl,
    month_end,
    month_label,
    month_start,
    monthly_statements,
)
from copilot.cashflow.forecast import (
    _pattern,
    active_assumptions,
    bill_payment_date,
    measured_delays,
    receipt_date,
)
from copilot.dates import add_months, clamp_day
from copilot.reconcile import match_settlements
from copilot.schemas import (
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    Id,
    Money,
    PaymentStatus,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

MONTHS = 36
CENT = Decimal("0.01")
PCT = Decimal("0.01")
RATIO = Decimal("0.0001")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")
GST_RATE = Decimal("0.09")  # Singapore GST, used when the books carry GST
GST_MONTHS = (1, 4, 7, 10)  # a quarter's return is paid in the month after it ends
DEFAULT_ISSUE_DAY = 15
DEFAULT_TERMS = 30

# Fixed steps from Expected (decided 2026-10-11).
GROWTH_STEP = Decimal("10")
COST_OF_SALES_STEP = Decimal("3")
COST_INCREASE = Decimal("3")  # our assumption, not data
COST_INCREASE_WORST_STEP = Decimal("2")  # 5%
COST_INCREASE_BEST_STEP = Decimal("-1")  # 2%
DELAY_WORST_STEP = 15

Case = Literal["worst", "expected", "best"]
CASES: tuple[Case, ...] = ("worst", "expected", "best")
CASE_NAMES = {"worst": "Worst", "expected": "Expected", "best": "Best"}
OPEX_LINES = ("rent", "utilities", "software", "marketing", "professional_fees", "other")
LINE_CATEGORY = {CASH_OPEX[c]: c for c in CASH_OPEX if c is not Cat.UNCATEGORISED}
Month = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]

NOTES = [
    "Accrual basis, amounts excluding GST; a projection from your books, not a promise.",
    "Month-end balances only: cash can dip inside a month. For the next 13 weeks day by day, "
    "use the 13-week forecast.",
    "Sales are flat within each year: year n = the last 12 months' average x (1 + growth)^n.",
    "Customers keep their share of sales and pay on their terms plus their delay; suppliers "
    "keep their share and are paid on their terms.",
    "Stock is kept at the usual cover of cost of sales; when there is more stock than that, "
    "purchases pause until it is used.",
    "Payroll is the latest payroll run; CPF is paid the month after. Other operating costs are "
    "the last 12 months' average per line. Both rise by the cost increase from year 2.",
    "Loan repayments follow the lender's schedule; GST owed at each quarter-end is paid the "
    "month after; depreciation follows each asset's life.",
    "Not modelled: income tax, new loans or asset purchases, seasonality, new customers.",
]


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


# --- Inputs ----------------------------------------------------------------------------------


class ModelEvent(CopilotModel):
    """A planned one-off or monthly amount, the same in all three cases. Counted as operating
    income (positive) or cost (negative) and as cash in the same month; no GST."""

    label: UntrustedText = Field(max_length=80, description="What it is, e.g. 'new hire'")
    month: Month = Field(description="YYYY-MM of the (first) month, inside the 36 months")
    amount: Money = Field(
        description='SGD as a string: negative for a cost ("-5000.00"), positive for income'
    )
    repeat: Literal["once", "monthly"] = Field(
        default="once", description="once, or monthly from `month` to the end of the model"
    )


class ModelInputs(CopilotModel):
    """Overrides for the Expected case (None = from the books). Worst and Best follow."""

    sales_growth_pct: Decimal | None = Field(default=None, ge=-50, le=100)
    cost_of_sales_pct: Decimal | None = Field(default=None, ge=0, le=95)
    cost_increase_pct: Decimal | None = Field(default=None, ge=-10, le=30)
    customer_delay_days: int | None = Field(default=None, ge=0, le=180)
    owner_drawings: Money | None = Field(default=None, ge=0, le=1_000_000)
    events: list[ModelEvent] = Field(default=[], max_length=5)


# --- Result models ---------------------------------------------------------------------------


class ModelDriver(CopilotModel):
    key: str
    label: str
    unit: str  # "% a year", "% of sales", "S$ a month"
    worst: Decimal
    expected: Decimal
    best: Decimal
    source: str  # where Expected comes from, built by code


class CustomerTerms(CopilotModel):
    id: Id
    name: UntrustedText
    share: Decimal  # fraction of sales, last 12 months
    terms_days: int
    issue_days: list[int]
    delay_worst: int
    delay_expected: int
    delay_best: int
    delay_source: str


class SupplierTerms(CopilotModel):
    id: Id
    name: UntrustedText
    share: Decimal
    terms_days: int
    issue_days: list[int]


class ModelLoan(CopilotModel):
    id: Id
    lender: UntrustedText
    balance_at_start: Money  # lender's schedule at the balance-sheet date
    last_payment_month: str | None  # YYYY-MM of the final instalment


class DirectCash(CopilotModel):
    """Money actually in and out of the bank in the month (the direct method)."""

    customer_receipts: Money
    supplier_payments: Money  # negative
    operating_costs_paid: Money  # rent, utilities, ..., events, scheduled one-offs (negative)
    payroll_paid: Money  # net pay this month + CPF for last month (negative)
    gst_paid: Money
    loan_repayments: Money
    owner_drawings: Money
    accrued_costs_settled: Money
    net_change: Money
    closing_cash: Money


class ModelChecks(CopilotModel):
    balance_sheet_difference: Money  # assets - liabilities - equity; must be 0.00
    indirect_minus_direct_cash: Money  # cash-flow statement closing cash - direct cash; 0.00
    balanced: bool
    cash_agrees: bool


class ModelMonth(CopilotModel):
    month: str
    pnl: ProfitAndLoss
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
    direct_cash: DirectCash
    checks: ModelChecks


class ModelYear(CopilotModel):
    year: int
    months: str  # e.g. "Oct 2026 - Sep 2027"
    pnl: ProfitAndLoss
    cash_flow: CashFlow
    balance_sheet: BalanceSheet  # at the year's last month-end
    ratios: Ratios


class Outlook(CopilotModel):
    lowest_cash: Money  # lowest month-end cash
    lowest_cash_month: str
    first_month_below_zero: str | None
    cash_end_of_year: list[Money]  # years 1-3
    revenue_by_year: list[Money]
    net_profit_by_year: list[Money]
    year1_revenue_vs_last_12_months: Decimal | None  # fraction


class CaseModel(CopilotModel):
    case: Case
    name: str
    sales_growth_pct: Decimal
    cost_of_sales_pct: Decimal
    cost_increase_pct: Decimal
    outlook: Outlook
    years: list[ModelYear]
    checks: ModelChecks  # the worst month
    monthly: list[ModelMonth] = []


class FinancialModel(CopilotModel):
    basis: Literal["accrual"] = "accrual"
    starts_from: date  # the balance sheet the model opens from
    first_month: str
    last_month: str
    drivers: list[ModelDriver]
    stock_cover_months: Decimal | None  # month-end stock / cost of sales (median, last 12)
    customers: list[CustomerTerms]
    suppliers: list[SupplierTerms]
    loans: list[ModelLoan]
    events: list[ModelEvent]
    actual_last_12_months: ProfitAndLoss
    cases: dict[str, CaseModel]
    notes: list[str]


# --- Base: everything measured from the books once --------------------------------------------


@dataclass
class _Doc:
    """A dated cash movement that settles receivables (+) or payables (-)."""

    when: date
    amount: Decimal
    ref: str | None = None


@dataclass
class _Party:
    id: str
    name: str
    share: Decimal
    terms: int
    days: list[int]
    delay: int = 0  # expected delay (customers)
    delay_source: str = ""


@dataclass
class _Base:
    today: date
    opening: MonthStatements
    last12: list[MonthStatements]
    avg_revenue: Decimal
    growth: Decimal
    growth_source: str
    cost_of_sales: Decimal
    cos_source: str
    stock_cover: Decimal | None
    opex: dict[str, Decimal]
    cost_changes: dict[str, tuple[str, Decimal]]  # line -> (from YYYY-MM, monthly amount)
    payroll_net: Decimal
    payroll_cpf: Decimal
    gst_rate: Decimal
    customers: list[_Party]
    suppliers: list[_Party]
    delays: dict[str, int]  # customer id -> expected days late (saved, else measured)
    open_invoices: list[tuple[date, str, Decimal, str]]  # (due, customer id, amount, ref)
    paid_invoices: list[_Doc]  # settled after the balance-sheet date (known dates)
    bill_payments: list[_Doc]  # open + settled-after bills, scheduled payments (negative)
    one_off_costs: list[_Doc]  # scheduled payments not tied to a bill (negative)
    loan_rows: dict[str, list]  # YYYY-MM -> schedule rows
    schedule_rows: list
    assets: list
    warnings: list[str] = field(default_factory=list)


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _shares(totals: dict[str, Decimal]) -> dict[str, Decimal]:
    total = sum(totals.values(), ZERO)
    return {k: v / total for k, v in totals.items()} if total > 0 else {}


def _base(store: Store, business_id: str, today: date) -> _Base | str:
    months, warnings, reason = monthly_statements(store, business_id, today)
    if reason is not None:
        return reason
    warnings = [w for w in warnings if "uncategorised" not in w]  # history detail, not the model
    opening = months[-1]
    bs_day = opening.balance_sheet.as_of
    last12 = months[-12:]
    revenue = [m.pnl.revenue for m in last12]
    total_revenue = sum(revenue, ZERO)
    if total_revenue <= 0:
        return "The books show no sales in the last 12 months, so there is nothing to project."
    avg_revenue = total_revenue / len(last12)
    if len(last12) < 12:
        warnings.append(
            f"Only {len(last12)} complete months of accrual books: averages use those months."
        )

    if len(months) >= 12:
        last6, prev6 = sum(revenue[-6:], ZERO), sum(revenue[-12:-6], ZERO)
        growth = ((last6 / prev6) ** 2 - 1) * HUNDRED if prev6 > 0 else ZERO
        growth = growth.quantize(PCT, ROUND_HALF_UP)
        growth_source = (
            f"measured: sales {sgd(_round(last6))} in the last 6 months vs {sgd(_round(prev6))} "
            "in the 6 before, annualised"
        )
    else:
        growth = ZERO
        growth_source = "not enough history to measure (needs 12 months): 0% assumed"

    cos_total = sum((m.pnl.cost_of_sales for m in last12), ZERO)
    cost_of_sales = (cos_total / total_revenue * HUNDRED).quantize(PCT, ROUND_HALF_UP)
    cos_source = (
        f"measured: cost of sales {sgd(cos_total)} / sales {sgd(total_revenue)}, last "
        f"{len(last12)} months"
    )

    has_stock = bool(store.list_inventory_snapshots(business_id))
    cover = (
        _median(
            [
                m.balance_sheet.inventory / m.pnl.cost_of_sales
                for m in last12
                if m.pnl.cost_of_sales > 0
            ]
        )
        if has_stock
        else None
    )
    cover = cover.quantize(PCT, ROUND_HALF_UP) if cover is not None else None

    opex = {
        line: _round(
            sum((m.pnl.operating_expenses.get(line, ZERO) for m in last12), ZERO) / len(last12)
        )
        for line in OPEX_LINES
    }

    # Payroll: the latest run.
    runs = sorted(store.list_payroll_runs(business_id), key=lambda r: r.period)
    if runs:
        run = runs[-1]
        payroll_net, payroll_cpf = run.net_pay, run.employee_cpf + run.employer_cpf
    else:
        payroll_net = _round(
            sum((m.pnl.operating_expenses.get("payroll", ZERO) for m in last12), ZERO) / len(last12)
        )
        payroll_cpf = ZERO
        if payroll_net:
            warnings.append("No payroll runs: payroll is the average paid, with no CPF timing.")

    # Saved assumptions (chunk 13).
    saved = active_assumptions(store, business_id)
    cost_changes: dict[str, tuple[str, Decimal]] = {}
    for a in saved:
        if a.kind == "recurring_change" and a.category and a.amount is not None and a.start:
            line = CASH_OPEX.get(a.category)
            if line in OPEX_LINES:
                cost_changes[line] = (_key(a.start), a.amount)
            else:
                warnings.append(
                    f"Saved assumption {a.id} ({a.category.value}) is used by the 13-week "
                    "forecast only; the 3-year model takes payroll from the latest payroll run."
                )

    # Customers and suppliers: shares of the last 12 months, usual days, terms, delays.
    window_start = month_start(last12[0].month)
    names = {c.id: c for c in store.list_counterparties(business_id)}
    invoices = [i for i in store.list_invoices(business_id) if i.status is not DocumentStatus.VOID]
    bills = [b for b in store.list_bills(business_id) if b.status is not DocumentStatus.VOID]
    delays, _ = measured_delays(store, business_id)
    delay_source = {cid: "measured average" for cid in delays}
    for a in saved:
        if a.kind == "payment_delay" and a.counterparty_id and a.days is not None:
            delays[a.counterparty_id] = a.days
            delay_source[a.counterparty_id] = f"your saved assumption {a.id}"

    def parties(docs, kind: str) -> list[_Party]:
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        by_party = defaultdict(list)
        for d in docs:
            by_party[d.counterparty_id].append(d)
            if window_start <= d.issue_date <= bs_day:
                totals[d.counterparty_id] += d.amount - d.gst
        out = []
        for cid, share in sorted(_shares(totals).items(), key=lambda kv: -kv[1]):
            pattern = _pattern(by_party[cid], bs_day)
            cp = names.get(cid)
            out.append(
                _Party(
                    id=cid,
                    name=cp.name if cp else cid,
                    share=share,
                    terms=cp.payment_terms_days if cp else DEFAULT_TERMS,
                    days=pattern[0] if pattern else [DEFAULT_ISSUE_DAY],
                    delay=delays.get(cid, 0) if kind == "customer" else 0,
                    delay_source=delay_source.get(cid, "no paid invoices: on the due date"),
                )
            )
        if not out:
            out.append(
                _Party(
                    id=f"unnamed-{kind}",
                    name=f"all {kind}s",
                    share=Decimal(1),
                    terms=DEFAULT_TERMS,
                    days=[DEFAULT_ISSUE_DAY],
                    delay_source="no invoices: on the due date",
                )
            )
            warnings.append(
                f"No {kind} documents in the last 12 months: one unnamed {kind} on "
                f"{DEFAULT_TERMS}-day terms is assumed."
            )
        return out

    customers = parties(invoices, "customer")
    suppliers = parties(bills, "supplier")
    gst_rate = GST_RATE if any(d.gst for d in [*invoices, *bills]) else ZERO

    # Documents open at the balance-sheet date.
    settled: dict[tuple[str, str], date] = {}
    txn_date = {t.id: t.date for t in store.list_transactions(business_id)}
    for txn_id, invoice_id in store.receipt_links(business_id).items():
        if txn_id in txn_date:
            settled[("invoice", invoice_id)] = txn_date[txn_id]
    for kind in ("invoice", "bill"):
        for doc_id, when in match_settlements(store, business_id, kind).paid_on.items():
            settled.setdefault((kind, doc_id), when)

    scheduled = store.list_scheduled_payments(business_id, (PaymentStatus.SCHEDULED,))
    scheduled_for_bill: dict[str, Decimal] = defaultdict(lambda: ZERO)
    bill_payments: list[_Doc] = []
    one_off_costs: list[_Doc] = []
    first_day = today + timedelta(days=1)
    for p in scheduled:
        when = max(p.pay_on, first_day)
        if p.bill_id is not None:
            scheduled_for_bill[p.bill_id] += p.amount
            bill_payments.append(_Doc(when, -p.amount, p.bill_id))
        else:
            one_off_costs.append(_Doc(when, -p.amount, p.id))

    open_invoices: list[tuple[date, str, Decimal, str]] = []
    paid_invoices: list[_Doc] = []
    for i in invoices:
        if i.issue_date > bs_day:
            continue
        if i.status is DocumentStatus.OPEN:
            open_invoices.append((i.due_date, i.counterparty_id, i.amount - i.amount_paid, i.id))
        elif settled.get(("invoice", i.id), date.min) > bs_day:
            paid_invoices.append(_Doc(settled[("invoice", i.id)], i.amount, i.id))
    for b in bills:
        if b.issue_date > bs_day:
            continue
        if b.status is DocumentStatus.OPEN:
            rest = max(b.amount - b.amount_paid - scheduled_for_bill[b.id], ZERO)
            if rest:
                bill_payments.append(_Doc(bill_payment_date(b.due_date, today), -rest, b.id))
        elif settled.get(("bill", b.id), date.min) > bs_day:
            bill_payments.append(_Doc(settled[("bill", b.id)], -b.amount, b.id))

    bs = opening.balance_sheet
    to_collect = sum((a for *_, a, _ in open_invoices), ZERO) + sum(
        (d.amount for d in paid_invoices), ZERO
    )
    if to_collect != bs.receivables:
        warnings.append(
            f"Open invoices ({sgd(to_collect)}) differ from receivables on the balance sheet "
            f"({sgd(bs.receivables)}); the difference stays unpaid in the model."
        )
    to_pay = -sum((d.amount for d in bill_payments), ZERO)
    if to_pay != bs.payables:
        warnings.append(
            f"Open bills ({sgd(to_pay)}) differ from payables on the balance sheet "
            f"({sgd(bs.payables)}); the difference stays unpaid in the model."
        )
    if bs.unmatched_customer_receipts or bs.unmatched_supplier_payments:
        warnings.append(
            "Payments not yet matched to an invoice or bill are carried unchanged; link them "
            "to correct the balance sheet."
        )
    if one_off_costs:
        warnings.append(
            f"{len(one_off_costs)} scheduled payment(s) not tied to a bill count as other costs."
        )

    loan_rows: dict[str, list] = defaultdict(list)
    schedule_rows = store.list_loan_schedule(business_id)
    for r in schedule_rows:
        if r.due_date > bs_day:
            loan_rows[_key(r.due_date)].append(r)
    assets = [a for a in store.list_fixed_assets(business_id) if a.acquired_on <= bs_day]

    return _Base(
        today=today,
        opening=opening,
        last12=last12,
        avg_revenue=avg_revenue,
        growth=growth,
        growth_source=growth_source,
        cost_of_sales=cost_of_sales,
        cos_source=cos_source,
        stock_cover=cover,
        opex=opex,
        cost_changes=cost_changes,
        payroll_net=payroll_net,
        payroll_cpf=payroll_cpf,
        gst_rate=gst_rate,
        customers=customers,
        suppliers=suppliers,
        delays=delays,
        open_invoices=open_invoices,
        paid_invoices=paid_invoices,
        bill_payments=bill_payments,
        one_off_costs=one_off_costs,
        loan_rows=dict(loan_rows),
        schedule_rows=schedule_rows,
        assets=assets,
        warnings=warnings,
    )


# --- Cases -----------------------------------------------------------------------------------


@dataclass
class _CaseInputs:
    case: Case
    growth: Decimal  # % a year
    cost_of_sales: Decimal  # % of sales
    cost_increase: Decimal  # % a year from year 2
    delays: dict[str, int]  # customer id -> days after due date
    drawings: Decimal
    events: list[ModelEvent]


def _drivers(
    base: _Base, inputs: ModelInputs
) -> tuple[list[ModelDriver], dict[Case, _CaseInputs], list[CustomerTerms]]:
    growth = base.growth if inputs.sales_growth_pct is None else inputs.sales_growth_pct
    cos = base.cost_of_sales if inputs.cost_of_sales_pct is None else inputs.cost_of_sales_pct
    rise = COST_INCREASE if inputs.cost_increase_pct is None else inputs.cost_increase_pct
    draw = ZERO if inputs.owner_drawings is None else inputs.owner_drawings
    yours = "your figure for this question"
    values = {
        "worst": (growth - GROWTH_STEP, min(cos + COST_OF_SALES_STEP, HUNDRED),
                  rise + COST_INCREASE_WORST_STEP),
        "expected": (growth, cos, rise),
        "best": (growth + GROWTH_STEP, max(cos - COST_OF_SALES_STEP, ZERO),
                 rise + COST_INCREASE_BEST_STEP),
    }  # fmt: skip
    drivers = [
        ModelDriver(
            key="sales_growth_pct",
            label="Sales growth",
            unit="% a year",
            worst=values["worst"][0],
            expected=growth,
            best=values["best"][0],
            source=base.growth_source if inputs.sales_growth_pct is None else yours,
        ),
        ModelDriver(
            key="cost_of_sales_pct",
            label="Cost of sales",
            unit="% of sales",
            worst=values["worst"][1],
            expected=cos,
            best=values["best"][1],
            source=base.cos_source if inputs.cost_of_sales_pct is None else yours,
        ),
        ModelDriver(
            key="cost_increase_pct",
            label="Cost increase (payroll and operating costs, from year 2)",
            unit="% a year",
            worst=values["worst"][2],
            expected=rise,
            best=values["best"][2],
            source="our assumption, not data" if inputs.cost_increase_pct is None else yours,
        ),
        ModelDriver(
            key="owner_drawings",
            label="Owner drawings",
            unit="S$ a month",
            worst=draw,
            expected=draw,
            best=draw,
            source="none assumed" if inputs.owner_drawings is None else yours,
        ),
    ]
    delays: dict[Case, dict[str, int]] = {c: {} for c in CASES}
    who = {p.id for p in base.customers} | {cid for _, cid, _, _ in base.open_invoices}
    for cid in who:
        expected = (
            base.delays.get(cid, 0)
            if inputs.customer_delay_days is None
            else inputs.customer_delay_days
        )
        delays["expected"][cid] = expected
        delays["worst"][cid] = expected + DELAY_WORST_STEP
        delays["best"][cid] = min(expected, 0)  # on terms (an early payer stays early)
    terms = []
    for p in base.customers:
        expected = delays["expected"][p.id]
        source = p.delay_source if inputs.customer_delay_days is None else yours
        terms.append(
            CustomerTerms(
                id=p.id,
                name=p.name,
                share=p.share.quantize(RATIO, ROUND_HALF_UP),
                terms_days=p.terms,
                issue_days=p.days,
                delay_worst=delays["worst"][p.id],
                delay_expected=expected,
                delay_best=delays["best"][p.id],
                delay_source=source,
            )
        )
    cases = {
        c: _CaseInputs(c, *values[c], delays=delays[c], drawings=draw, events=inputs.events)
        for c in CASES
    }
    return drivers, cases, terms


def _split(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split a cent amount by weights; the first (largest) part takes the rounding."""
    parts = [_round(total * w) for w in weights[1:]]
    return [total - sum(parts, ZERO), *parts]


def _documents(
    month: date, net: Decimal, parties: list[_Party], gst_rate: Decimal
) -> list[tuple[_Party, date, Decimal, Decimal]]:
    """One month's invoices or bills: (party, issue date, amount incl. GST, GST)."""
    docs = []
    shares = _split(net, [p.share for p in parties])
    for party, share in zip(parties, shares, strict=True):
        days = party.days
        for day, piece in zip(
            days, _split(share, [Decimal(1) / len(days)] * len(days)), strict=True
        ):
            if piece == 0:
                continue
            gross = _round(piece * (1 + gst_rate))
            docs.append((party, clamp_day(month.year, month.month, day), gross, gross - piece))
    return docs


def _active(event: ModelEvent, key: str) -> bool:
    return event.month == key if event.repeat == "once" else key >= event.month


LINE_ORDER = ("payroll", *OPEX_LINES, "depreciation", "planned_events")


def _run_case(base: _Base, ci: _CaseInputs) -> list[ModelMonth]:
    """Roll the opening balance sheet forward 36 months for one case."""
    bs0 = base.opening.balance_sheet
    first = add_months(month_start(base.opening.month), 1)
    receipts: dict[str, Decimal] = defaultdict(lambda: ZERO)  # YYYY-MM -> customer money in
    payments: dict[str, Decimal] = defaultdict(lambda: ZERO)  # YYYY-MM -> supplier money out (-)
    one_offs: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for due, cid, amount, _ in base.open_invoices:
        receipts[_key(receipt_date(due, ci.delays[cid], base.today))] += amount
    for d in base.paid_invoices:
        receipts[_key(d.when)] += d.amount
    for d in base.bill_payments:
        payments[_key(d.when)] += d.amount
    for d in base.one_off_costs:
        one_offs[_key(d.when)] += d.amount

    # Sales are known up front (flat within each year), so every invoice can be dated now.
    revenue: list[Decimal] = []
    invoiced: list[Decimal] = []
    output_tax: list[Decimal] = []
    for k in range(MONTHS):
        month = add_months(first, k)
        net = _round(base.avg_revenue * (1 + ci.growth / HUNDRED) ** (k // 12 + 1))
        gross_total = tax_total = ZERO
        for party, issue, gross, tax in _documents(month, net, base.customers, base.gst_rate):
            collect = max(issue, issue + timedelta(days=party.terms + ci.delays[party.id]))
            receipts[_key(collect)] += gross
            gross_total += gross
            tax_total += tax
        revenue.append(net)
        invoiced.append(gross_total)
        output_tax.append(tax_total)

    cash = cf_cash = bs0.cash
    ar, stock, ap = bs0.receivables, bs0.inventory, bs0.payables
    gst, cpf, accrued = bs0.gst_payable, bs0.cpf_payable, bs0.accrued_costs
    loans, acc_dep = bs0.loans, bs0.accumulated_depreciation
    retained, drawings_total = bs0.retained_earnings, bs0.owner_drawings
    prev_end = bs0.as_of
    out: list[ModelMonth] = []
    for k in range(MONTHS):
        month = add_months(first, k)
        end = month_end(month)
        key = _key(month)
        factor = (1 + ci.cost_increase / HUNDRED) ** (k // 12)

        # Sales, cost of sales, stock and purchases.
        rev = revenue[k]
        cos = _round(rev * ci.cost_of_sales / HUNDRED)
        if base.stock_cover is not None:
            purchases = max(ZERO, cos + _round(cos * base.stock_cover) - stock)
        else:
            purchases = cos
        closing_stock = stock + purchases - cos
        new_payables = input_tax = ZERO
        for party, issue, gross, tax in _documents(month, purchases, base.suppliers, base.gst_rate):
            payments[_key(issue + timedelta(days=party.terms))] -= gross
            new_payables += gross
            input_tax += tax

        # Operating costs.
        opex: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for line in OPEX_LINES:
            monthly = base.opex[line]
            change = base.cost_changes.get(line)
            if change is not None and key >= change[0]:
                monthly = change[1]
            opex[line] += _round(monthly * factor)
        opex["other"] -= one_offs.get(key, ZERO)
        net_pay = _round(base.payroll_net * factor)
        payroll_cost = net_pay + _round(base.payroll_cpf * factor)
        opex["payroll"] += payroll_cost
        opex["depreciation"] += sum((_depreciation_to(a, end) for a in base.assets), ZERO) - sum(
            (_depreciation_to(a, prev_end) for a in base.assets), ZERO
        )
        event_income = ZERO
        for e in ci.events:
            if _active(e, key):
                if e.amount > 0:
                    event_income += e.amount
                else:
                    opex["planned_events"] -= e.amount
        lines = {name: opex[name] for name in LINE_ORDER if opex.get(name)}
        total_opex = sum(lines.values(), ZERO)
        dep = lines.get("depreciation", ZERO)
        cash_opex = total_opex - lines.get("payroll", ZERO) - dep

        # Loan, GST, CPF, drawings: what leaves the bank this month.
        rows = base.loan_rows.get(key, [])
        interest = sum((r.interest for r in rows), ZERO)
        principal = sum((r.principal for r in rows), ZERO)
        gst_paid = gst if month.month in GST_MONTHS else ZERO  # owed at the quarter-end
        cpf_paid = cpf  # last month's CPF (and any wages owed)
        accrued_settled = accrued  # the owner's accrued costs are paid in month 1
        drawn = ci.drawings
        received = receipts.get(key, ZERO)
        paid = payments.get(key, ZERO)

        gross_profit = rev - cos
        operating_profit = gross_profit - total_opex
        net_profit = operating_profit + event_income - interest

        # Direct cash: money actually in and out.
        flows = {
            "customer_receipts": received,
            "supplier_payments": paid,
            "operating_costs_paid": -cash_opex + event_income,
            "payroll_paid": -(net_pay + cpf_paid),
            "gst_paid": -gst_paid,
            "loan_repayments": -(interest + principal),
            "owner_drawings": -drawn,
            "accrued_costs_settled": -accrued_settled,
        }
        change = sum(flows.values(), ZERO)
        cash += change
        direct = DirectCash(**flows, net_change=change, closing_cash=cash)

        # Indirect cash flow from profit and the balance-sheet movements.
        old = {
            "receivables": ar,
            "inventory": stock,
            "payables": ap,
            "gst_payable": gst,
            "cpf_payable": cpf,
            "accrued_costs": accrued,
        }
        new = {
            "receivables": ar + invoiced[k] - received,
            "inventory": closing_stock,
            "payables": ap + new_payables + paid,
            "gst_payable": gst + output_tax[k] - input_tax - gst_paid,
            "cpf_payable": cpf + payroll_cost - net_pay - cpf_paid,
            "accrued_costs": accrued - accrued_settled,
        }
        changes = {
            name: (old[name] - new[name]) if name in ("receivables", "inventory")
            else (new[name] - old[name])
            for name in new
            if name != "accrued_costs" or old[name] or new[name]
        }  # fmt: skip
        operating = net_profit + dep + sum(changes.values(), ZERO)
        financing = -principal - drawn
        cf_opening = cf_cash
        cf_cash = cf_opening + operating + financing

        ar, stock, ap = new["receivables"], new["inventory"], new["payables"]
        gst, cpf, accrued = new["gst_payable"], new["cpf_payable"], new["accrued_costs"]
        loans -= principal
        acc_dep += dep
        retained += net_profit
        drawings_total += drawn

        within, after = _loan_split(base, loans, end)
        total_assets = (
            cash + ar + stock + bs0.unmatched_supplier_payments + bs0.fixed_assets_cost - acc_dep
        )
        total_liabilities = (
            ap + gst + cpf + bs0.unmatched_customer_receipts + accrued + loans
            + bs0.other_borrowings
        )  # fmt: skip
        total_equity = bs0.share_capital + retained - drawings_total
        bs_diff = total_assets - total_liabilities - total_equity
        cash_diff = cf_cash - cash
        out.append(
            ModelMonth(
                month=key,
                pnl=ProfitAndLoss(
                    revenue=rev,
                    purchases=purchases,
                    cost_of_sales=cos,
                    gross_profit=gross_profit,
                    operating_expenses=lines,
                    total_operating_expenses=total_opex,
                    operating_profit=operating_profit,
                    other_income=event_income,
                    interest=interest,
                    net_profit=net_profit,
                ),
                balance_sheet=BalanceSheet(
                    as_of=end,
                    cash=cash,
                    receivables=ar,
                    inventory=stock,
                    unmatched_supplier_payments=bs0.unmatched_supplier_payments,
                    fixed_assets_cost=bs0.fixed_assets_cost,
                    accumulated_depreciation=acc_dep,
                    fixed_assets_net=bs0.fixed_assets_cost - acc_dep,
                    total_assets=total_assets,
                    payables=ap,
                    gst_payable=gst,
                    cpf_payable=cpf,
                    unmatched_customer_receipts=bs0.unmatched_customer_receipts,
                    accrued_costs=accrued,
                    loans=loans,
                    loans_due_within_12_months=within,
                    loans_due_after_12_months=after,
                    other_borrowings=bs0.other_borrowings,
                    total_liabilities=total_liabilities,
                    share_capital=bs0.share_capital,
                    retained_earnings=retained,
                    owner_drawings=drawings_total,
                    total_equity=total_equity,
                ),
                cash_flow=CashFlow(
                    net_profit=net_profit,
                    add_depreciation=dep,
                    working_capital=changes,
                    operating=operating,
                    investing=ZERO,
                    financing_loan_principal=-principal,
                    new_borrowing=ZERO,
                    owner_drawings=-drawn,
                    financing=financing,
                    net_change=operating + financing,
                    opening_cash=cf_opening,
                    closing_cash=cf_cash,
                ),
                direct_cash=direct,
                checks=ModelChecks(
                    balance_sheet_difference=bs_diff,
                    indirect_minus_direct_cash=cash_diff,
                    balanced=bs_diff == 0,
                    cash_agrees=cash_diff == 0,
                ),
            )
        )
        prev_end = end
    return out


def _loan_split(base: _Base, balance: Decimal, end: date) -> tuple[Decimal | None, Decimal | None]:
    """Principal due in the 12 months after `end` (lender's schedule), and the rest."""
    if balance == 0:
        return ZERO, ZERO
    if not base.schedule_rows:
        return None, None
    horizon = add_months(end, 12)
    due = sum((r.principal for r in base.schedule_rows if end < r.due_date <= horizon), ZERO)
    within = min(due, balance)
    return within, balance - within


def _outlook(months: list[ModelMonth], last12_revenue: Decimal) -> Outlook:
    lowest = min(months, key=lambda m: m.balance_sheet.cash)
    below = next((m.month for m in months if m.balance_sheet.cash < 0), None)
    years = [months[i * 12 : (i + 1) * 12] for i in range(MONTHS // 12)]
    revenue = [sum((m.pnl.revenue for m in y), ZERO) for y in years]
    return Outlook(
        lowest_cash=lowest.balance_sheet.cash,
        lowest_cash_month=lowest.month,
        first_month_below_zero=below,
        cash_end_of_year=[y[-1].balance_sheet.cash for y in years],
        revenue_by_year=revenue,
        net_profit_by_year=[sum((m.pnl.net_profit for m in y), ZERO) for y in years],
        year1_revenue_vs_last_12_months=(
            ((revenue[0] - last12_revenue) / last12_revenue).quantize(RATIO, ROUND_HALF_UP)
            if last12_revenue
            else None
        ),
    )


def _years(months: list[ModelMonth]) -> list[ModelYear]:
    out = []
    for i in range(MONTHS // 12):
        chunk = months[i * 12 : (i + 1) * 12]
        pnl = _sum_pnl([m.pnl for m in chunk])
        bs = chunk[-1].balance_sheet
        out.append(
            ModelYear(
                year=i + 1,
                months=f"{month_label(chunk[0].month)} - {month_label(chunk[-1].month)}",
                pnl=pnl,
                cash_flow=_sum_cash_flow([m.cash_flow for m in chunk]),
                balance_sheet=bs,
                ratios=_ratios(pnl, bs),
            )
        )
    return out


def _loans(store: Store, business_id: str, base: _Base) -> list[ModelLoan]:
    day = base.opening.balance_sheet.as_of
    out = []
    for loan in store.list_loans(business_id):
        rows = [r for r in base.schedule_rows if r.loan_id == loan.id]
        paid = [r for r in rows if r.due_date <= day]
        out.append(
            ModelLoan(
                id=loan.id,
                lender=loan.lender,
                balance_at_start=paid[-1].balance_after if paid else loan.principal,
                last_payment_month=_key(rows[-1].due_date) if rows else None,
            )
        )
    return out


def _worst_check(months: list[ModelMonth]) -> ModelChecks:
    return max(
        months,
        key=lambda m: (
            abs(m.checks.balance_sheet_difference) + abs(m.checks.indirect_minus_direct_cash)
        ),
    ).checks


def financial_model(
    store: Store,
    business_id: str,
    today: date,
    inputs: ModelInputs | None = None,
    include_monthly: bool = False,
) -> DomainResult[FinancialModel | None]:
    """The 3-year model in all three cases. Value None with the reason when the business has
    no accrual books. Raises ValueError for an event outside the model's months."""
    base = _base(store, business_id, today)
    if isinstance(base, str):
        return DomainResult(
            value=None,
            data_coverage=DataCoverage(period_start=today, period_end=today, record_count=0),
            warnings=[base],
        )
    return model_from_base(store, business_id, base, inputs, include_monthly)


def model_from_base(
    store: Store,
    business_id: str,
    base: _Base,
    inputs: ModelInputs | None = None,
    include_monthly: bool = False,
) -> DomainResult[FinancialModel]:
    """financial_model for an already measured base (valuation.py reuses the base)."""
    inputs = inputs or ModelInputs()
    first = add_months(month_start(base.opening.month), 1)
    keys = [_key(add_months(first, k)) for k in range(MONTHS)]
    for e in inputs.events:
        if e.month not in keys:
            raise ValueError(
                f"Event '{e.label}' is in {e.month}; the model runs from {keys[0]} to {keys[-1]}."
            )
    drivers, case_inputs, customers = _drivers(base, inputs)
    last12 = _sum_pnl([m.pnl for m in base.last12])
    cases = {}
    for c in CASES:
        ci = case_inputs[c]
        months = _run_case(base, ci)
        cases[c] = CaseModel(
            case=c,
            name=CASE_NAMES[c],
            sales_growth_pct=ci.growth,
            cost_of_sales_pct=ci.cost_of_sales,
            cost_increase_pct=ci.cost_increase,
            outlook=_outlook(months, last12.revenue),
            years=_years(months),
            checks=_worst_check(months),
            monthly=months if include_monthly else [],
        )
    summary = [
        Driver(
            label=f"{CASE_NAMES[c]} case: lowest month-end cash",
            amount=cases[c].outlook.lowest_cash,
            detail=month_label(cases[c].outlook.lowest_cash_month),
        )
        for c in CASES
    ]
    below = cases["expected"].outlook.first_month_below_zero
    if below:
        summary.append(
            Driver(
                label="Expected case: month-end cash first below zero", detail=month_label(below)
            )
        )
    model = FinancialModel(
        starts_from=base.opening.balance_sheet.as_of,
        first_month=keys[0],
        last_month=keys[-1],
        drivers=drivers,
        stock_cover_months=base.stock_cover,
        customers=customers,
        suppliers=[
            SupplierTerms(
                id=p.id,
                name=p.name,
                share=p.share.quantize(RATIO, ROUND_HALF_UP),
                terms_days=p.terms,
                issue_days=p.days,
            )
            for p in base.suppliers
        ],
        loans=_loans(store, business_id, base),
        events=inputs.events,
        actual_last_12_months=last12,
        cases=cases,
        notes=NOTES,
    )
    return DomainResult(
        value=model,
        drivers=summary,
        data_coverage=DataCoverage(
            period_start=month_start(base.last12[0].month),
            period_end=base.opening.balance_sheet.as_of,
            record_count=len(base.last12),
        ),
        warnings=[*base.warnings, "Income tax is not modelled, so profit is before tax."],
    )
