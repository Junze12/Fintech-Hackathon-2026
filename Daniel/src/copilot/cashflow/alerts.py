"""Cash alerts (v1): threshold, shortfall and overdue receivables, ranked by importance.

- threshold: forecast cash falls below the floor (default: one month of fixed costs).
- shortfall: a stretch where cash goes below zero, naming the biggest payment it can't cover.
- overdue receivable: an open invoice past its due date, compared with that customer's usual
  delay (info if it is normal for them, warning if later than usual).
Ranking (agreed 2026-10-04): severity first (critical, warning, info), then score = SGD at
stake x urgency (1 within a week, then 7/days), so an info note never outranks a critical one.
Pure functions over the store and a forecast: no writes, no LLM.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from copilot.cashflow.forecast import Forecast, daily_balances
from copilot.cashflow.recurring import detect_recurring
from copilot.reconcile import estimate_payment_delays
from copilot.schemas import (
    CopilotModel,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    Money,
    UntrustedText,
    sgd,
)
from copilot.store import Store

CENT = Decimal("0.01")


def default_floor(store: Store, business_id: str, as_of: date) -> DomainResult[Decimal]:
    """Default cash floor: one month of recurring fixed costs (quarterly costs count 1/3)."""
    items = detect_recurring(store, business_id, as_of)
    monthly = [(-r.amount if r.cadence == "monthly" else -r.amount / 3, r) for r in items]
    floor = sum((m for m, _ in monthly), Decimal("0")).quantize(CENT)
    warnings = [] if items else ["No recurring costs found; floor set to 0"]
    txns = store.list_transactions(business_id, end=as_of)
    return DomainResult[Decimal](
        value=floor,
        drivers=[Driver(label=r.label, amount=-m.quantize(CENT)) for m, r in monthly],
        data_coverage=DataCoverage(
            period_start=txns[0].date if txns else as_of, period_end=as_of, record_count=len(txns)
        ),
        warnings=warnings,
    )


class Alert(CopilotModel):
    kind: Literal["threshold"] = "threshold"
    severity: Literal["warning", "critical"]
    floor: Money
    first_breach_date: date
    first_breach_week: int
    lowest_balance: Money
    lowest_date: date
    gap_below_floor: Money  # how far the lowest point is below the floor
    message: str


def threshold_alert(forecast: DomainResult[Forecast], floor: Decimal) -> DomainResult[Alert | None]:
    """Warn if the forecast balance falls below the floor at any point in the 13 weeks."""
    fc = forecast.value
    breach = next(((d, b) for d, b in daily_balances(fc) if b < floor), None)
    alert = None
    if breach is not None:
        breach_week = next(w.week for w in fc.weeks if w.start <= breach[0] <= w.end)
        low = fc.low_point
        severity = "critical" if low.balance < 0 else "warning"
        alert = Alert(
            severity=severity,
            floor=floor,
            first_breach_date=breach[0],
            first_breach_week=breach_week,
            lowest_balance=low.balance,
            lowest_date=low.date,
            gap_below_floor=floor - low.balance,
            message=(
                f"Cash is forecast to fall below your floor of {sgd(floor)} from "
                f"{breach[0].isoformat()} (week {breach_week}), reaching {sgd(low.balance)} "
                f"on {low.date.isoformat()}"
                + (" - the account would be overdrawn." if severity == "critical" else ".")
            ),
        )
    drivers: list[Driver] = []
    if alert is not None:
        # Explain the breach where it starts, not the forecast's overall low point:
        # the user's "why?" is about what first pushes cash under the floor.
        week = fc.weeks[alert.first_breach_week - 1]
        in_week = [it for it in fc.items if week.start <= it.date <= week.end]
        drivers = [
            Driver(label=it.label, amount=it.amount, detail=f"{it.date.isoformat()} ({it.source})")
            for it in sorted(in_week, key=lambda it: abs(it.amount), reverse=True)[:5]
        ]
    return DomainResult[Alert | None](
        value=alert,
        drivers=drivers,
        data_coverage=forecast.data_coverage,
        warnings=forecast.warnings,
    )


# --- v1 alerts, ranked (chunk 4b-1) ----------------------------------------------

Severity = Literal["critical", "warning", "info"]
AlertKind = Literal["threshold", "shortfall", "overdue_receivable"]

URGENT_DAYS = 7  # anything within a week (or already overdue) counts as fully urgent
OVERDUE_GRACE_DAYS = 7  # overdue but within the customer's usual delay + a week: info only
_SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}
# Money the business must pay out: a shortfall alert names one of these.
_OBLIGATIONS = {"scheduled_payment", "open_bill", "expected_bill", "recurring"}


class CashAlert(CopilotModel):
    key: UntrustedText  # stable identity, used to spot new alerts after the clock moves
    kind: AlertKind
    severity: Severity
    title: UntrustedText
    message: UntrustedText
    impact: Money  # SGD at stake
    event_date: date
    days_away: int  # 0 if it is already happening (e.g. overdue)
    score: Money  # impact x urgency; ranks alerts within the same severity
    drivers: list[Driver] = []


def urgency(days_away: int) -> Decimal:
    """1 within a week, then falling off: 0.5 at two weeks, 0.25 at four."""
    return Decimal("1") if days_away <= URGENT_DAYS else Decimal(URGENT_DAYS) / days_away


def _alert(
    *,
    key: str,
    kind: AlertKind,
    severity: Severity,
    title: str,
    message: str,
    impact: Decimal,
    event_date: date,
    today: date,
    drivers: list[Driver] | None = None,
) -> CashAlert:
    days_away = max(0, (event_date - today).days)
    score = (impact * urgency(days_away)).quantize(CENT)
    return CashAlert(
        key=key,
        kind=kind,
        severity=severity,
        title=title,
        message=message,
        impact=impact,
        event_date=event_date,
        days_away=days_away,
        score=score,
        drivers=drivers or [],
    )


def _from_threshold(alert: Alert, drivers: list[Driver], today: date) -> CashAlert:
    return _alert(
        key="threshold",
        kind="threshold",
        severity=alert.severity,
        title=f"Cash below your floor of {sgd(alert.floor)}",
        message=alert.message,
        impact=alert.gap_below_floor,
        event_date=alert.first_breach_date,
        today=today,
        drivers=drivers,
    )


def shortfall_alerts(forecast: Forecast) -> list[CashAlert]:
    """One alert per stretch of days the forecast is below zero, naming the biggest payment
    due in that stretch: the obligation the business can't cover without action."""
    days = daily_balances(forecast)
    runs: list[list[tuple[date, Decimal]]] = []
    for day, balance in days:
        if balance < 0:
            if runs and (day - runs[-1][-1][0]).days == 1:
                runs[-1].append((day, balance))
            else:
                runs.append([(day, balance)])
    alerts = []
    for run in runs:
        start, end = run[0][0], run[-1][0]
        lowest_day, lowest = min(run, key=lambda db: db[1])
        due = [
            it
            for it in forecast.items
            if it.source in _OBLIGATIONS and it.amount < 0 and start <= it.date <= end
        ]
        if not due:
            continue
        biggest = max(due, key=lambda it: -it.amount)
        short_by = -lowest
        alerts.append(
            _alert(
                key=f"shortfall:{biggest.label}",
                kind="shortfall",
                severity="critical",
                title=f"Can't cover {biggest.label}",
                message=(
                    f"Not enough cash for {biggest.label} ({sgd(-biggest.amount)}). The forecast "
                    f"balance goes below zero on {start.isoformat()} and bottoms out at "
                    f"{sgd(lowest)} on {lowest_day.isoformat()}."
                ),
                impact=short_by,
                event_date=start,
                today=forecast.as_of,
                drivers=[
                    Driver(label=it.label, amount=it.amount, detail=f"{it.date} ({it.source})")
                    for it in sorted(due, key=lambda it: it.amount)[:5]
                ],
            )
        )
    return alerts


def overdue_alerts(store: Store, business_id: str, today: date) -> list[CashAlert]:
    """One alert per open invoice past its due date, compared with the customer's usual delay."""
    delays = estimate_payment_delays(store, business_id).value
    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    alerts = []
    for inv in store.list_invoices(business_id, DocumentStatus.OPEN):
        days_overdue = (today - inv.due_date).days
        if days_overdue <= 0:
            continue
        customer = names.get(inv.counterparty_id, inv.counterparty_id)
        outstanding = inv.amount - inv.amount_paid
        usual = (
            round(delays[inv.counterparty_id].mean_delay_days)
            if inv.counterparty_id in delays
            else None
        )
        if usual is None:
            pattern, severity = "There is no payment history for this customer.", "warning"
        elif days_overdue <= max(usual, 0) + OVERDUE_GRACE_DAYS:
            pattern = (
                f"{customer} usually pays about {usual} days late, so this is normal for them."
            )
            severity = "info"
        else:
            pattern = (
                f"{customer} usually pays about {usual} days late, so this is later than usual."
            )
            severity = "warning"
        alerts.append(
            _alert(
                key=f"overdue:{inv.id}",
                kind="overdue_receivable",
                severity=severity,  # type: ignore[arg-type]
                title=f"Invoice {inv.number} is {days_overdue} days overdue",
                message=(
                    f"Invoice {inv.number} to {customer}: {sgd(outstanding)} was due on "
                    f"{inv.due_date.isoformat()} and is {days_overdue} days overdue. {pattern}"
                ),
                impact=outstanding,
                event_date=inv.due_date,
                today=today,
            )
        )
    return alerts


def evaluate_alerts(
    store: Store,
    business_id: str,
    forecast: DomainResult[Forecast],
    floor: Decimal,
) -> DomainResult[list[CashAlert]]:
    """All v1 alerts, most important first: by severity, then by score (impact x urgency)."""
    today = forecast.value.as_of
    threshold = threshold_alert(forecast, floor)
    alerts: list[CashAlert] = []
    if threshold.value is not None:
        alerts.append(_from_threshold(threshold.value, threshold.drivers, today))
    alerts += shortfall_alerts(forecast.value)
    alerts += overdue_alerts(store, business_id, today)
    alerts.sort(key=lambda a: (-_SEVERITY_RANK[a.severity], -a.score, a.event_date, a.key))
    return DomainResult[list[CashAlert]](
        value=alerts,
        drivers=alerts[0].drivers if alerts else [],
        data_coverage=forecast.data_coverage,
        warnings=forecast.warnings,
    )


def new_alerts(before: list[CashAlert], after: list[CashAlert]) -> list[CashAlert]:
    """Alerts in `after` that weren't in `before`, or that became more severe."""
    previous = {a.key: a.severity for a in before}
    return [
        a
        for a in after
        if a.key not in previous or _SEVERITY_RANK[a.severity] > _SEVERITY_RANK[previous[a.key]]
    ]
