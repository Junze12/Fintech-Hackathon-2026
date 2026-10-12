"""What-if: change the forecast's items, walk them again, and compare with the base case.

A scenario is a short list of changes (at most 5):
  collect_on_time  an open invoice is paid on its due date (or within 7 days if already overdue)
  delay_receipt    an invoice, or every receipt from one customer, arrives N days later
  delay_payment    an open bill is paid N days later
  add_one_off      a single extra payment or receipt (e.g. equipment purchase)
  add_monthly      a new monthly cost or income from a start date (e.g. a new hire)
  pause_recurring  a recurring cost (e.g. marketing) stops until a date
Ids are checked against this business's own records; unknown ids are an error, never guessed.
Read-only: the base forecast and the store are never changed. recommend.py reuses these changes.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from copilot.cashflow.forecast import (
    LATE_RECEIPT_DAYS,
    Forecast,
    ForecastItem,
    Gap,
    LowPoint,
    balance_path,
    find_gaps,
    horizon_end,
    walk,
)
from copilot.dates import add_months, clamp_day
from copilot.schemas import (
    CopilotModel,
    CounterpartyKind,
    DocumentStatus,
    DomainResult,
    Driver,
    Id,
    Money,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import NotFoundError, Store

MAX_CHANGES = 5
MAX_DELAY_DAYS = 120
Label = Annotated[str, StringConstraints(min_length=1, max_length=80)]


class ScenarioError(ValueError):
    """A change refers to something that doesn't exist or can't be changed."""


class CollectOnTime(CopilotModel):
    kind: Literal["collect_on_time"] = "collect_on_time"
    invoice_id: Id


class DelayReceipt(CopilotModel):
    kind: Literal["delay_receipt"] = "delay_receipt"
    invoice_id: Id | None = None
    customer_id: Id | None = None
    days: int = Field(ge=1, le=MAX_DELAY_DAYS)

    @model_validator(mode="after")
    def _one_target(self) -> DelayReceipt:
        if (self.invoice_id is None) == (self.customer_id is None):
            raise ValueError("give exactly one of invoice_id or customer_id")
        return self


class DelayPayment(CopilotModel):
    kind: Literal["delay_payment"] = "delay_payment"
    bill_id: Id
    days: int = Field(ge=1, le=MAX_DELAY_DAYS)


class AddOneOff(CopilotModel):
    kind: Literal["add_one_off"] = "add_one_off"
    amount: Money = Field(description="+ money in, - money out")
    date: date
    label: Label

    @model_validator(mode="after")
    def _non_zero(self) -> AddOneOff:
        if self.amount == 0:
            raise ValueError("amount must not be zero")
        return self


class AddMonthly(CopilotModel):
    kind: Literal["add_monthly"] = "add_monthly"
    amount: Money = Field(description="+ money in, - money out, per month")
    start: date
    label: Label

    @model_validator(mode="after")
    def _non_zero(self) -> AddMonthly:
        if self.amount == 0:
            raise ValueError("amount must not be zero")
        return self


class PauseRecurring(CopilotModel):
    kind: Literal["pause_recurring"] = "pause_recurring"
    category: Cat
    until: date = Field(description="last day of the pause (inclusive)")


Change = Annotated[
    CollectOnTime | DelayReceipt | DelayPayment | AddOneOff | AddMonthly | PauseRecurring,
    Field(discriminator="kind"),
]


class ItemChange(CopilotModel):
    label: UntrustedText
    amount: Money
    from_date: date | None  # None: a new item
    to_date: date | None  # None: moved past the end of the forecast


class WeekDiff(CopilotModel):
    week: int
    start: date
    end: date
    base_end_balance: Money
    scenario_end_balance: Money
    difference: Money


class WeekRun(CopilotModel):
    """Consecutive weeks whose end balance differs from the base by the same amount."""

    first_week: int
    last_week: int
    start: date
    end: date
    difference: Money  # per week, scenario - base


class GapChange(CopilotModel):
    """A stretch below zero that exists in both cases but got deeper, shallower or longer."""

    before: list[Gap]  # base gaps it overlaps (several if the scenario merged them)
    after: Gap
    worse: bool  # deeper low, or more days below zero


class WhatIf(CopilotModel):
    changes: list[Change]
    base_low: LowPoint
    scenario_low: LowPoint
    low_point_change: Money  # scenario low balance - base low balance (+ = better)
    base_first_below_zero: date | None
    scenario_first_below_zero: date | None
    base_end_balance: Money
    scenario_end_balance: Money
    weeks: list[WeekDiff]
    week_runs: list[WeekRun]  # only weeks that differ, grouped
    base_gaps: list[Gap]  # stretches below zero
    scenario_gaps: list[Gap]
    gaps_closed: list[Gap]  # base gaps with no day below zero in the scenario
    gaps_new: list[Gap]  # scenario gaps that don't overlap any base gap
    gaps_changed: list[GapChange]  # overlapping gaps whose depth or length changed
    timing_only: bool  # only moves money in time: same total, same end balance
    changed_items: list[ItemChange]
    notes: list[UntrustedText]  # what each change did, in plain words


def week_runs(diffs: list[WeekDiff]) -> list[WeekRun]:
    runs: list[WeekRun] = []
    for d in diffs:
        if d.difference == 0:
            continue
        last = runs[-1] if runs else None
        if last and last.last_week == d.week - 1 and last.difference == d.difference:
            runs[-1] = last.model_copy(update={"last_week": d.week, "end": d.end})
        else:
            runs.append(
                WeekRun(
                    first_week=d.week,
                    last_week=d.week,
                    start=d.start,
                    end=d.end,
                    difference=d.difference,
                )
            )
    return runs


def _overlaps(a: Gap, b: Gap) -> bool:
    return a.start <= b.end and b.start <= a.end


def first_below(path: list[tuple[date, Decimal]], target: Decimal = Decimal("0")) -> date | None:
    return next((d for d, b in path if b < target), None)


def _shift(it: ForecastItem, to: date, last: date) -> tuple[ForecastItem | None, ItemChange]:
    change = ItemChange(
        label=it.label, amount=it.amount, from_date=it.date, to_date=to if to <= last else None
    )
    return (it.model_copy(update={"date": to}) if to <= last else None), change


def apply_changes(
    store: Store, business_id: str, forecast: Forecast, changes: list[Change]
) -> tuple[list[ForecastItem], list[ItemChange], list[str]]:
    """The forecast's items with `changes` applied, plus what changed and a note per change."""
    if len(changes) > MAX_CHANGES:
        raise ScenarioError(f"at most {MAX_CHANGES} changes per scenario")
    first, last = forecast.as_of + timedelta(days=1), horizon_end(forecast.as_of)
    items = list(forecast.items)
    changed: list[ItemChange] = []
    notes: list[str] = []

    def move(match, to_date, what: str) -> None:
        nonlocal items
        kept: list[ForecastItem] = []
        moved = 0
        for it in items:
            if match(it):
                new_date = to_date(it)
                if new_date != it.date:
                    new_item, change = _shift(it, new_date, last)
                    changed.append(change)
                    moved += 1
                    if new_item is not None:
                        kept.append(new_item)
                    else:
                        notes.append(
                            f"{it.label} moves past the end of the forecast ({last.isoformat()}), "
                            "so it drops out of the 13 weeks."
                        )
                    continue
            kept.append(it)
        items = kept
        if moved == 0:
            notes.append(f"{what}: nothing to move within the forecast.")

    def invoice(doc_id: str):
        try:
            doc = store.get_document(business_id, "invoice", doc_id)
        except NotFoundError:
            raise ScenarioError(f"invoice {doc_id} not found for this business") from None
        if doc.status is not DocumentStatus.OPEN:
            raise ScenarioError(f"invoice {doc.number} is already paid")
        return doc

    for c in changes:
        if isinstance(c, CollectOnTime):
            inv = invoice(c.invoice_id)
            on_time = max(inv.due_date, forecast.as_of + timedelta(days=LATE_RECEIPT_DAYS))
            move(
                lambda it, i=inv: it.source == "open_invoice" and it.ref == i.id,
                lambda it, d=on_time: min(it.date, d),  # never later than already expected
                f"Invoice {inv.number}",
            )
            notes.append(
                f"Invoice {inv.number} is assumed paid by {on_time.isoformat()} "
                + ("(its due date)." if on_time == inv.due_date else "(it is already overdue).")
            )
        elif isinstance(c, DelayReceipt):
            if c.invoice_id is not None:
                inv = invoice(c.invoice_id)
                move(
                    lambda it, i=inv: it.source == "open_invoice" and it.ref == i.id,
                    lambda it, n=c.days: it.date + timedelta(days=n),
                    f"Invoice {inv.number}",
                )
                notes.append(f"Invoice {inv.number} arrives {c.days} days later than expected.")
            else:
                customers = {
                    p.id: p
                    for p in store.list_counterparties(business_id)
                    if p.kind is CounterpartyKind.CUSTOMER
                }
                if c.customer_id not in customers:
                    raise ScenarioError(f"customer {c.customer_id} not found for this business")
                move(
                    lambda it, cid=c.customer_id: it.counterparty_id == cid and it.amount > 0,
                    lambda it, n=c.days: it.date + timedelta(days=n),
                    customers[c.customer_id].name,
                )
                notes.append(
                    f"Every payment from {customers[c.customer_id].name} arrives {c.days} days "
                    "later than expected."
                )
        elif isinstance(c, DelayPayment):
            try:
                bill = store.get_document(business_id, "bill", c.bill_id)
            except NotFoundError:
                raise ScenarioError(f"bill {c.bill_id} not found for this business") from None
            if bill.status is not DocumentStatus.OPEN:
                raise ScenarioError(f"bill {bill.number} is already paid")
            move(
                lambda it, b=bill: it.source == "open_bill" and it.ref == b.id,
                lambda it, n=c.days: it.date + timedelta(days=n),
                f"Bill {bill.number}",
            )
            notes.append(f"Bill {bill.number} is paid {c.days} days later than its due date.")
        elif isinstance(c, AddOneOff):
            if not first <= c.date <= last:
                raise ScenarioError(
                    f"date must be within the forecast ({first.isoformat()} to {last.isoformat()})"
                )
            items.append(
                ForecastItem(date=c.date, amount=c.amount, source="what_if", label=c.label)
            )
            changed.append(
                ItemChange(label=c.label, amount=c.amount, from_date=None, to_date=c.date)
            )
            notes.append(f"Adds {c.label}: {sgd(c.amount)} on {c.date.isoformat()}.")
        elif isinstance(c, PauseRecurring):
            paused = [
                it
                for it in items
                if it.source == "recurring" and it.ref == c.category.value and it.date <= c.until
            ]
            if not paused:
                raise ScenarioError(
                    f"no recurring {c.category.value} payments in the forecast before "
                    f"{c.until.isoformat()}"
                )
            items = [it for it in items if it not in paused]
            changed += [
                ItemChange(label=it.label, amount=it.amount, from_date=it.date, to_date=None)
                for it in paused
            ]
            notes.append(
                f"{c.category.value.replace('_', ' ')} is paused until {c.until.isoformat()}: "
                f"{len(paused)} payments ({sgd(-sum(it.amount for it in paused))}) skipped."
            )
        else:  # AddMonthly
            if not first <= c.start <= last:
                raise ScenarioError(
                    f"start must be within the forecast ({first.isoformat()} to {last.isoformat()})"
                )
            when, n = c.start, 0
            while when <= last:
                items.append(
                    ForecastItem(date=when, amount=c.amount, source="what_if", label=c.label)
                )
                changed.append(
                    ItemChange(label=c.label, amount=c.amount, from_date=None, to_date=when)
                )
                n += 1
                following = add_months(when, 1)
                when = clamp_day(following.year, following.month, c.start.day)
            notes.append(
                f"Adds {c.label}: {sgd(c.amount)} a month from {c.start.isoformat()} "
                f"({n} times within the forecast)."
            )
    items.sort(key=lambda it: (it.date, it.source, it.label))
    return items, changed, notes


def what_if(
    store: Store, business_id: str, forecast: DomainResult[Forecast], changes: list[Change]
) -> DomainResult[WhatIf]:
    base = forecast.value
    items, changed, notes = apply_changes(store, business_id, base, changes)
    weeks, low = walk(base.as_of, base.start_balance, items)
    base_path = balance_path(base.as_of, base.start_balance, base.items)
    path = balance_path(base.as_of, base.start_balance, items)
    diffs = [
        WeekDiff(
            week=b.week,
            start=b.start,
            end=b.end,
            base_end_balance=b.end_balance,
            scenario_end_balance=s.end_balance,
            difference=s.end_balance - b.end_balance,
        )
        for b, s in zip(base.weeks, weeks, strict=True)
    ]
    runs = week_runs(diffs)
    base_gaps, scenario_gaps = find_gaps(base_path), find_gaps(path)
    below = {d for d, b in path if b < 0}
    closed = [g for g in base_gaps if not any(g.start <= d <= g.end for d in below)]
    new = [g for g in scenario_gaps if not any(_overlaps(g, b) for b in base_gaps)]
    changed_gaps = []
    for g in scenario_gaps:
        olds = [b for b in base_gaps if _overlaps(g, b)]
        if not olds:
            continue
        old_low = min(b.lowest_balance for b in olds)
        old_days = sum((b.end - b.start).days + 1 for b in olds)
        new_days = (g.end - g.start).days + 1
        if g.lowest_balance != old_low or new_days != old_days:
            worse = g.lowest_balance < old_low or (
                g.lowest_balance == old_low and new_days > old_days
            )
            changed_gaps.append(GapChange(before=olds, after=g, worse=worse))
    timing_only = bool(changed) and all(
        c.from_date is not None and c.to_date is not None for c in changed
    )
    return DomainResult[WhatIf](
        value=WhatIf(
            changes=changes,
            base_low=base.low_point,
            scenario_low=low,
            low_point_change=low.balance - base.low_point.balance,
            base_first_below_zero=first_below(base_path),
            scenario_first_below_zero=first_below(path),
            base_end_balance=base.weeks[-1].end_balance,
            scenario_end_balance=weeks[-1].end_balance,
            weeks=diffs,
            week_runs=runs,
            base_gaps=base_gaps,
            scenario_gaps=scenario_gaps,
            gaps_closed=closed,
            gaps_new=new,
            gaps_changed=changed_gaps,
            timing_only=timing_only,
            changed_items=changed,
            notes=notes,
        ),
        drivers=[
            Driver(
                label=(
                    f"Week {r.first_week}"
                    + (f"-{r.last_week}" if r.last_week > r.first_week else "")
                    + f" ({r.start.isoformat()} to {r.end.isoformat()})"
                ),
                amount=r.difference,
            )
            for r in sorted(runs, key=lambda r: abs(r.difference), reverse=True)[:3]
        ],
        data_coverage=forecast.data_coverage,
        warnings=forecast.warnings,
    )
