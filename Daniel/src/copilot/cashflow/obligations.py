"""Obligations calendar: the known money in and out over the next few weeks.

A filtered view of the forecast. It keeps the items that come from real documents and fixed
costs (scheduled payments, open bills, recurring costs, open invoices) and drops the projected
future invoices and bills. No new arithmetic: amounts and the running balance come from the
forecast's own items, walked in date order.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.cashflow.forecast import WEEKS, Forecast
from copilot.schemas import CopilotModel, DomainResult, Driver, Money, UntrustedText

DEFAULT_WEEKS = 4

# Where each kind of item comes from, and how sure we are of its date and amount.
_CERTAINTY: dict[str, Literal["scheduled", "due", "estimated"]] = {
    "scheduled_payment": "scheduled",  # the owner confirmed it; runs on that date
    "open_bill": "due",  # a real bill, assumed paid on its due date
    "recurring": "estimated",  # detected from history (rent, payroll, ...)
    "open_invoice": "estimated",  # a real invoice; arrival date uses the customer's usual delay
}


class Obligation(CopilotModel):
    date: date
    label: UntrustedText
    amount: Money  # + money in, - money out
    kind: Literal["payment", "receipt"]
    source: str
    certainty: Literal["scheduled", "due", "estimated"]
    balance_after: Money  # forecast balance at the end of that day


class ObligationsCalendar(CopilotModel):
    start: date
    end: date
    items: list[Obligation]
    total_out: Money
    total_in: Money


def obligations_calendar(
    forecast: DomainResult[Forecast], weeks: int = DEFAULT_WEEKS
) -> DomainResult[ObligationsCalendar]:
    if not 1 <= weeks <= WEEKS:
        raise ValueError(f"weeks must be between 1 and {WEEKS}")
    fc = forecast.value
    start = fc.as_of + timedelta(days=1)
    end = fc.as_of + timedelta(days=7 * weeks)

    ordered = sorted(fc.items, key=lambda it: it.date)  # stable: keeps the forecast's order
    end_of_day: dict[date, Decimal] = {}  # every item counts, including projected ones
    balance = fc.start_balance
    for it in ordered:
        balance += it.amount
        end_of_day[it.date] = balance
    rows = [
        Obligation(
            date=it.date,
            label=it.label,
            amount=it.amount,
            kind="receipt" if it.amount > 0 else "payment",
            source=it.source,
            certainty=_CERTAINTY[it.source],
            balance_after=end_of_day[it.date],
        )
        for it in ordered
        if it.date <= end and it.source in _CERTAINTY
    ]

    payments = [r for r in rows if r.amount < 0]
    return DomainResult[ObligationsCalendar](
        value=ObligationsCalendar(
            start=start,
            end=end,
            items=rows,
            total_out=sum((-r.amount for r in payments), Decimal("0")),
            total_in=sum((r.amount for r in rows if r.amount > 0), Decimal("0")),
        ),
        drivers=[
            Driver(label=r.label, amount=r.amount, detail=f"{r.date.isoformat()} ({r.certainty})")
            for r in sorted(payments, key=lambda r: r.amount)[:5]
        ],
        data_coverage=forecast.data_coverage,
        warnings=forecast.warnings,
    )
