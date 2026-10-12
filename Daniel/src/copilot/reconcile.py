"""Light reconciliation: match invoices and bills to the bank transactions that settled them.

Used for two things:
- each customer's average payment delay (days after the due date), for the forecast;
- when each document was paid, so receivables and payables can be rebuilt at any past date
  (DSO / DPO in analysis/metrics.py).

Matching rule: a paid document is matched to the earliest not-yet-used transaction with the same
counterparty and exactly the same amount (money in for an invoice, money out for a bill), dated
on or after the document's issue date.

Known limits (see algorithms.md): same-amount documents could be matched in the wrong order,
and partial or combined payments are not matched. Full reconciliation is deferred.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from copilot.schemas import (
    Bill,
    CopilotModel,
    CounterpartyKind,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    Id,
    Invoice,
    Transaction,
)
from copilot.store import Store

UNMATCHED_WARNING_SHARE = Decimal("0.10")

DocumentKind = Literal["invoice", "bill"]


@dataclass
class Settlements:
    """Paid documents of one kind, and the date each was settled (when it could be matched)."""

    paid: list[Invoice] | list[Bill]  # sorted by issue date
    paid_on: dict[str, date] = field(default_factory=dict)  # document id -> settlement date
    unmatched: list[str] = field(default_factory=list)  # paid document ids with no match
    matched_transactions: set[str] = field(default_factory=set)  # transaction ids used
    matched: dict[str, str] = field(default_factory=dict)  # document id -> transaction id


def match_settlements(store: Store, business_id: str, kind: DocumentKind) -> Settlements:
    if kind == "invoice":
        docs = store.list_invoices(business_id, DocumentStatus.PAID)
    else:
        docs = store.list_bills(business_id, DocumentStatus.PAID)
    paid = sorted(docs, key=lambda d: (d.issue_date, d.id))
    sign = 1 if kind == "invoice" else -1
    candidates = [
        t
        for t in store.list_transactions(business_id)
        if t.counterparty_id is not None and t.amount * sign > 0
    ]  # already in date order

    result = Settlements(paid=paid)
    used = result.matched_transactions
    for doc in paid:
        match = next(
            (
                t
                for t in candidates
                if t.id not in used
                and t.counterparty_id == doc.counterparty_id
                and t.amount * sign == doc.amount
                and t.date >= doc.issue_date
            ),
            None,
        )
        if match is None:
            result.unmatched.append(doc.id)
            continue
        used.add(match.id)
        result.paid_on[doc.id] = match.date
        result.matched[doc.id] = match.id
    return result


def unlinked_receipts(store: Store, business_id: str) -> list[Transaction]:
    """Money in from customers that is not yet tied to any invoice.

    A receipt is tied if the sandbox recorded it against an invoice, the owner linked it
    (mark_invoice_paid), or it is the matched settlement of a paid invoice.
    """
    customers = {
        c.id
        for c in store.list_counterparties(business_id)
        if c.kind in (CounterpartyKind.CUSTOMER, CounterpartyKind.BOTH)
    }
    tied = set(store.receipt_links(business_id))
    tied |= match_settlements(store, business_id, "invoice").matched_transactions
    return [
        t
        for t in store.list_transactions(business_id)
        if t.amount > 0 and t.counterparty_id in customers and t.id not in tied
    ]


class Outstanding(CopilotModel):
    as_of: date
    total: Decimal
    by_document: dict[str, Decimal]  # document id -> amount unpaid at as_of (only > 0)
    assumed: list[str]  # ids whose settlement date had to be assumed (see warning)


def outstanding_at(
    open_docs: list[Invoice] | list[Bill], settlements: Settlements, as_of: date
) -> Outstanding:
    """Amount still unpaid at the end of `as_of`, over documents issued on or before it.

    - paid and matched: unpaid until the matched transaction's date
    - paid but unmatched: assumed paid on its due date (listed in `assumed`)
    - open: its current outstanding amount; any part already paid is assumed paid by as_of
      (listed in `assumed`, because the date of a part payment isn't matched)
    """
    by_doc: dict[str, Decimal] = {}
    assumed: list[str] = []
    for doc in settlements.paid:
        if doc.issue_date > as_of:
            continue
        paid_on = settlements.paid_on.get(doc.id)
        if paid_on is None:
            assumed.append(doc.id)
            paid_on = doc.due_date
        if paid_on > as_of:
            by_doc[doc.id] = doc.amount
    for doc in open_docs:
        if doc.issue_date > as_of:
            continue
        if doc.amount_paid > 0:
            assumed.append(doc.id)
        unpaid = doc.amount - doc.amount_paid
        if unpaid > 0:
            by_doc[doc.id] = unpaid
    return Outstanding(
        as_of=as_of,
        total=sum(by_doc.values(), Decimal("0")),
        by_document=by_doc,
        assumed=sorted(assumed),
    )


class CustomerDelay(CopilotModel):
    customer_id: Id
    mean_delay_days: Decimal  # positive = paid late, negative = paid early
    matched: int
    unmatched: int


def estimate_payment_delays(
    store: Store, business_id: str
) -> DomainResult[dict[str, CustomerDelay]]:
    customers = {
        c.id: c
        for c in store.list_counterparties(business_id)
        if c.kind in (CounterpartyKind.CUSTOMER, CounterpartyKind.BOTH)
    }
    settlements = match_settlements(store, business_id, "invoice")
    paid = [i for i in settlements.paid if i.counterparty_id in customers]

    delays: dict[str, list[int]] = {cid: [] for cid in customers}
    unmatched: dict[str, int] = dict.fromkeys(customers, 0)
    for invoice in paid:
        paid_on = settlements.paid_on.get(invoice.id)
        if paid_on is None:
            unmatched[invoice.counterparty_id] += 1
            continue
        delays[invoice.counterparty_id].append((paid_on - invoice.due_date).days)

    result: dict[str, CustomerDelay] = {}
    warnings: list[str] = []
    for cid in sorted(customers):
        observed = delays[cid]
        mean = (
            (Decimal(sum(observed)) / len(observed)).quantize(Decimal("0.1"))
            if observed
            else Decimal("0.0")
        )
        if not observed:
            warnings.append(
                f"No matched payments for customer {cid}; assuming they pay on the due date"
            )
        result[cid] = CustomerDelay(
            customer_id=cid, mean_delay_days=mean, matched=len(observed), unmatched=unmatched[cid]
        )

    total_unmatched = sum(unmatched.values())
    if paid and Decimal(total_unmatched) / len(paid) > UNMATCHED_WARNING_SHARE:
        warnings.append(
            f"{total_unmatched} of {len(paid)} paid invoices could not be matched to a receipt; "
            "payment-delay estimates may be less reliable"
        )

    if paid:
        coverage = DataCoverage(
            period_start=paid[0].issue_date,
            period_end=max(i.due_date for i in paid),
            record_count=len(paid),
        )
    else:
        founded = store.get_business(business_id).incorporated_on
        coverage = DataCoverage(period_start=founded, period_end=founded, record_count=0)

    return DomainResult[dict[str, CustomerDelay]](
        value=result,
        drivers=[
            Driver(
                label=cid,
                detail=f"{d.mean_delay_days} days after due date over {d.matched} invoices",
            )
            for cid, d in result.items()
        ],
        data_coverage=coverage,
        warnings=warnings,
    )
