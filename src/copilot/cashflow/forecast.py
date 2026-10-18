"""Rolling 13-week cash forecast (what-if and recommendations build on it: scenarios.py,
recommend.py).

Built from, in order of certainty:
  0. payments the owner has scheduled through the copilot, on their payment date
  1. open bills, paid on their due date (less anything already scheduled against them)
  2. open invoices, expected on due date + that customer's average payment delay
  3. future invoices and bills, following each counterparty's last-6-months pattern
  4. recurring fixed costs detected from history; a quarterly GST payment whose quarter has
     ended is instead output tax - input tax from that quarter's invoices and bills
With under 8 weeks of history only 0-2 are used (thin-data rule).
Read-only: never writes to the store.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.cashflow.recurring import RecurringItem, detect_recurring
from copilot.dates import add_months, clamp_day, months_window_start, week_start
from copilot.reconcile import estimate_payment_delays
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    Bill,
    CopilotModel,
    Counterparty,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    ForecastAssumption,
    Invoice,
    Money,
    PaymentStatus,
    TransactionCategory,
    UntrustedText,
    sgd,
)
from copilot.store import Store

WEEKS = 13
THIN_DATA_DAYS = 56  # 8 weeks
PATTERN_MONTHS = 6
LATE_RECEIPT_DAYS = 7  # invoice already later than expected: assume it arrives within a week
MIN_GAP_DAYS = 10  # don't project a new document within 10 days of the last real one
CENT = Decimal("0.01")

Source = Literal[
    "scheduled_payment",
    "open_bill",
    "open_invoice",
    "expected_invoice",
    "expected_bill",
    "recurring",
    "what_if",  # added by a what-if scenario (scenarios.py), never by the base forecast
]


class ForecastItem(CopilotModel):
    date: date
    amount: Money
    source: Source
    label: UntrustedText  # contains counterparty names and document numbers
    # What the item comes from, so what-if and recommendations can find it without parsing
    # labels: the bill/invoice/scheduled-payment id, or the recurring category.
    ref: str | None = None
    counterparty_id: str | None = None


class WeekForecast(CopilotModel):
    week: int
    start: date
    end: date
    inflows: Money
    outflows: Money
    end_balance: Money
    min_balance: Money


class LowPoint(CopilotModel):
    date: date
    balance: Money
    week: int


class Forecast(CopilotModel):
    as_of: date
    start_balance: Money
    weeks: list[WeekForecast]
    low_point: LowPoint
    items: list[ForecastItem]
    assumptions: list[str]
    # The owner's saved assumptions in effect (chunk 13), in plain English. Untrusted: they
    # name customers. Empty when none are saved or use_saved=False.
    saved_assumptions: list[UntrustedText] = []
    # Set by forecast_balance when assumptions are saved: the low point from imported data only.
    low_point_without_saved: LowPoint | None = None


def horizon_end(as_of: date) -> date:
    """Last day of the 13-week horizon (a Sunday)."""
    return week_start(as_of + timedelta(days=1)) + timedelta(days=7 * WEEKS - 1)


def balance_path(
    as_of: date, start_balance: Decimal, items: list[ForecastItem]
) -> list[tuple[date, Decimal]]:
    """End-of-day balance for every day from as_of + 1 to the horizon end, for any item list."""
    flows: dict[date, Decimal] = defaultdict(Decimal)
    for item in items:
        flows[item.date] += item.amount
    balance = start_balance
    days = []
    day, last = as_of + timedelta(days=1), horizon_end(as_of)
    while day <= last:
        balance += flows.get(day, Decimal("0"))
        days.append((day, balance))
        day += timedelta(days=1)
    return days


class Gap(CopilotModel):
    start: date
    end: date
    lowest_date: date
    lowest_balance: Money
    shortfall: Money  # target - lowest balance


def find_gaps(path: list[tuple[date, Decimal]], target: Decimal = Decimal("0")) -> list[Gap]:
    """Runs of consecutive days with the balance below target."""
    runs: list[list[tuple[date, Decimal]]] = []
    for day, balance in path:
        if balance < target:
            if runs and (day - runs[-1][-1][0]).days == 1:
                runs[-1].append((day, balance))
            else:
                runs.append([(day, balance)])
    gaps = []
    for run in runs:
        lowest_day, lowest = min(run, key=lambda db: db[1])
        gaps.append(
            Gap(
                start=run[0][0],
                end=run[-1][0],
                lowest_date=lowest_day,
                lowest_balance=lowest,
                shortfall=target - lowest,
            )
        )
    return gaps


def daily_balances(forecast: Forecast) -> list[tuple[date, Decimal]]:
    """End-of-day balance for every day in the horizon."""
    return balance_path(forecast.as_of, forecast.start_balance, forecast.items)


def gst_return(
    invoices: list[Invoice], bills: list[Bill], start: date, end: date
) -> Decimal | None:
    """Net GST for documents issued start..end: output tax - input tax. None if no GST."""
    live = [d for d in [*invoices, *bills] if start <= d.issue_date <= end]
    live = [d for d in live if d.status is not DocumentStatus.VOID]
    if not any(d.gst for d in live):
        return None
    output = sum((d.gst for d in live if isinstance(d, Invoice)), Decimal("0"))
    return output - sum((d.gst for d in live if isinstance(d, Bill)), Decimal("0"))


def measured_delays(store: Store, business_id: str) -> tuple[dict[str, int], list[str]]:
    """Each customer's average days paid after the due date, in whole days, and warnings."""
    result = estimate_payment_delays(store, business_id)
    return {cid: round(d.mean_delay_days) for cid, d in result.value.items()}, list(result.warnings)


def active_assumptions(
    store: Store,
    business_id: str,
    preview: tuple[Sequence[ForecastAssumption], Collection[str]] = ((), ()),
) -> list[ForecastAssumption]:
    """The owner's active saved assumptions, with a preview's additions and removals."""
    kept = [a for a in store.list_assumptions(business_id, "active") if a.id not in preview[1]]
    return kept + list(preview[0])


def receipt_date(due: date, delay_days: int, as_of: date) -> date:
    """When an open invoice is expected: due date + the customer's delay; if that has already
    passed, within LATE_RECEIPT_DAYS. Shared with the 3-year model (analysis/model.py)."""
    expected = due + timedelta(days=delay_days)
    return expected if expected > as_of else as_of + timedelta(days=LATE_RECEIPT_DAYS)


def bill_payment_date(due: date, as_of: date) -> date:
    """When an open bill is paid: its due date; an overdue bill the next day."""
    return max(due, as_of + timedelta(days=1))


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return ((ordered[mid - 1] + ordered[mid]) / 2).quantize(CENT)


def _pattern(docs: list[Invoice] | list[Bill], as_of: date) -> tuple[list[int], Decimal] | None:
    """Typical issue days and median amount over the last 6 months, or None if irregular."""
    start = months_window_start(as_of, PATTERN_MONTHS)
    recent = [d for d in docs if start <= d.issue_date <= as_of]
    per_month = round(len(recent) / PATTERN_MONTHS)
    if per_month == 0:
        return None
    days = sorted(d.issue_date.day for d in recent)
    size = len(days) / per_month
    typical = [
        sorted(days[round(i * size) : round((i + 1) * size)])[
            (round((i + 1) * size) - round(i * size)) // 2
        ]
        for i in range(per_month)
    ]
    return typical, _median([d.amount for d in recent])


def _projected_issues(days: list[int], last_issue: date, as_of: date, last_day: date) -> list[date]:
    issues = []
    for offset in range(0, 5):
        first = add_months(date(as_of.year, as_of.month, 1), offset)
        for day in days:
            issue = clamp_day(first.year, first.month, day)
            if issue > as_of and (issue - last_issue).days >= MIN_GAP_DAYS and issue <= last_day:
                issues.append(issue)
    return issues


def walk(
    as_of: date, start_balance: Decimal, items: list[ForecastItem]
) -> tuple[list[WeekForecast], LowPoint]:
    """Weekly totals and the low point from a start balance and dated items (13 weeks)."""
    first_day = as_of + timedelta(days=1)
    week1 = week_start(first_day)
    flows: dict[date, list[ForecastItem]] = defaultdict(list)
    for it in items:
        flows[it.date].append(it)
    balance = start_balance
    weeks: list[WeekForecast] = []
    low = LowPoint(date=as_of, balance=start_balance, week=0)
    for w in range(WEEKS):
        start = week1 + timedelta(days=7 * w)
        inflow = outflow = Decimal("0")
        week_min: Decimal | None = None
        for offset in range(7):
            day = start + timedelta(days=offset)
            if day < first_day:
                continue
            for it in flows.get(day, []):
                balance += it.amount
                if it.amount > 0:
                    inflow += it.amount
                else:
                    outflow -= it.amount
            week_min = balance if week_min is None else min(week_min, balance)
            if balance < low.balance:
                low = LowPoint(date=day, balance=balance, week=w + 1)
        weeks.append(
            WeekForecast(
                week=w + 1,
                start=start,
                end=start + timedelta(days=6),
                inflows=inflow,
                outflows=outflow,
                end_balance=balance,
                min_balance=week_min if week_min is not None else balance,
            )
        )
    return weeks, low


def forecast_13_weeks(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    as_of: date | None = None,
    use_saved: bool = True,
    preview: tuple[Sequence[ForecastAssumption], Collection[str]] = ((), ()),
) -> DomainResult[Forecast]:
    """use_saved: apply the owner's saved assumptions (chunk 13); False gives the forecast
    from the imported data alone, for comparison. preview: (assumptions to add, ids of saved
    ones to leave out), to show a save or a removal before it is confirmed."""
    as_of = as_of or sandbox.today(business_id)
    first_day = as_of + timedelta(days=1)
    last_day = horizon_end(as_of)

    counterparties: dict[str, Counterparty] = {
        c.id: c for c in store.list_counterparties(business_id)
    }
    history = store.list_transactions(business_id, end=as_of)
    thin = not history or (history[-1].date - history[0].date).days < THIN_DATA_DAYS
    delays, delay_warnings = measured_delays(store, business_id)
    saved = active_assumptions(store, business_id, preview) if use_saved else []
    cost_changes: dict[TransactionCategory, tuple[date, Decimal]] = {}
    saved_text: list[str] = []
    for a in saved:
        if a.kind == "payment_delay" and a.counterparty_id and a.days is not None:
            measured = delays.get(a.counterparty_id)
            delays[a.counterparty_id] = a.days
            was = f"measured {measured}" if measured is not None else "no history"
            who = counterparties.get(a.counterparty_id)
            saved_text.append(
                f"{who.name if who else a.counterparty_id} pays {a.days} days after the due "
                f"date ({was}) [saved assumption {a.id}]"
            )
        elif a.kind == "recurring_change" and a.category and a.amount is not None and a.start:
            cost_changes[a.category] = (a.start, a.amount)
            saved_text.append(
                f"{a.category.value} costs {sgd(a.amount)} a month from {a.start.isoformat()} "
                f"[saved assumption {a.id}]"
            )
    invoices = store.list_invoices(business_id)
    bills = store.list_bills(business_id)

    items: list[ForecastItem] = []
    warnings: list[str] = delay_warnings

    def add(
        when: date,
        amount: Decimal,
        source: Source,
        label: str,
        ref: str | None = None,
        counterparty_id: str | None = None,
    ) -> None:
        if first_day <= when <= last_day and amount != 0:
            items.append(
                ForecastItem(
                    date=when,
                    amount=amount,
                    source=source,
                    label=label,
                    ref=ref,
                    counterparty_id=counterparty_id,
                )
            )

    def name(cid: str) -> str:
        return counterparties[cid].name if cid in counterparties else cid

    # 0. Payments the owner scheduled through the copilot (not yet executed).
    scheduled = store.list_scheduled_payments(business_id, (PaymentStatus.SCHEDULED,))
    payees = {p.id: p.name for p in store.list_payees(business_id)}
    bill_numbers = {b.id: b.number for b in bills}
    scheduled_for_bill: dict[str, Decimal] = defaultdict(Decimal)
    for p in scheduled:
        if p.bill_id is not None:
            scheduled_for_bill[p.bill_id] += p.amount
        what = f" for bill {bill_numbers.get(p.bill_id, p.bill_id)}" if p.bill_id else ""
        add(
            max(p.pay_on, first_day),
            -p.amount,
            "scheduled_payment",
            f"Scheduled payment to {payees.get(p.payee_id, p.payee_id)}{what}",
            ref=p.id,
        )
    # 1. Open bills, less what is already scheduled against them.
    for b in bills:
        if b.status is DocumentStatus.OPEN:
            add(
                bill_payment_date(b.due_date, as_of),
                -max(b.amount - b.amount_paid - scheduled_for_bill[b.id], Decimal("0")),
                "open_bill",
                f"Bill {b.number} to {name(b.counterparty_id)} due {b.due_date.isoformat()}",
                ref=b.id,
                counterparty_id=b.counterparty_id,
            )
    # 2. Open invoices.
    for i in invoices:
        if i.status is DocumentStatus.OPEN:
            add(
                receipt_date(i.due_date, delays.get(i.counterparty_id, 0), as_of),
                i.amount - i.amount_paid,
                "open_invoice",
                f"Invoice {i.number} from {name(i.counterparty_id)} (due {i.due_date.isoformat()})",
                ref=i.id,
                counterparty_id=i.counterparty_id,
            )

    recurring: list[RecurringItem] = []
    if thin:
        warnings.append(
            "Less than 8 weeks of history: forecast uses only open invoices and bills, "
            "not patterns from history"
        )
    else:
        # 3. Future invoices and bills from each counterparty's recent pattern.
        for kind, docs_all, source in (
            ("invoice", invoices, "expected_invoice"),
            ("bill", bills, "expected_bill"),
        ):
            by_party: dict[str, list] = defaultdict(list)
            for d in docs_all:
                by_party[d.counterparty_id].append(d)
            for cid, docs in sorted(by_party.items()):
                pattern = _pattern(docs, as_of)
                if pattern is None:
                    continue
                days, amount = pattern
                terms = counterparties[cid].payment_terms_days if cid in counterparties else 30
                lag = terms + (delays.get(cid, 0) if kind == "invoice" else 0)
                last_issue = max(d.issue_date for d in docs)
                for issue in _projected_issues(days, last_issue, as_of, last_day):
                    add(
                        issue + timedelta(days=lag),
                        amount if kind == "invoice" else -amount,
                        source,  # type: ignore[arg-type]
                        f"Expected {kind} {'from' if kind == 'invoice' else 'to'} {name(cid)}, "
                        f"issued around {issue.isoformat()}",
                        counterparty_id=cid,
                    )
        # 4. Recurring fixed costs.
        recurring = detect_recurring(store, business_id, as_of)
        for r in recurring:
            step = 1 if r.cadence == "monthly" else 3
            when = r.next_date
            while when <= last_day:
                amount, label = r.amount, r.label
                if r.category is TransactionCategory.TAX and r.cadence == "quarterly":
                    # A GST return pays the quarter that ended the month before. Once that
                    # quarter is over, its invoices and bills give the exact amount.
                    quarter_end = when.replace(day=1) - timedelta(days=1)
                    quarter_start = add_months(quarter_end.replace(day=1), -2)
                    net = (
                        gst_return(invoices, bills, quarter_start, quarter_end)
                        if quarter_end <= as_of
                        else None
                    )
                    if net is not None:
                        amount = -net
                        label = (
                            f"GST return {quarter_start.isoformat()} to {quarter_end.isoformat()}"
                            " (output tax - input tax on invoices and bills)"
                        )
                change = cost_changes.get(r.category)
                if change is not None and when >= change[0]:
                    amount = -change[1]
                    label = f"{r.label} (saved assumption: {sgd(change[1])} a month)"
                add(when, amount, "recurring", label, ref=r.category.value)
                following = add_months(when, step)
                # Re-apply the usual day, so the 31st doesn't drift to the 28th after February.
                when = clamp_day(following.year, following.month, r.day)

    items.sort(key=lambda it: (it.date, it.source, it.label))
    start_balance = sum(sandbox.balances(business_id, as_of).values(), Decimal("0"))
    weeks, low = walk(as_of, start_balance, items)

    low_week_items = (
        [it for it in items if weeks[low.week - 1].start <= it.date <= weeks[low.week - 1].end]
        if low.week
        else []
    )
    drivers = [
        Driver(label=it.label, amount=it.amount, detail=f"{it.date.isoformat()} ({it.source})")
        for it in sorted(low_week_items, key=lambda it: abs(it.amount), reverse=True)[:5]
    ]

    assumptions = [
        f"Starts from total cash across all accounts on {as_of.isoformat()}.",
        "Open bills are paid on their due date (already-overdue bills: the next day).",
        "Customer payments arrive on the due date plus that customer's average delay, "
        "measured from past invoices.",
        f"Invoices already later than that are assumed to arrive within {LATE_RECEIPT_DAYS} days.",
    ]
    if not thin:
        assumptions += [
            f"Future invoices and bills follow each customer's and supplier's last "
            f"{PATTERN_MONTHS} months (typical issue days, median amount); the business pays "
            "suppliers on time.",
            "Recurring costs: " + "; ".join(f"{r.label}: {sgd(r.amount)}" for r in recurring) + ".",
        ]
    if any(it.label.startswith("GST return") for it in items):
        assumptions.append(
            "A GST payment for a quarter that has already ended is that quarter's output tax "
            "minus input tax from your invoices and bills (input tax on costs without a "
            "supplier bill is not counted)."
        )
    assumptions.append(
        "Not included: uncategorised one-off spending and any new customers or costs that "
        "don't follow past patterns."
    )
    if saved_text:
        assumptions.insert(
            0,
            f"{len(saved_text)} saved assumption(s) from the owner replace the measured figures "
            "(listed in saved_assumptions).",
        )

    return DomainResult[Forecast](
        value=Forecast(
            as_of=as_of,
            start_balance=start_balance,
            weeks=weeks,
            low_point=low,
            items=items,
            assumptions=assumptions,
            saved_assumptions=saved_text,
        ),
        drivers=drivers,
        data_coverage=DataCoverage(
            period_start=history[0].date if history else as_of,
            period_end=as_of,
            record_count=len(history),
        ),
        warnings=warnings,
    )
