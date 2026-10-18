"""Accrual financial statements: profit and loss, balance sheet, indirect cash flow (chunk 12).

Built from store data only (opening balance sheet, documents, bank transactions, stocktakes,
fixed assets, loan schedule, payroll runs), never from an answer key. Pure and read-only.

Every month is double entry: each bank transaction and each document moves exactly one pair of
lines, and every balance-sheet line is rolled forward from the opening balance sheet. So the
balance sheet balances from real lines, with no balancing figure, and closing cash from the
cash flow equals the bank. Both are still checked every month and reported.

Rules (algorithms.md, "Accrual statements"):
- revenue and purchases are documents issued in the month, net of GST;
- cost of sales = opening stock + purchases - closing stock (month-end stocktake);
- payroll cost = gross pay + employer CPF (payroll runs); CPF and wages owed is a liability;
- depreciation is straight line from the month after purchase down to the residual value;
- other operating costs are the bank payments categorised rent, utilities, software, marketing,
  professional fees or other; uncategorised payments count as "other";
- loan repayments are split into interest (P&L) and principal (financing) by the schedule;
- money in from customers (out to suppliers) that no document claims is shown on its own line,
  never guessed onto an invoice;
- the owner's applied adjustments (chunk 13) are read beside the imported data, never written
  into it: an accrued cost (expense + / accrued costs +, reversed the next month), a relabelled
  bank payment (read as another category), a stock count (replaces the month-end stocktake).
  None of them touches cash, so closing cash still equals the bank.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from copilot.dates import add_months, clamp_day
from copilot.reconcile import match_settlements
from copilot.schemas import (
    Adjustment,
    BalanceLine,
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    FixedAsset,
    Id,
    Money,
    Transaction,
    UntrustedText,
    balance_difference,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

CENT = Decimal("0.01")
RATIO = Decimal("0.0001")
TIMES = Decimal("0.01")
ZERO = Decimal("0.00")
TOP_DRIVERS = 3

# Bank categories that are an operating cost when paid (no bill or accrual in our data).
CASH_OPEX: dict[Cat, str] = {
    Cat.RENT: "rent",
    Cat.UTILITIES: "utilities",
    Cat.SOFTWARE: "software",
    Cat.MARKETING: "marketing",
    Cat.PROFESSIONAL_FEES: "professional_fees",
    Cat.OTHER: "other",
    Cat.UNCATEGORISED: "other",  # money out that no rule labelled: a real cost, counted
}
OPEX_LABELS = {
    "payroll": "Payroll (gross pay + employer CPF)",
    "rent": "Rent",
    "utilities": "Utilities",
    "software": "Software",
    "marketing": "Marketing",
    "professional_fees": "Professional fees",
    "other": "Other costs",
    "depreciation": "Depreciation (no cash)",
    "planned_events": "Planned events (your figures)",  # 3-year model only (chunk 14a)
}
WORKING_CAPITAL_LABELS = {
    "receivables": "Unpaid customer invoices",
    "inventory": "Stock",
    "payables": "Unpaid supplier bills",
    "gst_payable": "GST owed",
    "cpf_payable": "CPF and wages owed",
    "unmatched_customer_receipts": "Customer payments not yet matched to an invoice",
    "unmatched_supplier_payments": "Supplier payments not yet matched to a bill",
    "accrued_costs": "Accrued costs (recorded adjustments)",
}

PeriodKind = Literal["month", "quarter", "ytd", "last_12_months"]
StatementKind = Literal["all", "pnl", "balance_sheet", "cash_flow"]
View = Literal["with_adjustments", "as_imported"]
# (adjustments to add, ids of applied adjustments to leave out): previews an apply or an undo.
Preview = tuple[Sequence[Adjustment], Collection[str]]

NO_DATA = (
    "Accrual statements need an opening balance sheet (opening_balances.csv), which this "
    "business doesn't have. Without it the starting receivables, payables, stock, loans and "
    "equity are unknown, and they won't be guessed. Cash-basis figures are still available "
    "(get_metrics, get_cash_summary)."
)


def _round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def month_end(d: date) -> date:
    return clamp_day(d.year, d.month, 31)


# --- Result models ---------------------------------------------------------------------------


class ProfitAndLoss(CopilotModel):
    revenue: Money  # invoices issued, net of GST
    purchases: Money  # supplier bills issued, net of GST
    cost_of_sales: Money  # opening stock + purchases - closing stock
    gross_profit: Money
    operating_expenses: dict[str, Money]  # payroll, rent, ..., depreciation (non-zero lines)
    total_operating_expenses: Money
    operating_profit: Money
    other_income: Money
    interest: Money
    net_profit: Money


class BalanceSheet(CopilotModel):
    as_of: date
    # Assets
    cash: Money  # the bank
    receivables: Money
    inventory: Money
    unmatched_supplier_payments: Money
    fixed_assets_cost: Money
    accumulated_depreciation: Money
    fixed_assets_net: Money
    total_assets: Money
    # Liabilities
    payables: Money
    gst_payable: Money
    cpf_payable: Money  # CPF and any wages owed
    unmatched_customer_receipts: Money
    accrued_costs: Money = ZERO  # owner's accrued-cost adjustments (chunk 13)
    loans: Money
    loans_due_within_12_months: Money | None  # None without a loan schedule
    loans_due_after_12_months: Money | None
    other_borrowings: Money
    total_liabilities: Money
    # Equity
    share_capital: Money
    retained_earnings: Money
    owner_drawings: Money  # since the opening date, deducted from equity
    total_equity: Money


class CashFlow(CopilotModel):
    net_profit: Money
    add_depreciation: Money
    working_capital: dict[str, Money]  # + means cash released, - means cash tied up
    operating: Money
    investing: Money
    financing_loan_principal: Money
    new_borrowing: Money
    owner_drawings: Money
    financing: Money
    net_change: Money
    opening_cash: Money
    closing_cash: Money


class Checks(CopilotModel):
    balance_sheet_difference: Money  # assets - liabilities - equity; must be 0.00
    closing_cash_minus_bank: Money  # cash-flow closing cash - bank balance; must be 0.00
    balanced: bool
    cash_matches_bank: bool


class MonthStatements(CopilotModel):
    month: str  # YYYY-MM
    pnl: ProfitAndLoss
    balance_sheet: BalanceSheet
    cash_flow: CashFlow
    checks: Checks


class Ratios(CopilotModel):
    gross_margin: Decimal | None  # fraction, 0.4399 = 43.99%
    operating_margin: Decimal | None
    net_margin: Decimal | None
    ebitda: Money  # operating profit + depreciation
    current_ratio: Decimal | None  # current assets / current liabilities, times
    debt_ratio: Decimal | None  # total liabilities / total assets


class AssetLine(CopilotModel):
    id: Id
    name: UntrustedText
    acquired_on: date
    cost: Money
    accumulated_depreciation: Money
    net_book_value: Money


class LoanLine(CopilotModel):
    id: Id
    lender: UntrustedText
    balance: Money
    due_within_12_months: Money | None
    interest_rate_pct: Decimal


class AdjustmentLine(CopilotModel):
    id: Id
    kind: str
    month: str
    description: str  # built by code
    reason: UntrustedText  # typed by the user


class AdjustmentSummary(CopilotModel):
    """The owner's applied adjustments that touch this period, and what they change."""

    count: int
    net_profit_as_imported: Money
    net_profit_with_adjustments: Money
    difference: Money
    applied: list[AdjustmentLine]


class Statements(CopilotModel):
    basis: Literal["accrual"] = "accrual"
    view: View = "with_adjustments"
    period: str  # e.g. "Sep 2026", "Q3 2026", "Jan-Sep 2026 (year to date)"
    start: date
    end: date
    months: list[str]
    pnl: ProfitAndLoss | None
    balance_sheet: BalanceSheet | None
    cash_flow: CashFlow | None
    checks: Checks  # worst month in the period
    ratios: Ratios
    fixed_assets: list[AssetLine] = []
    loans: list[LoanLine] = []
    monthly: list[MonthStatements] = []  # only filled for the dashboard / tests
    adjustments: AdjustmentSummary | None = None  # None: no applied adjustment in the period


# --- Building the months ---------------------------------------------------------------------


@dataclass
class _Books:
    """Everything the monthly roll-forward needs, read once from the store."""

    opening_day: date
    opening: dict[BalanceLine, Decimal]
    bank_at_opening: Decimal  # the bank at the end of the opening day
    txns: list[Transaction]
    settled_by: dict[str, str]  # transaction id -> "invoice" | "bill"
    issued_invoices: dict[date, list[tuple[Decimal, Decimal]]]  # issue date -> (amount, gst)
    issued_bills: dict[date, list[tuple[Decimal, Decimal]]]
    stock: dict[date, Decimal]
    assets: list[FixedAsset]
    payroll: dict[str, tuple[Decimal, Decimal]]  # YYYY-MM -> (cost, employer cpf)
    schedule: dict[str, list]  # loan id -> instalments
    loans: list
    warnings: list[str] = field(default_factory=list)
    # Applied adjustments (chunk 13): YYYY-MM -> [(cost line key, amount)] accrued that month.
    accruals: dict[str, list[tuple[str, Decimal]]] = field(default_factory=dict)


def _depreciation_to(asset: FixedAsset, end: date) -> Decimal:
    """Accumulated depreciation at month-end `end` (straight line, from the month after
    purchase, stopping at the residual value; rounded cumulatively so months never drift)."""
    elapsed = (end.year * 12 + end.month) - (asset.acquired_on.year * 12 + asset.acquired_on.month)
    elapsed = max(0, min(elapsed, asset.useful_life_months))
    return _round((asset.cost - asset.residual_value) * elapsed / asset.useful_life_months)


def _read(
    store: Store, business_id: str, with_adjustments: bool = True, preview: Preview = ((), ())
) -> _Books | str:
    """The inputs, or the reason accrual statements can't be built. With adjustments, the
    owner's applied adjustments are laid over copies of the imported data. `preview` adds
    adjustments not yet applied and leaves out applied ones (by id), to show an effect first."""
    lines = store.list_opening_balances(business_id)
    if not lines:
        return NO_DATA
    days = {b.as_of for b in lines}
    if len(days) > 1:
        return "The opening balance sheet has more than one date, so its starting point is unclear."
    opening_day = days.pop()
    if month_end(opening_day) != opening_day:
        return (
            f"The opening balance sheet is dated {opening_day.isoformat()}, which is not a "
            "month-end. Monthly statements need it at the end of a month."
        )
    diff = balance_difference(lines)
    if diff != 0:
        return (
            f"The opening balance sheet doesn't balance: assets minus liabilities and equity is "
            f"{sgd(diff)}. Fix the opening figures first; no line is adjusted to force it."
        )
    opening = dict.fromkeys(BalanceLine, ZERO)
    for b in lines:
        opening[b.line] += b.amount

    warnings: list[str] = []
    accounts = store.list_accounts(business_id)
    every = store.list_transactions(business_id)
    txns = [t for t in every if t.date > opening_day]
    bank_at_opening = sum((a.opening_balance for a in accounts), ZERO) + sum(
        (t.amount for t in every if t.date <= opening_day), ZERO
    )
    if bank_at_opening != opening[BalanceLine.CASH]:
        warnings.append(
            f"Opening cash ({sgd(opening[BalanceLine.CASH])}) differs from the bank on "
            f"{opening_day.isoformat()} ({sgd(bank_at_opening)}); the checks will show it."
        )

    # Which bank transactions settle a document: receipts linked by the owner or the sandbox
    # first, then exact matches (reconcile.match_settlements) not already taken.
    txn_date = {t.id: t.date for t in every}
    settled_by: dict[str, str] = {}
    settled_on: dict[tuple[str, str], date] = {}  # (kind, document id) -> settling date
    links = store.receipt_links(business_id)
    for txn_id, invoice_id in links.items():
        settled_by[txn_id] = "invoice"
        if txn_id in txn_date:
            settled_on[("invoice", invoice_id)] = txn_date[txn_id]
    unsettled_paid = 0
    for kind in ("invoice", "bill"):
        s = match_settlements(store, business_id, kind)
        for doc_id, txn_id in s.matched.items():
            if (kind, doc_id) in settled_on or txn_id in settled_by:
                continue
            settled_by[txn_id] = kind
            settled_on[(kind, doc_id)] = txn_date[txn_id]
        unsettled_paid += sum(1 for d in s.paid if (kind, d.id) not in settled_on)
    if unsettled_paid:
        warnings.append(
            f"{unsettled_paid} paid invoice(s) or bill(s) have no matching bank payment, so they "
            "are still shown as unpaid."
        )

    def issued(docs) -> dict[date, list[tuple[Decimal, Decimal]]]:
        out: dict[date, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for d in docs:
            if d.status is not DocumentStatus.VOID and d.issue_date > opening_day:
                out[d.issue_date].append((d.amount, d.gst))
        return out

    # Documents open on the opening day should add up to the opening lines.
    for kind, docs, line in (
        ("invoice", store.list_invoices(business_id), BalanceLine.RECEIVABLES),
        ("bill", store.list_bills(business_id), BalanceLine.PAYABLES),
    ):
        open_then = sum(
            (
                d.amount
                for d in docs
                if d.status is not DocumentStatus.VOID
                and d.issue_date <= opening_day
                and settled_on.get((kind, d.id), date.max) > opening_day
            ),
            ZERO,
        )
        if open_then != opening[line]:
            warnings.append(
                f"Opening {line.value} ({sgd(opening[line])}) differ from the {kind}s open on "
                f"{opening_day.isoformat()} ({sgd(open_then)}); the opening figure is used."
            )

    assets = []
    for a in store.list_fixed_assets(business_id):
        if a.acquired_on > opening_day:
            warnings.append(
                f"Fixed asset {a.id} was bought after the opening date; buying assets inside the "
                "period isn't supported yet, so it is left out."
            )
        else:
            assets.append(a)
    asset_cost = sum((a.cost for a in assets), ZERO)
    if asset_cost != opening[BalanceLine.FIXED_ASSETS_COST]:
        warnings.append(
            f"The fixed asset register costs {sgd(asset_cost)} but the opening balance sheet "
            f"says {sgd(opening[BalanceLine.FIXED_ASSETS_COST])}."
        )

    schedule: dict[str, list] = defaultdict(list)
    for row in store.list_loan_schedule(business_id):
        schedule[row.loan_id].append(row)

    stock = {s.date: s.value for s in store.list_inventory_snapshots(business_id)}
    accruals: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
    if with_adjustments:
        relabels: dict[str, Cat] = {}
        extra, excluded = preview
        applied = [
            a for a in store.list_adjustments(business_id, "applied") if a.id not in excluded
        ]
        for adj in [*applied, *extra]:
            if adj.kind == "accrued_cost" and adj.line is not None and adj.amount is not None:
                accruals[adj.month].append((CASH_OPEX[adj.line], adj.amount))
            elif adj.kind == "relabel" and adj.transaction_id and adj.to_category:
                relabels[adj.transaction_id] = adj.to_category
            elif adj.kind == "stock_count" and adj.amount is not None:
                stock[month_end(month_start(adj.month))] = adj.amount
        txns = [
            t.model_copy(update={"category": relabels[t.id]}) if t.id in relabels else t
            for t in txns
        ]

    return _Books(
        opening_day=opening_day,
        opening=opening,
        bank_at_opening=bank_at_opening,
        txns=txns,
        settled_by=settled_by,
        issued_invoices=issued(store.list_invoices(business_id)),
        issued_bills=issued(store.list_bills(business_id)),
        stock=stock,
        assets=assets,
        payroll={
            r.period: (r.gross_pay + r.employer_cpf, r.employer_cpf)
            for r in store.list_payroll_runs(business_id)
        },
        schedule=dict(schedule),
        loans=store.list_loans(business_id),
        warnings=warnings,
        accruals=dict(accruals),
    )


def month_start(key: str) -> date:
    """First day of a YYYY-MM month."""
    return date(int(key[:4]), int(key[5:7]), 1)


def _months(books: _Books, today: date) -> list[date]:
    """Month-ends of every complete month after the opening date, up to today."""
    ends = []
    end = month_end(books.opening_day + timedelta(days=1))
    while end <= today:
        ends.append(end)
        end = month_end(end + timedelta(days=1))
    return ends


def build_months(books: _Books, today: date) -> tuple[list[MonthStatements], list[str]]:
    """Roll the opening balance sheet forward one month at a time."""
    warnings = list(books.warnings)
    o = books.opening
    bal = {
        "receivables": o[BalanceLine.RECEIVABLES],
        "inventory": o[BalanceLine.INVENTORY],
        "unmatched_supplier_payments": ZERO,
        "payables": o[BalanceLine.PAYABLES],
        "gst_payable": o[BalanceLine.GST_PAYABLE],
        "cpf_payable": o[BalanceLine.CPF_PAYABLE],
        "unmatched_customer_receipts": ZERO,
        "accrued_costs": ZERO,
    }
    fa_cost = o[BalanceLine.FIXED_ASSETS_COST]
    acc_dep = o[BalanceLine.ACCUMULATED_DEPRECIATION]
    loans = o[BalanceLine.LOANS]
    other_borrowings = ZERO
    share_capital = o[BalanceLine.SHARE_CAPITAL]
    retained = o[BalanceLine.RETAINED_EARNINGS]
    drawings = ZERO
    cash_flow_cash = o[BalanceLine.CASH]
    bank = books.bank_at_opening

    used_rows: set[tuple[str, int]] = set()
    counted: dict[str, int] = defaultdict(int)  # warning counters
    months: list[MonthStatements] = []
    has_stock = bool(books.stock) or o[BalanceLine.INVENTORY] != 0
    prev_end = books.opening_day
    reversing: list[tuple[str, Decimal]] = []  # last month's accruals, reversed this month
    for end in _months(books, today):
        start = prev_end + timedelta(days=1)
        key = f"{end.year}-{end.month:02d}"
        month_txns = [t for t in books.txns if start <= t.date <= end]

        revenue = output_tax = purchases = input_tax = ZERO
        new_receivables = new_payables = ZERO
        for d in _days(start, end):
            for amount, gst in books.issued_invoices.get(d, []):
                revenue += amount - gst
                output_tax += gst
                new_receivables += amount
            for amount, gst in books.issued_bills.get(d, []):
                purchases += amount - gst
                input_tax += gst
                new_payables += amount

        opex: dict[str, Decimal] = defaultdict(lambda: ZERO)
        other_income = interest = principal = new_borrowing = drawn = ZERO
        receipts = payments = gst_paid = payroll_paid = ZERO
        unmatched_in = unmatched_out = transfers = ZERO
        for t in month_txns:
            settles = books.settled_by.get(t.id)
            if settles == "invoice":
                receipts += t.amount
            elif settles == "bill":
                payments -= t.amount
            elif t.category is Cat.SALES:
                unmatched_in += t.amount
            elif t.category is Cat.COGS:
                unmatched_out -= t.amount
            elif t.category is Cat.TAX:
                gst_paid -= t.amount
            elif t.category is Cat.PAYROLL:
                payroll_paid -= t.amount
            elif t.category is Cat.LOAN_REPAYMENT:
                row = _instalment(books, t, used_rows)
                if row is None:
                    counted["loan"] += 1
                    principal -= t.amount
                else:
                    interest += row.interest
                    principal += -t.amount - row.interest
            elif t.category is Cat.FINANCING_INFLOW:
                new_borrowing += t.amount
            elif t.category is Cat.OWNER_DRAW:
                drawn -= t.amount
            elif t.category is Cat.TRANSFER:
                transfers += t.amount
            elif t.category is Cat.OTHER_INCOME or (
                t.category is Cat.UNCATEGORISED and t.amount > 0
            ):
                other_income += t.amount
                if t.category is Cat.UNCATEGORISED:
                    counted["uncategorised_in"] += 1
            else:
                opex[CASH_OPEX[t.category]] -= t.amount
                if t.category is Cat.UNCATEGORISED:
                    counted["uncategorised_out"] += 1
        if transfers != 0:
            warnings.append(
                f"{key}: transfers between own accounts don't net to zero ({sgd(transfers)}); "
                "the checks will show the gap."
            )

        # Stock and cost of sales (periodic method).
        if end in books.stock:
            closing_stock = books.stock[end]
        else:
            closing_stock = bal["inventory"]
            if has_stock:
                warnings.append(
                    f"{key}: no stocktake at month-end, so stock is carried at "
                    f"{sgd(closing_stock)} and cost of sales equals purchases."
                )
        cost_of_sales = bal["inventory"] + purchases - closing_stock

        # Payroll: the run's cost, or what was paid when the run is missing.
        if key in books.payroll:
            payroll_cost = books.payroll[key][0]
        else:
            payroll_cost = payroll_paid
            if payroll_paid:
                warnings.append(
                    f"{key}: no payroll run, so payroll cost is the {sgd(payroll_paid)} paid."
                )
        if payroll_cost:
            opex["payroll"] += payroll_cost
        depreciation = sum((_depreciation_to(a, end) for a in books.assets), ZERO) - sum(
            (_depreciation_to(a, prev_end) for a in books.assets), ZERO
        )
        if depreciation:
            opex["depreciation"] += depreciation
        # Owner's accrued costs: the cost counts this month and reverses next month, when the
        # real bill or payment lands (a liability in between; no cash moves).
        accrued_now = books.accruals.get(key, [])
        for line, amount in accrued_now:
            opex[line] += amount
        for line, amount in reversing:
            opex[line] -= amount
        accrued_change = sum((a for _, a in accrued_now), ZERO) - sum(
            (a for _, a in reversing), ZERO
        )
        reversing = accrued_now

        lines = {k: v for k, v in opex.items() if v != 0}
        ordered = {k: lines[k] for k in OPEX_LABELS if k in lines}
        total_opex = sum(ordered.values(), ZERO)
        gross_profit = revenue - cost_of_sales
        operating_profit = gross_profit - total_opex
        net_profit = operating_profit + other_income - interest

        new = {
            "receivables": bal["receivables"] + new_receivables - receipts,
            "inventory": closing_stock,
            "unmatched_supplier_payments": bal["unmatched_supplier_payments"] + unmatched_out,
            "payables": bal["payables"] + new_payables - payments,
            "gst_payable": bal["gst_payable"] + output_tax - input_tax - gst_paid,
            "cpf_payable": bal["cpf_payable"] + payroll_cost - payroll_paid,
            "unmatched_customer_receipts": bal["unmatched_customer_receipts"] + unmatched_in,
            "accrued_costs": bal["accrued_costs"] + accrued_change,
        }
        assets_side = {"receivables", "inventory", "unmatched_supplier_payments"}
        changes = {
            k: (bal[k] - new[k]) if k in assets_side else (new[k] - bal[k])
            for k in WORKING_CAPITAL_LABELS
            if k != "accrued_costs" or bal[k] or new[k]  # shown only when there are accruals
        }
        acc_dep += depreciation
        loans -= principal
        other_borrowings += new_borrowing
        retained += net_profit
        drawings += drawn

        operating = net_profit + depreciation + sum(changes.values(), ZERO)
        financing = -principal + new_borrowing - drawn
        opening_cash = cash_flow_cash
        cash_flow_cash = opening_cash + operating + financing
        bank += sum((t.amount for t in month_txns), ZERO)

        within, after = _loan_split(books, loans, end)
        total_assets = (
            bank + new["receivables"] + new["inventory"] + new["unmatched_supplier_payments"]
            + fa_cost - acc_dep
        )  # fmt: skip
        total_liabilities = (
            new["payables"] + new["gst_payable"] + new["cpf_payable"]
            + new["unmatched_customer_receipts"] + new["accrued_costs"] + loans
            + other_borrowings
        )  # fmt: skip
        total_equity = share_capital + retained - drawings
        bs_diff = total_assets - total_liabilities - total_equity
        cash_diff = cash_flow_cash - bank
        months.append(
            MonthStatements(
                month=key,
                pnl=ProfitAndLoss(
                    revenue=revenue,
                    purchases=purchases,
                    cost_of_sales=cost_of_sales,
                    gross_profit=gross_profit,
                    operating_expenses=ordered,
                    total_operating_expenses=total_opex,
                    operating_profit=operating_profit,
                    other_income=other_income,
                    interest=interest,
                    net_profit=net_profit,
                ),
                balance_sheet=BalanceSheet(
                    as_of=end,
                    cash=bank,
                    receivables=new["receivables"],
                    inventory=new["inventory"],
                    unmatched_supplier_payments=new["unmatched_supplier_payments"],
                    fixed_assets_cost=fa_cost,
                    accumulated_depreciation=acc_dep,
                    fixed_assets_net=fa_cost - acc_dep,
                    total_assets=total_assets,
                    payables=new["payables"],
                    gst_payable=new["gst_payable"],
                    cpf_payable=new["cpf_payable"],
                    unmatched_customer_receipts=new["unmatched_customer_receipts"],
                    accrued_costs=new["accrued_costs"],
                    loans=loans,
                    loans_due_within_12_months=within,
                    loans_due_after_12_months=after,
                    other_borrowings=other_borrowings,
                    total_liabilities=total_liabilities,
                    share_capital=share_capital,
                    retained_earnings=retained,
                    owner_drawings=drawings,
                    total_equity=total_equity,
                ),
                cash_flow=CashFlow(
                    net_profit=net_profit,
                    add_depreciation=depreciation,
                    working_capital=changes,
                    operating=operating,
                    investing=ZERO,
                    financing_loan_principal=-principal,
                    new_borrowing=new_borrowing,
                    owner_drawings=-drawn,
                    financing=financing,
                    net_change=operating + financing,
                    opening_cash=opening_cash,
                    closing_cash=cash_flow_cash,
                ),
                checks=Checks(
                    balance_sheet_difference=bs_diff,
                    closing_cash_minus_bank=cash_diff,
                    balanced=bs_diff == 0,
                    cash_matches_bank=cash_diff == 0,
                ),
            )
        )
        bal = new
        prev_end = end

    if counted["uncategorised_out"]:
        warnings.append(
            f"{counted['uncategorised_out']} uncategorised payment(s) are counted as other "
            "operating costs (real money out that no rule labelled)."
        )
    if counted["uncategorised_in"]:
        warnings.append(
            f"{counted['uncategorised_in']} uncategorised receipt(s) are counted as other income."
        )
    if counted["loan"]:
        warnings.append(
            f"{counted['loan']} loan repayment(s) don't match the loan schedule, so all of it is "
            "treated as principal (interest may be understated)."
        )
    for loan in books.loans:
        rows = [r for r in books.schedule.get(loan.id, []) if r.due_date <= today]
        if rows and len(books.loans) == 1 and months:
            last = [r for r in rows if r.due_date <= months[-1].balance_sheet.as_of]
            if last and last[-1].balance_after != months[-1].balance_sheet.loans:
                warnings.append(
                    f"Loan balance {sgd(months[-1].balance_sheet.loans)} differs from the "
                    f"lender's schedule ({sgd(last[-1].balance_after)})."
                )
    return months, warnings


def _days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _instalment(books: _Books, txn: Transaction, used: set[tuple[str, int]]):
    """The schedule row a loan repayment pays: same month, same instalment amount."""
    for loan_id, rows in books.schedule.items():
        for r in rows:
            if (
                (loan_id, r.instalment_no) not in used
                and (r.due_date.year, r.due_date.month) == (txn.date.year, txn.date.month)
                and r.instalment == -txn.amount
            ):
                used.add((loan_id, r.instalment_no))
                return r
    return None


def _loan_split(
    books: _Books, balance: Decimal, end: date
) -> tuple[Decimal | None, Decimal | None]:
    """Principal due in the 12 months after `end` (from the schedule), and the rest."""
    if balance == 0:
        return ZERO, ZERO
    if not books.schedule:
        return None, None
    horizon = add_months(end, 12)
    within = sum(
        (
            r.principal
            for rows in books.schedule.values()
            for r in rows
            if end < r.due_date <= horizon
        ),
        ZERO,
    )
    within = min(within, balance)
    return within, balance - within


# --- Periods and the public functions --------------------------------------------------------

_MONTH_NAMES = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def month_label(key: str) -> str:
    """'2026-09' -> 'Sep 2026'."""
    return _label(key)


def _label(key: str) -> str:
    year, month = key.split("-")
    return f"{_MONTH_NAMES[int(month) - 1]} {year}"


def _period_months(
    available: list[str], kind: PeriodKind, month: str | None
) -> tuple[list[str], str, list[str]]:
    """The months a period covers (oldest first), its label, and warnings."""
    if month is None:
        month = available[-1]
    if month not in available:
        raise ValueError(
            f"No accrual statements for {month}: available months are {available[0]} to "
            f"{available[-1]} (complete months only)."
        )
    year, mon = (int(x) for x in month.split("-"))
    if kind == "month":
        return [month], _label(month), []
    if kind == "quarter":
        first = (mon - 1) // 3 * 3 + 1
        wanted = [f"{year}-{m:02d}" for m in range(first, mon + 1)]
        label = f"Q{(mon - 1) // 3 + 1} {year}" + ("" if mon % 3 == 0 else " to date")
    elif kind == "ytd":
        wanted = [f"{year}-{m:02d}" for m in range(1, mon + 1)]
        label = f"Jan-{_MONTH_NAMES[mon - 1]} {year} (year to date)"
    else:
        firsts = (add_months(date(year, mon, 1), -back) for back in range(11, -1, -1))
        wanted = [f"{d.year}-{d.month:02d}" for d in firsts]
        label = f"12 months to {_label(month)}"
    months = [m for m in wanted if m in available]
    warnings = []
    if len(months) < len(wanted):
        warnings.append(
            f"The books start in {_label(available[0])}, so this period covers only "
            f"{len(months)} of its {len(wanted)} months."
        )
    return months, label, warnings


def _sum_pnl(items: list[ProfitAndLoss]) -> ProfitAndLoss:
    lines: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for p in items:
        for k, v in p.operating_expenses.items():
            lines[k] += v
    totals = {
        name: sum((getattr(p, name) for p in items), ZERO)
        for name in ProfitAndLoss.model_fields
        if name != "operating_expenses"
    }
    return ProfitAndLoss(
        operating_expenses={k: lines[k] for k in OPEX_LABELS if k in lines}, **totals
    )


def _sum_cash_flow(items: list[CashFlow]) -> CashFlow:
    wc: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for c in items:
        for k, v in c.working_capital.items():
            wc[k] += v
    flows = {
        name: sum((getattr(c, name) for c in items), ZERO)
        for name in CashFlow.model_fields
        if name not in ("working_capital", "opening_cash", "closing_cash")
    }
    return CashFlow(
        working_capital=dict(wc),
        opening_cash=items[0].opening_cash,
        closing_cash=items[-1].closing_cash,
        **flows,
    )


def _ratio(numerator: Decimal, denominator: Decimal, unit: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(unit, ROUND_HALF_UP)


def _ratios(pnl: ProfitAndLoss, bs: BalanceSheet) -> Ratios:
    current_assets = bs.cash + bs.receivables + bs.inventory + bs.unmatched_supplier_payments
    loan_current = (
        bs.loans if bs.loans_due_within_12_months is None else bs.loans_due_within_12_months
    )
    current_liabilities = (
        bs.payables + bs.gst_payable + bs.cpf_payable + bs.unmatched_customer_receipts
        + bs.accrued_costs + bs.other_borrowings + loan_current
    )  # fmt: skip
    return Ratios(
        gross_margin=_ratio(pnl.gross_profit, pnl.revenue, RATIO),
        operating_margin=_ratio(pnl.operating_profit, pnl.revenue, RATIO),
        net_margin=_ratio(pnl.net_profit, pnl.revenue, RATIO),
        ebitda=pnl.operating_profit + pnl.operating_expenses.get("depreciation", ZERO),
        current_ratio=_ratio(current_assets, current_liabilities, TIMES),
        debt_ratio=_ratio(bs.total_liabilities, bs.total_assets, RATIO),
    )


def _drivers(pnl: ProfitAndLoss, cf: CashFlow, checks: Checks) -> list[Driver]:
    biggest = sorted(pnl.operating_expenses.items(), key=lambda kv: -kv[1])[:TOP_DRIVERS]
    drivers = [
        Driver(label=OPEX_LABELS[k], amount=v, detail="operating expense") for k, v in biggest
    ]
    moves = sorted(cf.working_capital.items(), key=lambda kv: -abs(kv[1]))
    for k, v in moves[:2]:
        if v != 0:
            detail = "cash released" if v > 0 else "cash tied up"
            drivers.append(Driver(label=WORKING_CAPITAL_LABELS[k], amount=v, detail=detail))
    balanced = "Balance sheet balances" if checks.balanced else "Balance sheet does NOT balance"
    bank = (
        "closing cash matches the bank"
        if checks.cash_matches_bank
        else "closing cash differs from the bank"
    )
    drivers.append(Driver(label="Checks", detail=f"{balanced}; {bank}"))
    return drivers


def describe_adjustment(store: Store, adj: Adjustment) -> str:
    """Plain-language description of an adjustment, built by code (names quoted are data)."""
    month = _label(adj.month)
    if adj.kind == "accrued_cost":
        line = OPEX_LABELS[CASH_OPEX[adj.line]].lower() if adj.line else "?"
        nxt = add_months(month_start(adj.month), 1)
        return (
            f"Accrued cost of {sgd(adj.amount or ZERO)} ({line}) in {month}, reversed in "
            f"{_label(f'{nxt.year}-{nxt.month:02d}')}"
        )
    if adj.kind == "relabel":
        txn = store.get_transaction(adj.business_id, adj.transaction_id or "")
        to = (
            "owner drawings (not a cost)"
            if adj.to_category is Cat.OWNER_DRAW
            else OPEX_LABELS[CASH_OPEX[adj.to_category]].lower()
            if adj.to_category in CASH_OPEX
            else str(adj.to_category)
        )
        return (
            f"Payment {txn.id} of {sgd(-txn.amount)} on {txn.date.isoformat()} counted as {to} "
            f"instead of {txn.category.value}"
        )
    return f"Stock at the end of {month} counted as {sgd(adj.amount or ZERO)}"


def _touches(adj: Adjustment, keys: list[str]) -> bool:
    """Whether an applied adjustment changes any month in `keys` (an accrual also reverses)."""
    months = {adj.month}
    if adj.kind == "accrued_cost":
        nxt = add_months(month_start(adj.month), 1)
        months.add(f"{nxt.year}-{nxt.month:02d}")
    if adj.kind == "stock_count":  # the next month opens from the corrected stock
        nxt = add_months(month_start(adj.month), 1)
        months.add(f"{nxt.year}-{nxt.month:02d}")
    return bool(months & set(keys))


def monthly_statements(
    store: Store,
    business_id: str,
    today: date,
    view: View = "with_adjustments",
    preview: Preview = ((), ()),
) -> tuple[list[MonthStatements], list[str], str | None]:
    """Every complete month's statements, the warnings, and the reason if there are none."""
    books = _read(store, business_id, view == "with_adjustments", preview)
    if isinstance(books, str):
        return [], [], books
    months, warnings = build_months(books, today)
    if not months:
        reason = (
            f"No complete month after the opening balance sheet "
            f"({books.opening_day.isoformat()}) yet."
        )
        return [], warnings, reason
    return months, warnings, None


def _loan_lines(store: Store, business_id: str, end: date) -> list[LoanLine]:
    lines = []
    horizon = add_months(end, 12)
    for loan in store.list_loans(business_id):
        rows = store.list_loan_schedule(business_id, loan.id)
        paid = [r for r in rows if r.due_date <= end]
        balance = paid[-1].balance_after if paid else loan.principal
        within = None
        if rows:
            due = sum((r.principal for r in rows if end < r.due_date <= horizon), ZERO)
            within = min(balance, due)
        lines.append(
            LoanLine(
                id=loan.id,
                lender=loan.lender,
                balance=balance,
                due_within_12_months=within,
                interest_rate_pct=loan.annual_rate_pct,
            )
        )
    return lines


def financial_statements(
    store: Store,
    business_id: str,
    today: date,
    period: PeriodKind = "month",
    month: str | None = None,
    include_monthly: bool = False,
    view: View = "with_adjustments",
) -> DomainResult[Statements | None]:
    """Accrual P&L, balance sheet and cash flow for a period ending in `month` (YYYY-MM,
    default the latest complete month). Value is None, with the reason, when the business has
    no accrual data. Raises ValueError for a month outside the books.

    view: "with_adjustments" (default) lays the owner's applied adjustments over the imported
    books; "as_imported" ignores them. Either way `adjustments` summarises the applied ones in
    the period with net profit both ways."""
    months, warnings, reason = monthly_statements(store, business_id, today, view)
    if reason is not None:
        return DomainResult(
            value=None,
            data_coverage=DataCoverage(period_start=today, period_end=today, record_count=0),
            warnings=[reason, *warnings],
        )
    by_key = {m.month: m for m in months}
    keys, label, period_warnings = _period_months(list(by_key), period, month)
    chosen = [by_key[k] for k in keys]
    pnl = _sum_pnl([m.pnl for m in chosen])
    cf = _sum_cash_flow([m.cash_flow for m in chosen])
    bs = chosen[-1].balance_sheet
    worst = max(
        chosen,
        key=lambda m: (
            abs(m.checks.balance_sheet_difference) + abs(m.checks.closing_cash_minus_bank)
        ),
    ).checks
    end = bs.as_of
    start = date(int(keys[0][:4]), int(keys[0][5:]), 1)
    assets = [
        AssetLine(
            id=a.id,
            name=a.name,
            acquired_on=a.acquired_on,
            cost=a.cost,
            accumulated_depreciation=_depreciation_to(a, end),
            net_book_value=a.cost - _depreciation_to(a, end),
        )
        for a in store.list_fixed_assets(business_id)
        if a.acquired_on <= end
    ]
    statements = Statements(
        period=label,
        start=start,
        end=end,
        months=keys,
        pnl=pnl,
        balance_sheet=bs,
        cash_flow=cf,
        checks=worst,
        ratios=_ratios(pnl, bs),
        fixed_assets=assets,
        loans=_loan_lines(store, business_id, end),
        monthly=chosen if include_monthly else [],
        view=view,
        adjustments=_adjustment_summary(store, business_id, today, view, keys, pnl),
    )
    return DomainResult(
        value=statements,
        drivers=_drivers(pnl, cf, worst),
        data_coverage=DataCoverage(
            period_start=start,
            period_end=end,
            record_count=len(store.list_transactions(business_id, start, end)),
        ),
        warnings=[
            "Accrual basis: sales and costs count when invoiced or incurred, not when paid; "
            "amounts exclude GST",
            *period_warnings,
            *warnings,
        ],
    )


def _adjustment_summary(
    store: Store,
    business_id: str,
    today: date,
    view: View,
    keys: list[str],
    pnl: ProfitAndLoss,
) -> AdjustmentSummary | None:
    applied = [a for a in store.list_adjustments(business_id, "applied") if _touches(a, keys)]
    if not applied:
        return None
    other: View = "as_imported" if view == "with_adjustments" else "with_adjustments"
    by_key = {m.month: m for m in monthly_statements(store, business_id, today, other)[0]}
    other_net = _sum_pnl([by_key[k].pnl for k in keys]).net_profit
    with_adj, imported = (
        (pnl.net_profit, other_net) if view == "with_adjustments" else (other_net, pnl.net_profit)
    )
    return AdjustmentSummary(
        count=len(applied),
        net_profit_as_imported=imported,
        net_profit_with_adjustments=with_adj,
        difference=with_adj - imported,
        applied=[
            AdjustmentLine(
                id=a.id,
                kind=a.kind,
                month=a.month,
                description=describe_adjustment(store, a),
                reason=a.reason,
            )
            for a in applied
        ],
    )


def only(statements: Statements, which: StatementKind) -> Statements:
    """The same result with only the asked-for statement filled in (keeps tool replies short)."""
    if which == "all":
        return statements
    update: dict = {name: None for name in ("pnl", "balance_sheet", "cash_flow") if name != which}
    if which != "balance_sheet":
        update["fixed_assets"] = []
        update["loans"] = []
    return statements.model_copy(update=update)


class AccrualMargins(CopilotModel):
    basis: Literal["accrual"] = "accrual"
    revenue: Money
    gross_margin: Decimal | None
    operating_margin: Decimal | None
    net_margin: Decimal | None
    net_profit: Money
    adjustments_included: int = 0  # owner's applied adjustments touching these months


def accrual_margins(
    store: Store, business_id: str, start: date, end: date, today: date
) -> tuple[AccrualMargins | None, str | None]:
    """Accrual margins for [start, end] when it is whole calendar months inside the books;
    otherwise None and the reason (for get_metrics)."""
    months, _, reason = monthly_statements(store, business_id, today)
    if reason is not None:
        return None, reason
    if start.day != 1 or month_end(end) != end:
        return None, "Accrual margins are only given for whole calendar months."
    wanted, d = [], start
    while d <= end:
        wanted.append(f"{d.year}-{d.month:02d}")
        d = month_end(d) + timedelta(days=1)
    by_key = {m.month: m for m in months}
    if any(k not in by_key for k in wanted):
        first, last = months[0].month, months[-1].month
        return None, f"Accrual figures cover {first} to {last} only (complete months)."
    pnl = _sum_pnl([by_key[k].pnl for k in wanted])
    margins = AccrualMargins(
        revenue=pnl.revenue,
        gross_margin=_ratio(pnl.gross_profit, pnl.revenue, RATIO),
        operating_margin=_ratio(pnl.operating_profit, pnl.revenue, RATIO),
        net_margin=_ratio(pnl.net_profit, pnl.revenue, RATIO),
        net_profit=pnl.net_profit,
        adjustments_included=sum(
            1 for a in store.list_adjustments(business_id, "applied") if _touches(a, wanted)
        ),
    )
    return margins, None
