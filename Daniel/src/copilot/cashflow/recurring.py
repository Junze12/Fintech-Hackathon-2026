"""Detect recurring fixed costs (rent, payroll, utilities, ...) from transaction history.

Scope: categorised outflows with no counterparty. Counterparty flows (customer receipts,
supplier payments) are forecast from invoices and bills instead, so they are left out here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from copilot.dates import add_months, clamp_day, month_keys
from copilot.schemas import CopilotModel, Money, Transaction
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

CLUSTER_GAP_DAYS = 5
MONTHLY_MIN_OF_6 = 5
QUARTERLY_MIN_OF_12 = 3
EXCLUDED = {Cat.TRANSFER, Cat.UNCATEGORISED}


class RecurringItem(CopilotModel):
    category: Cat
    cadence: Literal["monthly", "quarterly"]
    amount: Money  # signed: negative = money out
    day: int
    next_date: date
    occurrences: int
    label: str


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return ((ordered[mid - 1] + ordered[mid]) / 2).quantize(Decimal("0.01"))


def _clusters(txns: list[Transaction]) -> list[list[Transaction]]:
    """Split one category's transactions into groups paid around the same day of month."""
    ordered = sorted(txns, key=lambda t: t.date.day)
    groups: list[list[Transaction]] = []
    for t in ordered:
        if groups and t.date.day - groups[-1][-1].date.day <= CLUSTER_GAP_DAYS:
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def _next_date(day: int, months: set[int] | None, after: date) -> date:
    for offset in range(0, 13):
        first = add_months(date(after.year, after.month, 1), offset)
        if months is not None and first.month % 3 not in months:
            continue
        when = clamp_day(first.year, first.month, day)
        if when > after:
            return when
    raise ValueError("no next occurrence within a year")


def detect_recurring(store: Store, business_id: str, as_of: date) -> list[RecurringItem]:
    candidates = [
        t
        for t in store.list_transactions(business_id, end=as_of)
        if t.amount < 0 and t.counterparty_id is None and t.category not in EXCLUDED
    ]
    by_category: dict[Cat, list[Transaction]] = defaultdict(list)
    for t in candidates:
        by_category[t.category].append(t)

    last6 = set(month_keys(as_of, 6))
    last12 = set(month_keys(as_of, 12))
    items: list[RecurringItem] = []
    for category, txns in sorted(by_category.items()):
        for group in _clusters(txns):
            per_month: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
            for t in group:
                per_month[(t.date.year, t.date.month)] += t.amount
            months_seen = set(per_month)
            day = sorted(t.date.day for t in group)[len(group) // 2]
            recent = [per_month[k] for k in sorted(per_month)[-3:]]

            if len(months_seen & last6) >= MONTHLY_MIN_OF_6:
                cadence, phase = "monthly", None
            else:
                in_year = months_seen & last12
                phases = {m % 3 for _, m in in_year}
                if len(in_year) >= QUARTERLY_MIN_OF_12 and len(phases) == 1:
                    cadence, phase = "quarterly", phases
                else:
                    continue
            items.append(
                RecurringItem(
                    category=category,
                    cadence=cadence,
                    amount=_median(recent),
                    day=day,
                    next_date=_next_date(day, phase, as_of),
                    occurrences=len(group),
                    label=f"{category.value.replace('_', ' ')} ({cadence}, around day {day})",
                )
            )
    return items
