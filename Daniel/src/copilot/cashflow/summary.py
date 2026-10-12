"""Cash-flow summaries: money in and out by category, per month or per week (cash basis).

Built from bank transactions only (what actually moved). Transfers between the business's own
accounts are left out, because they are neither money in nor money out of the business.
Uncategorised flows (anything no categorisation rule matched, at import or when the sandbox
posted it) are kept as their own line and flagged, never dropped.
Read-only: never writes to the store.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.dates import add_months, week_start
from copilot.schemas import (
    CopilotModel,
    DataCoverage,
    DomainResult,
    Driver,
    Money,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

Granularity = Literal["month", "week"]
MAX_PERIODS = 60  # keeps a week-by-week summary over several years from flooding the chat


class CategoryFlow(CopilotModel):
    category: Cat
    amount: Money  # signed: + money in, - money out


class PeriodSummary(CopilotModel):
    start: date
    end: date
    inflows: Money
    outflows: Money  # positive number: total money out
    net: Money
    by_category: list[CategoryFlow]  # money in first, then biggest outflows


class CashSummary(CopilotModel):
    start: date
    end: date
    granularity: Granularity
    periods: list[PeriodSummary]
    total_inflows: Money
    total_outflows: Money
    net: Money
    by_category: list[CategoryFlow]


def _periods(start: date, end: date, granularity: Granularity) -> list[tuple[date, date]]:
    """Calendar months or Mon-Sun weeks covering [start, end], clipped to the range."""
    spans = []
    if granularity == "week":
        first = week_start(start)
        while first <= end:
            last = first + timedelta(days=6)
            spans.append((max(first, start), min(last, end)))
            first = last + timedelta(days=1)
    else:
        first = date(start.year, start.month, 1)
        while first <= end:
            following = add_months(first, 1)
            spans.append((max(first, start), min(following - timedelta(days=1), end)))
            first = following
    return spans


def _by_category(flows: dict[Cat, Decimal]) -> list[CategoryFlow]:
    # Money in first (largest first), then money out (largest first).
    ordered = sorted(flows.items(), key=lambda kv: (kv[1] < 0, -abs(kv[1]), kv[0].value))
    return [CategoryFlow(category=c, amount=a) for c, a in ordered if a != 0]


def cash_summary(
    store: Store,
    business_id: str,
    start: date,
    end: date,
    granularity: Granularity = "month",
) -> DomainResult[CashSummary]:
    if end < start:
        raise ValueError("end must not be before start")
    spans = _periods(start, end, granularity)
    if len(spans) > MAX_PERIODS:
        raise ValueError(
            f"{len(spans)} {granularity}s requested; the limit is {MAX_PERIODS}. "
            "Use a shorter range or monthly periods."
        )
    txns = [
        t
        for t in store.list_transactions(business_id, start=start, end=end)
        if t.category is not Cat.TRANSFER
    ]

    per_period: list[dict[Cat, Decimal]] = [defaultdict(Decimal) for _ in spans]
    totals: dict[Cat, Decimal] = defaultdict(Decimal)
    index = 0
    for t in sorted(txns, key=lambda t: t.date):
        while spans[index][1] < t.date:
            index += 1
        per_period[index][t.category] += t.amount
        totals[t.category] += t.amount

    periods = []
    for (p_start, p_end), flows in zip(spans, per_period, strict=True):
        inflows = sum((a for a in flows.values() if a > 0), Decimal("0"))
        outflows = -sum((a for a in flows.values() if a < 0), Decimal("0"))
        periods.append(
            PeriodSummary(
                start=p_start,
                end=p_end,
                inflows=inflows,
                outflows=outflows,
                net=inflows - outflows,
                by_category=_by_category(flows),
            )
        )
    # Totals use per-transaction signs, so a category with refunds still adds up correctly.
    total_in = sum((t.amount for t in txns if t.amount > 0), Decimal("0"))
    total_out = -sum((t.amount for t in txns if t.amount < 0), Decimal("0"))

    warnings = []
    if not txns:
        warnings.append(f"No transactions between {start.isoformat()} and {end.isoformat()}.")
    uncategorised = [t for t in txns if t.category is Cat.UNCATEGORISED]
    if uncategorised:
        warnings.append(
            f"{len(uncategorised)} transactions ({sgd(sum(t.amount for t in uncategorised))} "
            "net) are not categorised yet and are shown as 'uncategorised'."
        )

    by_category = _by_category(totals)
    outflow_drivers = [f for f in by_category if f.amount < 0][:5]
    return DomainResult[CashSummary](
        value=CashSummary(
            start=start,
            end=end,
            granularity=granularity,
            periods=periods,
            total_inflows=total_in,
            total_outflows=total_out,
            net=total_in - total_out,
            by_category=by_category,
        ),
        drivers=[
            Driver(label=f.category.value.replace("_", " "), amount=f.amount)
            for f in outflow_drivers
        ],
        data_coverage=DataCoverage(period_start=start, period_end=end, record_count=len(txns)),
        warnings=warnings,
    )
