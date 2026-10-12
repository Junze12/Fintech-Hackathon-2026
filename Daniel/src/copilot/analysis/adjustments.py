"""Recorded adjustments (chunk 13): the rules shared by the tools and the policy guards.

An adjustment never overwrites imported data and never touches cash; statements.py lays the
applied ones over the books. This module says which months are still open, which lines and
payments may be adjusted, and what an adjustment would do to a month's net profit before it is
applied (so the confirmation restates the exact effect). Pure and read-only.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from copilot.analysis.statements import (
    CASH_OPEX,
    MonthStatements,
    month_start,
    monthly_statements,
)
from copilot.reconcile import match_settlements
from copilot.schemas import Adjustment, CopilotModel, Id, Money, UntrustedText
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

OPEN_MONTHS = 3  # the last 3 complete months can be adjusted; older months are closed
MAX_ADJUSTMENT = Decimal("250000.00")
MAX_APPLIED = 20
MAX_DRAFTS = 20

# Lines an accrued cost can go to (cash operating costs; payroll has its own runs).
ACCRUAL_LINES = (
    Cat.RENT,
    Cat.UTILITIES,
    Cat.SOFTWARE,
    Cat.MARKETING,
    Cat.PROFESSIONAL_FEES,
    Cat.OTHER,
)
# A payment can be relabelled from an operating-cost category or uncategorised...
RELABEL_FROM = frozenset(CASH_OPEX)
# ...to another operating-cost line, or to owner drawings (money the owner took, not a cost).
RELABEL_TO = (*ACCRUAL_LINES, Cat.OWNER_DRAW)


def open_months(store: Store, business_id: str, today: date) -> tuple[list[str], str | None]:
    """The months that can still be adjusted (oldest first), or the reason there are none."""
    months, _, reason = monthly_statements(store, business_id, today, "as_imported")
    if reason is not None:
        return [], reason
    return [m.month for m in months[-OPEN_MONTHS:]], None


class RelabelCandidate(CopilotModel):
    transaction_id: Id
    date: date
    amount: Money  # positive: money out
    category: str
    description: UntrustedText


def settled_bill_payments(store: Store, business_id: str) -> set[str]:
    return set(match_settlements(store, business_id, "bill").matched.values())


def relabel_candidates(store: Store, business_id: str, months: list[str]) -> list[RelabelCandidate]:
    """Uncategorised money out in the open months, not yet relabelled: the payments most likely
    to need a label."""
    if not months:
        return []
    start = month_start(months[0])
    settled = settled_bill_payments(store, business_id)
    relabelled = {
        a.transaction_id for a in store.list_adjustments(business_id, "applied") if a.transaction_id
    }
    return [
        RelabelCandidate(
            transaction_id=t.id,
            date=t.date,
            amount=-t.amount,
            category=t.category.value,
            description=t.description,
        )
        for t in store.list_transactions(business_id, start=start)
        if t.amount < 0
        and t.category is Cat.UNCATEGORISED
        and t.id not in settled
        and t.id not in relabelled
        and f"{t.date.year}-{t.date.month:02d}" in months
    ]


class ProfitEffect(CopilotModel):
    month: str
    net_profit_before: Money
    net_profit_after: Money


def _month(months: list[MonthStatements], key: str) -> MonthStatements | None:
    return next((m for m in months if m.month == key), None)


def profit_effect(
    store: Store,
    business_id: str,
    today: date,
    adj: Adjustment,
    undo: bool = False,
) -> ProfitEffect | None:
    """Net profit of the adjustment's month now, and after applying (or undoing) it."""
    now, _, reason = monthly_statements(store, business_id, today)
    preview = ((), {adj.id}) if undo else ((adj,), ())
    after, _, _ = monthly_statements(store, business_id, today, preview=preview)
    before_m, after_m = _month(now, adj.month), _month(after, adj.month)
    if reason is not None or before_m is None or after_m is None:
        return None
    return ProfitEffect(
        month=adj.month,
        net_profit_before=before_m.pnl.net_profit,
        net_profit_after=after_m.pnl.net_profit,
    )
