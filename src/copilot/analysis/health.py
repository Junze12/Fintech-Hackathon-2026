"""Business health measures for an owner and a lender (chunk 8).

- ageing: unpaid invoices and bills by days past due (invoice basis), plus who pays late
- cash_trend: monthly revenue, burn and net cash flow, and whether things are improving (cash)
- debt_service_cover: how many times operating cash covers loan repayments (cash basis)
- break_even_sales: monthly sales needed to cover fixed costs at the current margin (cash)

Pure and read-only. Every result says which basis it used. Uncategorised outflows are counted as
operating costs in DSCR and break-even (conservative: they are real money out that no rule
labelled), and the warning says so.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.analysis.compare import pct_change
from copilot.cashflow.summary import cash_summary
from copilot.dates import add_months
from copilot.reconcile import estimate_payment_delays
from copilot.schemas import (
    CategoryGroup,
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    Id,
    Money,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

CENT = Decimal("0.01")
RATIO = Decimal("0.0001")
TIMES = Decimal("0.01")
MIN_TREND_MONTHS = 6
DSCR_MONTHS = 12
BREAK_EVEN_MONTHS = 3
TOP_DOCUMENTS = 3

# --- Ageing (invoice basis) ------------------------------------------------------------------

Bucket = Literal["not_due", "1_30", "31_60", "61_90", "over_90"]
BUCKETS: list[tuple[Bucket, str]] = [
    ("not_due", "Not yet due"),
    ("1_30", "1-30 days overdue"),
    ("31_60", "31-60 days overdue"),
    ("61_90", "61-90 days overdue"),
    ("over_90", "Over 90 days overdue"),
]


def bucket_for(days_late: int) -> Bucket:
    if days_late <= 0:
        return "not_due"
    if days_late <= 30:
        return "1_30"
    if days_late <= 60:
        return "31_60"
    if days_late <= 90:
        return "61_90"
    return "over_90"


class AgeingBucket(CopilotModel):
    bucket: Bucket
    label: str
    amount: Money
    count: int


class AgedDocument(CopilotModel):
    id: Id
    number: UntrustedText
    counterparty_id: Id
    counterparty_name: UntrustedText
    due_date: date
    days_overdue: int  # 0 when not yet due
    outstanding: Money


class PaymentHabit(CopilotModel):
    customer_id: Id
    name: UntrustedText
    avg_days_late: Decimal  # mean days paid after the due date; negative = early
    paid_invoices_matched: int
    outstanding: Money
    overdue: Money
    paid_by_due_pct: Decimal | None = (
        None  # share of matched payments on or before due; None if none
    )


class Ageing(CopilotModel):
    as_of: date
    kind: Literal["receivables", "payables"]
    basis: Literal["invoice"] = "invoice"
    total: Money
    overdue: Money
    overdue_share: Decimal | None  # fraction of the total that is overdue
    buckets: list[AgeingBucket]
    oldest_overdue: list[AgedDocument]  # most days overdue first
    customers: list[PaymentHabit] = []  # receivables only: slowest payer first


def ageing(
    store: Store,
    business_id: str,
    as_of: date,
    kind: Literal["receivables", "payables"],
) -> DomainResult[Ageing]:
    """Unpaid documents at `as_of` (the simulated today: statuses are the current ones) by days
    past due. For receivables, also each customer's payment habit from matched receipts."""
    docs = (
        store.list_invoices(business_id, DocumentStatus.OPEN)
        if kind == "receivables"
        else store.list_bills(business_id, DocumentStatus.OPEN)
    )
    docs = [d for d in docs if d.issue_date <= as_of and d.amount > d.amount_paid]
    names = {c.id: c.name for c in store.list_counterparties(business_id)}

    amounts: dict[Bucket, Decimal] = defaultdict(Decimal)
    counts: dict[Bucket, int] = defaultdict(int)
    aged: list[AgedDocument] = []
    for d in docs:
        late = (as_of - d.due_date).days
        bucket = bucket_for(late)
        outstanding = d.amount - d.amount_paid
        amounts[bucket] += outstanding
        counts[bucket] += 1
        aged.append(
            AgedDocument(
                id=d.id,
                number=d.number,
                counterparty_id=d.counterparty_id,
                counterparty_name=names.get(d.counterparty_id, d.counterparty_id),
                due_date=d.due_date,
                days_overdue=max(late, 0),
                outstanding=outstanding,
            )
        )
    total = sum(amounts.values(), Decimal("0"))
    overdue = total - amounts["not_due"]
    oldest = sorted(
        (a for a in aged if a.days_overdue > 0),
        key=lambda a: (-a.days_overdue, -a.outstanding, a.id),
    )[:TOP_DOCUMENTS]

    noun = "invoices" if kind == "receivables" else "bills"
    warnings = [
        f"Invoice basis: built from unpaid {noun} as of {as_of.isoformat()}, not from bank balances"
    ]
    if any(d.amount_paid > 0 for d in docs):
        warnings.append(f"Some {noun} are part-paid; only the unpaid part is counted")
    if not docs:
        warnings.append(f"No unpaid {noun} as of {as_of.isoformat()}")

    habits: list[PaymentHabit] = []
    if kind == "receivables":
        delays = estimate_payment_delays(store, business_id)
        warnings += delays.warnings
        for cid, delay in delays.value.items():
            mine = [a for a in aged if a.counterparty_id == cid]
            habits.append(
                PaymentHabit(
                    customer_id=cid,
                    name=names.get(cid, cid),
                    avg_days_late=delay.mean_delay_days,
                    paid_invoices_matched=delay.matched,
                    paid_by_due_pct=(
                        (Decimal(100 * delay.paid_by_due) / delay.matched).quantize(Decimal("0.1"))
                        if delay.matched
                        else None
                    ),
                    outstanding=sum((a.outstanding for a in mine), Decimal("0")),
                    overdue=sum((a.outstanding for a in mine if a.days_overdue), Decimal("0")),
                )
            )
        habits.sort(key=lambda h: (-h.avg_days_late, h.customer_id))

    return DomainResult[Ageing](
        value=Ageing(
            as_of=as_of,
            kind=kind,
            total=total,
            overdue=overdue,
            overdue_share=(overdue / total).quantize(RATIO) if total > 0 else None,
            buckets=[
                AgeingBucket(bucket=b, label=label, amount=amounts[b], count=counts[b])
                for b, label in BUCKETS
            ],
            oldest_overdue=oldest,
            customers=habits,
        ),
        drivers=[
            Driver(
                label=f"{a.number} ({a.counterparty_name})",
                amount=a.outstanding,
                detail=f"{a.days_overdue} days overdue, due {a.due_date.isoformat()}",
            )
            for a in oldest
        ],
        data_coverage=DataCoverage(
            period_start=min((d.issue_date for d in docs), default=as_of),
            period_end=as_of,
            record_count=len(docs),
        ),
        warnings=warnings,
    )


# --- Cash trend (cash basis) -----------------------------------------------------------------


def complete_months(as_of: date, months: int) -> tuple[date, date]:
    """The last `months` whole calendar months up to as_of. as_of's own month counts only if
    as_of is its last day."""
    month_ends_today = (as_of + timedelta(days=1)).day == 1
    end = as_of if month_ends_today else date(as_of.year, as_of.month, 1) - timedelta(days=1)
    start = add_months(date(end.year, end.month, 1), -(months - 1))
    return start, end


class MonthFlow(CopilotModel):
    month: str  # YYYY-MM
    revenue: Money
    gross_burn: Money  # all money out (positive number), own transfers excluded
    net: Money  # all money in minus out
    revenue_growth: Decimal | None  # vs the month before; None for the first month or from 0


class CashTrend(CopilotModel):
    start: date
    end: date
    basis: Literal["cash"] = "cash"
    months: list[MonthFlow]  # oldest first
    avg_revenue_recent: Money  # last 3 months
    avg_revenue_before: Money | None  # the 3 months before that
    avg_burn_recent: Money
    avg_burn_before: Money | None
    avg_net_recent: Money
    avg_net_before: Money | None
    net_burn_recent: Money  # average monthly net outflow, last 3 months; 0 if cash-positive
    revenue_volatility: Decimal | None  # std dev / mean of monthly revenue
    direction: Literal["improving", "worsening", "steady", "not enough history"]


def _avg(values: list[Decimal]) -> Decimal:
    return (sum(values, Decimal("0")) / len(values)).quantize(CENT)


def cash_trend(
    store: Store, business_id: str, as_of: date, months: int = 12
) -> DomainResult[CashTrend]:
    if not 3 <= months <= 12:
        raise ValueError("months must be between 3 and 12")
    start, end = complete_months(as_of, months)
    first = store.list_transactions(business_id, end=end)[:1]
    partial_first = False
    if first and first[0].date > start:  # don't report months before the history begins
        start = min(date(first[0].date.year, first[0].date.month, 1), date(end.year, end.month, 1))
        partial_first = first[0].date.day > 1
    summary = cash_summary(store, business_id, start, end, "month")
    periods = summary.value.periods

    flows: list[MonthFlow] = []
    for p in periods:
        revenue = sum(
            (c.amount for c in p.by_category if c.category.group is CategoryGroup.REVENUE),
            Decimal("0"),
        )
        growth = pct_change(flows[-1].revenue, revenue) if flows else None
        flows.append(
            MonthFlow(
                month=p.start.strftime("%Y-%m"),
                revenue=revenue,
                gross_burn=p.outflows,
                net=p.net,
                revenue_growth=growth,
            )
        )

    recent, before = flows[-3:], flows[-6:-3]
    avg_net_recent = _avg([f.net for f in recent]) if recent else Decimal("0")
    avg_net_before = _avg([f.net for f in before]) if len(before) == 3 else None
    revenues = [f.revenue for f in flows]
    mean = sum(revenues, Decimal("0")) / len(revenues) if revenues else Decimal("0")
    volatility = None
    if len(revenues) >= 3 and mean > 0:
        variance = sum(((r - mean) ** 2 for r in revenues), Decimal("0")) / len(revenues)
        volatility = (variance.sqrt() / mean).quantize(RATIO)

    warnings = [
        "Cash basis: revenue and burn are counted when money moves; transfers between own "
        "accounts are left out"
    ]
    warnings += summary.warnings
    if partial_first:
        warnings.append(
            f"History starts on {first[0].date.isoformat()}, so the first month is partial"
        )
    if len(flows) < MIN_TREND_MONTHS:
        direction = "not enough history"
        warnings.append(
            f"Only {len(flows)} whole months of history; a trend needs {MIN_TREND_MONTHS}"
        )
    else:
        change = avg_net_recent - avg_net_before
        # "Steady" when the change is under 5% of the average monthly burn: noise, not a trend.
        threshold = _avg([f.gross_burn for f in flows]) * Decimal("0.05")
        direction = (
            "improving" if change > threshold else "worsening" if change < -threshold else "steady"
        )

    value = CashTrend(
        start=start,
        end=end,
        months=flows,
        avg_revenue_recent=_avg([f.revenue for f in recent]) if recent else Decimal("0"),
        avg_revenue_before=_avg([f.revenue for f in before]) if len(before) == 3 else None,
        avg_burn_recent=_avg([f.gross_burn for f in recent]) if recent else Decimal("0"),
        avg_burn_before=_avg([f.gross_burn for f in before]) if len(before) == 3 else None,
        avg_net_recent=avg_net_recent,
        avg_net_before=avg_net_before,
        net_burn_recent=max(-avg_net_recent, Decimal("0")),
        revenue_volatility=volatility,
        direction=direction,
    )
    drivers = [
        Driver(label="Average monthly revenue, last 3 months", amount=value.avg_revenue_recent),
        Driver(label="Average monthly money out, last 3 months", amount=-value.avg_burn_recent),
        Driver(label="Average monthly net cash flow, last 3 months", amount=avg_net_recent),
    ]
    if avg_net_before is not None:
        drivers.append(
            Driver(label="Average monthly net cash flow, 3 months before", amount=avg_net_before)
        )
    return DomainResult[CashTrend](
        value=value,
        drivers=drivers,
        data_coverage=summary.data_coverage,
        warnings=warnings,
    )


# --- Debt service cover and break-even (cash basis) ------------------------------------------

_NOT_OPERATING = {Cat.TRANSFER, Cat.LOAN_REPAYMENT, Cat.FINANCING_INFLOW, Cat.UNCATEGORISED}
UNCATEGORISED_NOTE = (
    "{n} uncategorised payments ({amount}) are counted as operating costs, to be safe; "
    "uncategorised receipts are left out"
)


class DebtServiceCover(CopilotModel):
    start: date
    end: date
    basis: Literal["cash"] = "cash"
    cash_available: Money  # operating cash flow after tax and owner drawings
    debt_service: Money  # loan repayments (positive number)
    dscr: Decimal | None  # cash_available / debt_service; None when there are no repayments


def debt_service_cover(
    store: Store, business_id: str, as_of: date, months: int = DSCR_MONTHS
) -> DomainResult[DebtServiceCover]:
    """Debt service coverage ratio over the last `months` whole months: money left after running
    the business (sales minus all operating costs, tax and owner drawings) divided by loan
    repayments. Below 1 means repayments are not covered by the business's own cash."""
    start, end = complete_months(as_of, months)
    txns = store.list_transactions(business_id, start=start, end=end)
    unlabelled = [t for t in txns if t.category is Cat.UNCATEGORISED and t.amount < 0]
    available = sum((t.amount for t in txns if t.category not in _NOT_OPERATING), Decimal("0"))
    available += sum((t.amount for t in unlabelled), Decimal("0"))
    service = -sum((t.amount for t in txns if t.category is Cat.LOAN_REPAYMENT), Decimal("0"))

    warnings = ["Cash basis: uses bank transactions, not audited accounts"]
    dscr = None
    if service > 0:
        dscr = (available / service).quantize(TIMES)
        warnings.append(
            "The data has loan repayments but no loan balance or interest/principal split, so "
            "leverage and interest cover can't be measured"
        )
        if dscr < 1:
            warnings.append("Below 1.0: the business's own cash did not cover its loan repayments")
    else:
        warnings.append("No loan repayments in this period, so there is no debt to cover")
    if unlabelled:
        warnings.append(
            UNCATEGORISED_NOTE.format(
                n=len(unlabelled), amount=sgd(sum(t.amount for t in unlabelled))
            )
        )

    return DomainResult[DebtServiceCover](
        value=DebtServiceCover(
            start=start, end=end, cash_available=available, debt_service=service, dscr=dscr
        ),
        drivers=[
            Driver(label="Cash from operations after tax and drawings", amount=available),
            Driver(label="Loan repayments", amount=-service),
        ],
        data_coverage=DataCoverage(period_start=start, period_end=end, record_count=len(txns)),
        warnings=warnings,
    )


class BreakEven(CopilotModel):
    start: date
    end: date
    basis: Literal["cash"] = "cash"
    avg_monthly_revenue: Money
    avg_monthly_fixed_costs: Money  # operating expenses + uncategorised payments
    gross_margin: Decimal | None
    break_even_monthly_sales: Money | None  # None when the margin is zero or negative
    headroom: Money | None  # avg monthly revenue - break-even sales (negative = below)


def break_even_sales(
    store: Store, business_id: str, as_of: date, months: int = BREAK_EVEN_MONTHS
) -> DomainResult[BreakEven]:
    """Monthly sales needed to cover fixed operating costs at the recent gross margin:
    average monthly operating expenses / gross margin, over the last `months` whole months."""
    start, end = complete_months(as_of, months)
    txns = store.list_transactions(business_id, start=start, end=end)
    revenue = sum(
        (t.amount for t in txns if t.category.group is CategoryGroup.REVENUE), Decimal("0")
    )
    cogs = -sum((t.amount for t in txns if t.category is Cat.COGS), Decimal("0"))
    unlabelled = [t for t in txns if t.category is Cat.UNCATEGORISED and t.amount < 0]
    fixed = -sum(
        (t.amount for t in txns if t.category.group is CategoryGroup.OPEX), Decimal("0")
    ) - sum((t.amount for t in unlabelled), Decimal("0"))

    avg_revenue = (revenue / months).quantize(CENT)
    avg_fixed = (fixed / months).quantize(CENT)
    warnings = [
        "Cash basis: stock bought in one month and sold in another makes the margin swing; "
        f"averaging {months} months smooths some of that",
        "Fixed costs are operating expenses (payroll, rent, utilities, ...); tax and loan "
        "repayments are not included",
    ]
    if unlabelled:
        warnings.append(
            UNCATEGORISED_NOTE.format(
                n=len(unlabelled), amount=sgd(sum(t.amount for t in unlabelled))
            )
        )
    margin = break_even = headroom = None
    if revenue > 0:
        margin = ((revenue - cogs) / revenue).quantize(RATIO)
    if margin is not None and margin > 0:
        break_even = (fixed / months / margin).quantize(CENT)
        headroom = avg_revenue - break_even
        if headroom < 0:
            warnings.append("Recent sales are below the break-even level")
    else:
        warnings.append(
            "No positive gross margin in this period, so a break-even level can't be calculated"
        )

    return DomainResult[BreakEven](
        value=BreakEven(
            start=start,
            end=end,
            avg_monthly_revenue=avg_revenue,
            avg_monthly_fixed_costs=avg_fixed,
            gross_margin=margin,
            break_even_monthly_sales=break_even,
            headroom=headroom,
        ),
        drivers=[
            Driver(label="Average monthly sales received", amount=avg_revenue),
            Driver(label="Average monthly fixed costs", amount=-avg_fixed),
        ],
        data_coverage=DataCoverage(period_start=start, period_end=end, record_count=len(txns)),
        warnings=warnings,
    )
