"""Compare two periods: how each metric changed, and which categories moved most and why.

The current period is [start, end]; the comparison period defaults to the one just before it of
the same length (dates.previous_period). Changes are always current minus previous.
Revenue, costs and margins are cash basis; DSO / DPO / CCC are invoice basis (metrics.py).
Read-only.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from copilot.analysis.metrics import RATIO, period_metrics, working_capital
from copilot.dates import previous_period
from copilot.schemas import (
    CategoryGroup,
    CopilotModel,
    DataCoverage,
    DomainResult,
    Driver,
    Money,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

TOP_MOVERS = 5
CAUSES_PER_MOVER = 3


class Period(CopilotModel):
    start: date
    end: date


def resolve_periods(
    start: date, end: date, compare_start: date | None, compare_end: date | None
) -> tuple[Period, Period]:
    if end < start:
        raise ValueError("end must not be before start")
    if (compare_start is None) != (compare_end is None):
        raise ValueError("give both compare_start and compare_end, or neither")
    if compare_start is None or compare_end is None:
        compare_start, compare_end = previous_period(start, end)
    if compare_end < compare_start:
        raise ValueError("compare_end must not be before compare_start")
    return Period(start=start, end=end), Period(start=compare_start, end=compare_end)


def _whole_months(p: Period) -> int | None:
    following = p.end + timedelta(days=1)
    if p.start.day != 1 or following.day != 1:
        return None
    return (following.year - p.start.year) * 12 + following.month - p.start.month


def unequal_warning(current: Period, previous: Period) -> list[str]:
    """Warn when totals aren't like-for-like. Aug vs Sep (whole months) counts as equal."""
    months = _whole_months(current)
    if months is not None and months == _whole_months(previous):
        return []
    if (current.end - current.start) == (previous.end - previous.start):
        return []
    return ["The two periods have different lengths, so totals aren't like-for-like"]


def pct_change(before: Decimal, after: Decimal) -> Decimal | None:
    """Relative change as a fraction (0.25 = +25%). None when there is no base to compare to,
    or when the sign flips (e.g. net cash flow +S$3.9k -> -S$74.6k), where a % misleads."""
    if before == 0 or before * after < 0:
        return None
    return ((after - before) / abs(before)).quantize(RATIO)


# --- Metric comparison ---------------------------------------------------------------------


class MetricChange(CopilotModel):
    name: str
    basis: Literal["cash", "invoice"]
    unit: Literal["sgd", "ratio", "days"]
    previous: Decimal | None
    current: Decimal | None
    change: Decimal | None  # current - previous; for ratios a fraction (0.02 = 2 points)
    pct_change: Decimal | None  # only for S$ metrics


class Comparison(CopilotModel):
    current: Period
    previous: Period
    metrics: list[MetricChange]


def _change(
    name: str,
    basis: Literal["cash", "invoice"],
    unit: Literal["sgd", "ratio", "days"],
    previous: Decimal | None,
    current: Decimal | None,
) -> MetricChange:
    both = previous is not None and current is not None
    return MetricChange(
        name=name,
        basis=basis,
        unit=unit,
        previous=previous,
        current=current,
        change=current - previous if both else None,
        pct_change=pct_change(previous, current) if both and unit == "sgd" else None,
    )


def compare_periods(
    store: Store,
    business_id: str,
    start: date,
    end: date,
    compare_start: date | None = None,
    compare_end: date | None = None,
) -> DomainResult[Comparison]:
    current, previous = resolve_periods(start, end, compare_start, compare_end)
    results = {
        p: (
            period_metrics(store, business_id, p.start, p.end),
            working_capital(store, business_id, p.start, p.end),
        )
        for p in (previous, current)
    }
    (pm0, wc0), (pm1, wc1) = results[previous], results[current]
    m0, m1, w0, w1 = pm0.value, pm1.value, wc0.value, wc1.value
    metrics = [
        _change("revenue", "cash", "sgd", m0.revenue, m1.revenue),
        _change("cost of goods sold", "cash", "sgd", m0.cogs, m1.cogs),
        _change("operating expenses", "cash", "sgd", m0.opex, m1.opex),
        _change("gross margin", "cash", "ratio", m0.gross_margin, m1.gross_margin),
        _change("operating margin", "cash", "ratio", m0.operating_margin, m1.operating_margin),
        _change("net cash flow", "cash", "sgd", m0.net_cash_flow, m1.net_cash_flow),
        _change("DSO", "invoice", "days", w0.dso, w1.dso),
        _change("DPO", "invoice", "days", w0.dpo, w1.dpo),
        _change("cash conversion cycle", "invoice", "days", w0.ccc, w1.ccc),
    ]

    warnings = []
    for label, result in (("previous", pm0), ("current", pm1), ("previous", wc0), ("current", wc1)):
        for w in result.warnings:
            line = w if w.startswith(("Cash basis", "Invoice basis", "DIO")) else f"{label}: {w}"
            if line not in warnings:
                warnings.append(line)
    warnings.extend(unequal_warning(current, previous))

    revenue = metrics[0]
    net = metrics[5]
    return DomainResult[Comparison](
        value=Comparison(current=current, previous=previous, metrics=metrics),
        drivers=[
            Driver(label="Change in revenue", amount=revenue.change),
            Driver(label="Change in net cash flow", amount=net.change),
        ],
        data_coverage=DataCoverage(
            period_start=min(previous.start, current.start),
            period_end=max(previous.end, current.end),
            record_count=pm0.data_coverage.record_count + pm1.data_coverage.record_count,
        ),
        warnings=warnings,
    )


# --- Top movers ------------------------------------------------------------------------------


Effect = Literal["more money in", "less money in", "more spending", "less spending"]


class MoverCause(CopilotModel):
    counterparty_id: str | None
    label: UntrustedText  # counterparty name (external text) or a fixed phrase
    previous: Money  # signed: + money in, - money out
    current: Money
    change: Money
    previous_count: int
    current_count: int
    note: str  # e.g. "only in the previous period", "3 payments vs 1"


class Mover(CopilotModel):
    category: Cat
    group: CategoryGroup
    previous: Money  # signed
    current: Money
    change: Money  # current - previous (signed)
    pct_change: Decimal | None
    effect: Effect
    note: str
    causes: list[MoverCause]


class TopMovers(CopilotModel):
    current: Period
    previous: Period
    basis: Literal["cash"] = "cash"
    movers: list[Mover]  # largest absolute change first


def _note(previous_count: int, current_count: int, inflow: bool) -> str:
    def noun(n: int) -> str:
        word = "receipt" if inflow else "payment"
        return f"{n} {word}" if n == 1 else f"{n} {word}s"

    if previous_count == 0:
        return "only in the current period"
    if current_count == 0:
        return "only in the previous period"
    if previous_count != current_count:
        return f"{noun(current_count)} vs {previous_count}"
    return f"{noun(current_count)} in each period; amounts changed"


def _effect(change: Decimal, inflow: bool) -> Effect:
    if inflow:
        return "more money in" if change > 0 else "less money in"
    return "less spending" if change > 0 else "more spending"


def top_movers(
    store: Store,
    business_id: str,
    start: date,
    end: date,
    compare_start: date | None = None,
    compare_end: date | None = None,
    limit: int = TOP_MOVERS,
) -> DomainResult[TopMovers]:
    """Categories whose cash flow changed most, each explained by the counterparties behind it."""
    current, previous = resolve_periods(start, end, compare_start, compare_end)
    names = {c.id: c.name for c in store.list_counterparties(business_id)}

    # [category][counterparty or None] -> [prev amount, cur amount, prev count, cur count]
    cells: dict[Cat, dict[str | None, list]] = defaultdict(
        lambda: defaultdict(lambda: [Decimal("0"), Decimal("0"), 0, 0])
    )
    record_count = 0
    for index, period in enumerate((previous, current)):
        for t in store.list_transactions(business_id, start=period.start, end=period.end):
            if t.category is Cat.TRANSFER:
                continue
            record_count += 1
            cell = cells[t.category][t.counterparty_id]
            cell[index] += t.amount
            cell[index + 2] += 1

    movers = []
    for category, parties in cells.items():
        prev = sum((c[0] for c in parties.values()), Decimal("0"))
        cur = sum((c[1] for c in parties.values()), Decimal("0"))
        change = cur - prev
        if change == 0:
            continue
        inflow = prev + cur > 0
        causes = []
        for cid, (p_amt, c_amt, p_n, c_n) in parties.items():
            if c_amt == p_amt:
                continue
            label = names.get(cid, cid) if cid is not None else "No named counterparty"
            causes.append(
                MoverCause(
                    counterparty_id=cid,
                    label=label,
                    previous=p_amt,
                    current=c_amt,
                    change=c_amt - p_amt,
                    previous_count=p_n,
                    current_count=c_n,
                    note=_note(p_n, c_n, inflow),
                )
            )
        # Biggest contributors in the direction of the overall change first.
        causes.sort(key=lambda c: (-(c.change * (1 if change > 0 else -1)), str(c.label)))
        movers.append(
            Mover(
                category=category,
                group=category.group,
                previous=prev,
                current=cur,
                change=change,
                pct_change=pct_change(prev, cur),
                effect=_effect(change, inflow),
                note=_note(
                    sum(c[2] for c in parties.values()),
                    sum(c[3] for c in parties.values()),
                    inflow,
                ),
                causes=causes[:CAUSES_PER_MOVER],
            )
        )
    movers.sort(key=lambda m: (-abs(m.change), m.category.value))
    movers = movers[:limit]

    warnings = ["Cash basis: changes in money actually received and paid, not invoiced"]
    if not movers:
        warnings.append("Nothing changed between the two periods")
    if any(m.category is Cat.UNCATEGORISED for m in movers):
        warnings.append("Some of the change is in uncategorised transactions")
    warnings.extend(unequal_warning(current, previous))

    return DomainResult[TopMovers](
        value=TopMovers(current=current, previous=previous, movers=movers),
        drivers=[
            Driver(
                label=m.category.value.replace("_", " "),
                amount=m.change,
                detail=f"{m.effect}: {sgd(m.previous)} -> {sgd(m.current)}",
            )
            for m in movers
        ],
        data_coverage=DataCoverage(
            period_start=min(previous.start, current.start),
            period_end=max(previous.end, current.end),
            record_count=record_count,
        ),
        warnings=warnings,
    )
