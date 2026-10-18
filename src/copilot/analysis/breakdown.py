"""Expense breakdown: spending by category with its share and the change from a prior period.

Cash basis, built on cashflow.summary.cash_summary (no second grouping of transactions).
Outflows only; transfers between the business's own accounts are already left out there.
Read-only.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from copilot.analysis.compare import Period, pct_change, resolve_periods, unequal_warning
from copilot.analysis.metrics import RATIO
from copilot.cashflow.summary import cash_summary
from copilot.schemas import (
    CategoryGroup,
    CopilotModel,
    DataCoverage,
    DomainResult,
    Driver,
    Money,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store


class ExpenseLine(CopilotModel):
    category: Cat
    group: CategoryGroup
    amount: Money  # spend in the current period, as a positive number
    share: Decimal | None  # fraction of total spend in the current period
    previous: Money  # spend in the previous period, positive
    change: Money  # amount - previous (positive = spent more)
    pct_change: Decimal | None
    status: Literal["new", "stopped"] | None  # spent in only one of the two periods


class ExpenseBreakdown(CopilotModel):
    current: Period
    previous: Period
    basis: Literal["cash"] = "cash"
    total: Money
    previous_total: Money
    change: Money
    pct_change: Decimal | None
    lines: list[ExpenseLine]  # largest current spend first; stopped categories last


def _spend(store: Store, business_id: str, period: Period):
    summary = cash_summary(store, business_id, period.start, period.end, "month")
    spend = {f.category: -f.amount for f in summary.value.by_category if f.amount < 0}
    return spend, summary


def expense_breakdown(
    store: Store,
    business_id: str,
    start: date,
    end: date,
    compare_start: date | None = None,
    compare_end: date | None = None,
) -> DomainResult[ExpenseBreakdown]:
    current, previous = resolve_periods(start, end, compare_start, compare_end)
    now, now_summary = _spend(store, business_id, current)
    before, before_summary = _spend(store, business_id, previous)
    total = sum(now.values(), Decimal("0"))
    previous_total = sum(before.values(), Decimal("0"))

    lines = []
    for category in set(now) | set(before):
        amount = now.get(category, Decimal("0"))
        prior = before.get(category, Decimal("0"))
        lines.append(
            ExpenseLine(
                category=category,
                group=category.group,
                amount=amount,
                share=(amount / total).quantize(RATIO) if total > 0 else None,
                previous=prior,
                change=amount - prior,
                pct_change=pct_change(prior, amount),
                status="new" if prior == 0 else "stopped" if amount == 0 else None,
            )
        )
    lines.sort(key=lambda line: (line.amount == 0, -line.amount, -line.previous, line.category))

    warnings = [
        "Cash basis: spending is counted when money leaves the bank. Transfers between your "
        "own accounts are left out; loan repayments and tax are included and labelled by group"
    ]
    for label, summary in (("previous", before_summary), ("current", now_summary)):
        warnings.extend(f"{label} period: {w}" for w in summary.warnings)
    warnings.extend(unequal_warning(current, previous))

    biggest_moves = sorted(lines, key=lambda line: (-abs(line.change), line.category))[:3]
    return DomainResult[ExpenseBreakdown](
        value=ExpenseBreakdown(
            current=current,
            previous=previous,
            total=total,
            previous_total=previous_total,
            change=total - previous_total,
            pct_change=pct_change(previous_total, total),
            lines=lines,
        ),
        drivers=[
            Driver(label=line.category.value.replace("_", " "), amount=line.change)
            for line in biggest_moves
            if line.change != 0
        ],
        data_coverage=DataCoverage(
            period_start=min(previous.start, current.start),
            period_end=max(previous.end, current.end),
            record_count=before_summary.data_coverage.record_count
            + now_summary.data_coverage.record_count,
        ),
        warnings=warnings,
    )
