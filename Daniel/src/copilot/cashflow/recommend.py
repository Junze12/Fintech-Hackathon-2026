"""Ways to close a forecast cash gap, in CLAUDE.md's order of preference, and the funding need.

1. Find the gaps: stretches of days the forecast balance is below the target (S$0 + buffer).
2. Build candidate options, each a what-if change (scenarios.py), in this order:
     collect     open invoices expected after a gap starts, if paid on time
     reschedule  open supplier bills due in or just before a gap, paid DEFER_DAYS later
     cut         discretionary recurring costs paused until the last gap is over
   Each option is scored on its own against the base case.
3. Plan: apply the options in that order, keeping one only if it reduces the shortfall
   (S$ x days below target), and stop as soon as no gap is left.
4. Whatever gap remains is the funding need (amount, draw date, repay date, duration) that
   financing (chunk 4c) matches products against. If nothing remains, borrowing is not needed.
Pure functions over the store and a forecast: no writes, no LLM.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from copilot.cashflow.forecast import (
    Forecast,
    ForecastItem,
    Gap,
    balance_path,
    find_gaps,
    horizon_end,
)
from copilot.cashflow.scenarios import (
    Change,
    CollectOnTime,
    DelayPayment,
    PauseRecurring,
    apply_changes,
)
from copilot.schemas import (
    UNTRUSTED,
    CopilotModel,
    DocumentStatus,
    DomainResult,
    Driver,
    Money,
    PaymentStatus,
    UntrustedText,
    sgd,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

DEFER_DAYS = 14  # how long we suggest asking a supplier to wait
NEAR_GAP_DAYS = 7  # a bill due up to a week before a gap still helps if moved
DISCRETIONARY = {Cat.MARKETING, Cat.PROFESSIONAL_FEES, Cat.OWNER_DRAW}
FUNDING_PURPOSE = "working capital: forecast cash gap"

OptionKind = Literal["collect", "reschedule", "cut"]
Path = list[tuple[date, Decimal]]
# Built by code but quotes counterparty names and document numbers, so it is wrapped for the LLM.
Message = Annotated[str, UNTRUSTED]


class Effect(CopilotModel):
    low_before: Money
    low_after: Money
    gaps_before: int
    gaps_after: int
    days_below_before: int
    days_below_after: int
    closes: list[date]  # start dates of base-case gaps this removes completely


class Option(CopilotModel):
    rank: int  # 1 = most preferred
    kind: OptionKind
    title: UntrustedText
    changes: list[Change]
    amount: Money  # money moved (+ earlier in, or - spending moved/cut)
    effect: Effect  # this option on its own, against the base case
    assumption: str
    follow_up_tool: str | None = None  # a tool that starts the action, if we have one
    in_plan: bool = False


class FundingNeed(CopilotModel):
    """What chunk 4c matches financing products against."""

    amount: Money  # enough to keep cash at or above the target throughout
    target: Money
    draw_date: date  # first day cash would fall below the target
    repay_date: date | None  # first day after which cash stays above target without the loan
    duration_days: int
    duration_months: int  # rounded up, for matching loan terms
    duration_is_lower_bound: bool  # True: cash hasn't recovered by the end of the forecast
    purpose: str
    basis: Literal["after non-borrowing plan", "no action", "stated by the user"]


class Recommendations(CopilotModel):
    target: Money
    gaps: list[Gap]  # base case
    options: list[Option]
    plan_effect: Effect
    gaps_after_plan: list[Gap]
    borrowing_needed: bool
    funding_need: FundingNeed | None
    need_without_actions: FundingNeed | None
    message: Message


def shortfall_area(path: Path, target: Decimal) -> Decimal:
    """S$ x days below target: the measure an option must reduce to join the plan."""
    return sum((target - b for _, b in path if b < target), Decimal("0"))


def _effect(before: Path, after: Path, target: Decimal) -> Effect:
    below_after = {d for d, b in after if b < target}
    closes = [
        g.start
        for g in find_gaps(before, target)
        if not any(g.start <= d <= g.end for d in below_after)
    ]
    return Effect(
        low_before=min(b for _, b in before),
        low_after=min(b for _, b in after),
        gaps_before=len(find_gaps(before, target)),
        gaps_after=len(find_gaps(after, target)),
        days_below_before=sum(1 for _, b in before if b < target),
        days_below_after=len(below_after),
        closes=closes,
    )


def funding_need(
    as_of: date, path: Path, target: Decimal, basis: str = "after non-borrowing plan"
) -> FundingNeed | None:
    """How much to borrow, from when and until when, to keep cash at or above target.

    A loan of `amount` drawn on the first day below target lifts every later day by `amount`,
    so the lowest day lands exactly on the target. It can be repaid once the balance without
    it stays at or above target for the rest of the forecast. Interest and fees are left to
    financing (4c), which prices each product for this amount and duration.
    """
    gaps = find_gaps(path, target)
    if not gaps:
        return None
    amount = max(g.shortfall for g in gaps)
    draw = gaps[0].start
    last = horizon_end(as_of)
    recovered = gaps[-1].end < last
    repay = gaps[-1].end + timedelta(days=1) if recovered else None
    days = ((repay or last) - draw).days + (0 if recovered else 1)
    return FundingNeed(
        amount=amount,
        target=target,
        draw_date=draw,
        repay_date=repay,
        duration_days=days,
        duration_months=max(1, math.ceil(days / 30)),
        duration_is_lower_bound=not recovered,
        purpose=FUNDING_PURPOSE,
        basis=basis,  # type: ignore[arg-type]
    )


def _candidates(
    store: Store, business_id: str, fc: Forecast, gaps: list[Gap]
) -> list[tuple[OptionKind, str, list[Change], Decimal, str, str | None]]:
    """(kind, title, changes, amount, assumption, follow-up tool) in order of preference."""
    out: list[tuple[OptionKind, str, list[Change], Decimal, str, str | None]] = []
    invoices = {i.id: i for i in store.list_invoices(business_id, DocumentStatus.OPEN)}
    bills = {b.id: b for b in store.list_bills(business_id, DocumentStatus.OPEN)}
    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    first_paid = fc.as_of + timedelta(days=7)

    # 1. Collect: an invoice expected after a gap starts that would arrive before it ends.
    for it in fc.items:
        inv = invoices.get(it.ref or "") if it.source == "open_invoice" else None
        if inv is None:
            continue
        on_time = max(inv.due_date, first_paid)
        if on_time < it.date and any(on_time <= g.end and it.date > g.start for g in gaps):
            out.append(
                (
                    "collect",
                    f"Chase invoice {inv.number} ({names.get(inv.counterparty_id, '')}, "
                    f"{sgd(it.amount)}) so it is paid by {on_time.isoformat()} instead of "
                    f"{it.date.isoformat()}",
                    [CollectOnTime(invoice_id=inv.id)],
                    it.amount,
                    "Assumes the customer pays by the due date once reminded; "
                    "they have usually paid later.",
                    "draft_reminder",
                )
            )
    # 2. Reschedule: an open bill (not already scheduled) due in or just before a gap.
    scheduled = {
        p.bill_id
        for p in store.list_scheduled_payments(business_id, (PaymentStatus.SCHEDULED,))
        if p.bill_id
    }
    for it in fc.items:
        bill = bills.get(it.ref or "") if it.source == "open_bill" else None
        if bill is None or bill.id in scheduled:
            continue
        if any(g.start - timedelta(days=NEAR_GAP_DAYS) <= it.date <= g.end for g in gaps):
            out.append(
                (
                    "reschedule",
                    f"Ask {names.get(bill.counterparty_id, 'the supplier')} to accept payment of "
                    f"bill {bill.number} ({sgd(-it.amount)}) {DEFER_DAYS} days later, on "
                    f"{(it.date + timedelta(days=DEFER_DAYS)).isoformat()}",
                    [DelayPayment(bill_id=bill.id, days=DEFER_DAYS)],
                    it.amount,
                    "Needs the supplier's agreement; a late payment may cost a fee or an "
                    "early-payment discount.",
                    None,
                )
            )
    # 3. Cut: pause discretionary recurring costs until the last gap is over.
    last_gap_end = gaps[-1].end
    by_category: dict[str, list[ForecastItem]] = {}
    for it in fc.items:
        if it.source == "recurring" and it.ref in DISCRETIONARY and it.date <= last_gap_end:
            by_category.setdefault(it.ref, []).append(it)
    for category, its in sorted(by_category.items()):
        saved = sum((-i.amount for i in its), Decimal("0"))
        out.append(
            (
                "cut",
                f"Pause {category.replace('_', ' ')} spending until {last_gap_end.isoformat()} "
                f"({len(its)} payments, {sgd(saved)})",
                [PauseRecurring(category=Cat(category), until=last_gap_end)],
                -saved,
                "Assumes this spending can stop for a few weeks without hurting sales.",
                None,
            )
        )
    return out


def _message(rec: Recommendations) -> str:
    target = "zero" if rec.target == 0 else sgd(rec.target)
    if not rec.gaps:
        return (
            f"Cash stays above {target} for the whole 13-week forecast. No action is needed, "
            "and borrowing is not needed."
        )
    kept = [o for o in rec.options if o.in_plan]
    if not rec.borrowing_needed:
        return (
            f"{len(kept)} step(s) without borrowing close every gap below {target}: "
            + "; ".join(o.title for o in kept)
            + ". Borrowing is not needed if these work out."
        )
    need = rec.funding_need
    assert need is not None
    length = f"{'at least ' if need.duration_is_lower_bound else ''}{need.duration_days} days"
    lead = (
        f"The steps without borrowing ({'; '.join(o.title for o in kept)}) close "
        f"{len(rec.gaps) - len(rec.gaps_after_plan)} of {len(rec.gaps)} gap(s), but not all. "
        if kept
        else "No step without borrowing closes the gap. "
    )
    return (
        lead + f"The rest needs about {sgd(need.amount)} from {need.draw_date.isoformat()} for "
        f"{length}"
        + (
            " (cash hasn't recovered by the end of the forecast)."
            if need.duration_is_lower_bound
            else f", repayable from {need.repay_date.isoformat()}."  # type: ignore[union-attr]
        )
    )


def recommend_actions(
    store: Store,
    business_id: str,
    forecast: DomainResult[Forecast],
    buffer: Decimal = Decimal("0"),
) -> DomainResult[Recommendations]:
    fc = forecast.value
    target = buffer
    base_path = balance_path(fc.as_of, fc.start_balance, fc.items)
    gaps = find_gaps(base_path, target)

    options: list[Option] = []
    plan: list[Change] = []
    plan_path = base_path
    if gaps:
        for rank, (kind, title, changes, amount, assumption, tool) in enumerate(
            _candidates(store, business_id, fc, gaps), start=1
        ):
            alone, _, _ = apply_changes(store, business_id, fc, changes)
            alone_path = balance_path(fc.as_of, fc.start_balance, alone)
            in_plan = False
            if find_gaps(plan_path, target):
                trial, _, _ = apply_changes(store, business_id, fc, plan + changes)
                trial_path = balance_path(fc.as_of, fc.start_balance, trial)
                if shortfall_area(trial_path, target) < shortfall_area(plan_path, target):
                    plan, plan_path, in_plan = plan + changes, trial_path, True
            options.append(
                Option(
                    rank=rank,
                    kind=kind,
                    title=title,
                    changes=changes,
                    amount=amount,
                    effect=_effect(base_path, alone_path, target),
                    assumption=assumption,
                    follow_up_tool=tool,
                    in_plan=in_plan,
                )
            )

    after = find_gaps(plan_path, target)
    rec = Recommendations(
        target=target,
        gaps=gaps,
        options=options,
        plan_effect=_effect(base_path, plan_path, target),
        gaps_after_plan=after,
        borrowing_needed=bool(after),
        funding_need=funding_need(fc.as_of, plan_path, target),
        need_without_actions=funding_need(fc.as_of, base_path, target, "no action"),
        message="",
    )
    rec = rec.model_copy(update={"message": _message(rec)})

    warnings = list(forecast.warnings)
    if rec.funding_need is not None and rec.funding_need.duration_is_lower_bound:
        warnings.append(
            f"Cash is still below {sgd(target)} at the end of the forecast "
            f"({horizon_end(fc.as_of).isoformat()}), so the borrowing period is a minimum."
        )
    return DomainResult[Recommendations](
        value=rec,
        drivers=[
            Driver(
                label=f"Gap from {g.start.isoformat()} to {g.end.isoformat()}",
                amount=g.lowest_balance,
            )
            for g in gaps[:5]
        ],
        data_coverage=forecast.data_coverage,
        warnings=warnings,
    )
