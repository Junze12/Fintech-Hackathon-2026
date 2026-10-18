"""Reconciliation: match invoices and bills to the bank transactions that settled them, and
list the bookkeeping exceptions left over.

Used for three things:
- each customer's average payment delay (days after the due date), for the forecast;
- when each document was paid, so receivables and payables can be rebuilt at any past date
  (DSO / DPO in analysis/metrics.py);
- find_exceptions (chunk 15): duplicate payments, over and short payments, bank money no
  document claims, documents marked paid with no bank payment, and supplier statements that
  disagree with our bills.

Matching rule: a paid document is matched to the earliest not-yet-used transaction with the same
counterparty and exactly the same amount (money in for an invoice, money out for a bill), dated
on or after the document's issue date.

Known limits (see algorithms.md): same-amount documents could be matched in the wrong order,
and combined payments (one transfer for several documents) are not matched.
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
    Money,
    SupplierStatementLine,
    Transaction,
    TransactionCategory,
    TransactionSource,
    UntrustedText,
    sgd,
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
    paid_by_due: int = 0  # matched payments received on or before the due date


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
            customer_id=cid,
            mean_delay_days=mean,
            matched=len(observed),
            unmatched=unmatched[cid],
            paid_by_due=sum(1 for d in observed if d <= 0),
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


# --- Exceptions (chunk 15) ----------------------------------------------------------------
# Thresholds agreed with Daniel 2026-10-13 ("balanced set"); see algorithms.md.
DUPLICATE_WINDOW_DAYS = 7
NEAR_SHARE = Decimal("0.05")  # a payment within 5% of a document's open amount is "near" it
MATERIAL_UNCLAIMED = Decimal("1000")  # untied money from this size up is MEDIUM, below LOW
STATEMENT_MATERIAL = Decimal("100")  # a statement difference from S$100 ...
STATEMENT_MATERIAL_SHARE = Decimal("0.01")  # ... or 1% of the bill is HIGH, below LOW

Severity = Literal["high", "medium", "low"]
SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
ExceptionKind = Literal[
    "duplicate_payment",
    "bill_overpaid",
    "invoice_overpaid",
    "short_payment",
    "unlinked_match",
    "invoice_paid_no_receipt",
    "bill_paid_no_payment",
    "unclaimed_receipt",
    "unclaimed_payment",
    "unexplained_payment",
    "statement_bill_missing",
    "statement_amount_differs",
    "statement_number_differs",
]


class DocRef(CopilotModel):
    kind: DocumentKind
    id: Id
    number: UntrustedText  # from the counterparty's paperwork


class StatementRef(CopilotModel):
    id: Id
    number: UntrustedText
    description: UntrustedText | None = None  # the supplier's own words: data, never orders


class ReconException(CopilotModel):
    """One thing in the books that doesn't add up.

    `reason` and `next_step` are written from trusted parts only (ids, amounts, dates); names,
    document numbers and statement text sit in the untrusted fields beside them."""

    id: str  # stable: "<kind>:<transaction, document or statement line id>"
    kind: ExceptionKind
    severity: Severity
    amount: Money  # S$ at stake, >= 0
    difference: Money | None = None  # signed, where two amounts disagree (paid - owed, etc.)
    date: date
    counterparty_id: Id | None = None
    counterparty_name: UntrustedText | None = None
    documents: list[DocRef] = []
    transactions: list[Id] = []
    statement_lines: list[StatementRef] = []
    reason: str
    next_step: str
    next_tool: str | None = None  # an existing tool that fixes it, when one does


class Reconciliation(CopilotModel):
    as_of: date
    exceptions: list[ReconException]  # high -> low, then amount (largest first)
    counts: dict[str, int]  # every exception found, by severity (also those not shown)
    amount_by_severity: dict[str, Money]
    shown_from: Severity  # the lowest severity included in `exceptions`
    checked: dict[str, int]  # transactions, invoices, bills, statement_lines looked at


def find_exceptions(
    store: Store, business_id: str, as_of: date, min_severity: Severity = "low"
) -> DomainResult[Reconciliation]:
    """Every reconciliation exception up to `as_of`, in five passes (algorithms.md). Each
    transaction and document is used at most once, so one mistake gives one exception."""
    txns = [t for t in store.list_transactions(business_id) if t.date <= as_of]
    invoices = [d for d in store.list_invoices(business_id) if d.issue_date <= as_of]
    bills = [d for d in store.list_bills(business_id) if d.issue_date <= as_of]
    statement = [
        line
        for line in store.list_supplier_statement_lines(business_id)
        if line.statement_date <= as_of
    ]
    names = {c.id: c.name for c in store.list_counterparties(business_id)}
    history_start = txns[0].date if txns else as_of

    # Pass 0: what is already explained.
    inv = match_settlements(store, business_id, "invoice")
    bil = match_settlements(store, business_id, "bill")
    tied = inv.matched_transactions | bil.matched_transactions
    tied |= set(store.receipt_links(business_id))
    tied |= {t.id for t in txns if t.source is TransactionSource.SANDBOX}  # posted for an action
    settled_docs = set(inv.matched) | set(bil.matched)
    untied = [t for t in txns if t.id not in tied]
    found: list[ReconException] = []
    used: set[str] = set()  # transactions and documents already explained by an exception

    def party(cid: str | None) -> dict:
        return {"counterparty_id": cid, "counterparty_name": names.get(cid) if cid else None}

    # Pass 1: duplicate payments.
    position = {t.id: i for i, t in enumerate(txns)}
    for t in untied:
        if t.amount >= 0:
            continue
        earlier = next(
            (
                e
                for e in txns[: position[t.id]]
                if e.account_id == t.account_id
                and e.amount == t.amount
                and e.id not in used
                and 0 <= (t.date - e.date).days <= DUPLICATE_WINDOW_DAYS
                and (
                    e.counterparty_id == t.counterparty_id
                    if t.counterparty_id or e.counterparty_id
                    else e.description == t.description
                )
            ),
            None,
        )
        if earlier is None:
            continue
        used.add(t.id)
        days = (t.date - earlier.date).days
        found.append(
            ReconException(
                id=f"duplicate_payment:{t.id}",
                kind="duplicate_payment",
                severity="high",
                amount=-t.amount,
                date=t.date,
                transactions=[earlier.id, t.id],
                reason=(
                    f"Payment {t.id} of {sgd(-t.amount)} on {t.date.isoformat()} repeats "
                    f"{earlier.id} from {days} day(s) earlier: same account, payee and amount."
                ),
                next_step=(
                    "Check with the payee whether they were paid twice; if so, ask for a "
                    "refund or a credit against the next bill."
                ),
                **party(t.counterparty_id),
            )
        )

    # Pass 2: a payment near (not at) a document's open amount, or exactly at an open document
    # nobody linked.
    def residuals(docs: list[Invoice] | list[Bill]) -> list[tuple[Invoice | Bill, Decimal]]:
        out: list[tuple[Invoice | Bill, Decimal]] = []
        for d in docs:
            if d.status is DocumentStatus.PAID:
                if d.id not in settled_docs:
                    out.append((d, d.amount))
            elif d.status is DocumentStatus.OPEN and d.amount > d.amount_paid:
                out.append((d, d.amount - d.amount_paid))
        return out

    pools = {"invoice": residuals(invoices), "bill": residuals(bills)}
    for t in untied:
        if t.id in used or t.counterparty_id is None:
            continue
        kind: DocumentKind = "invoice" if t.amount > 0 else "bill"
        paid = abs(t.amount)
        near = [
            (abs(paid - owed), d.issue_date, d.id, d, owed)
            for d, owed in pools[kind]
            if d.id not in used
            and d.counterparty_id == t.counterparty_id
            and d.issue_date <= t.date
            and abs(paid - owed) <= owed * NEAR_SHARE
        ]
        if not near:
            continue
        *_, doc, owed = min(near, key=lambda n: n[:3])
        used |= {t.id, doc.id}
        found.append(_near_exception(t, doc, kind, paid, owed, party(t.counterparty_id)))

    # Pass 3: documents marked paid that no bank payment explains.
    skipped_early = 0
    for kind, docs in (("invoice", invoices), ("bill", bills)):
        for d in docs:
            if d.status is not DocumentStatus.PAID or d.id in settled_docs or d.id in used:
                continue
            if d.issue_date < history_start:
                skipped_early += 1  # may have been paid before the bank history starts
                continue
            used.add(d.id)
            found.append(_paid_unexplained(d, kind, party(d.counterparty_id)))

    # Pass 4: bank money no document claims.
    for t in untied:
        if t.id in used:
            continue
        if t.counterparty_id is None and t.category is not TransactionCategory.UNCATEGORISED:
            continue  # rent, payroll, tax, ...: no document expected
        used.add(t.id)
        found.append(_unclaimed(t, party(t.counterparty_id)))

    # Pass 5: supplier statements vs our bills.
    for line in statement:
        found.extend(_statement_check(line, bills, used, party(line.counterparty_id)))

    counts = dict.fromkeys(SEVERITY_ORDER, 0)
    totals = dict.fromkeys(SEVERITY_ORDER, Decimal("0"))
    for x in found:
        counts[x.severity] += 1
        totals[x.severity] += x.amount
    found.sort(key=lambda x: (SEVERITY_ORDER[x.severity], -x.amount, x.date, x.id))
    shown = [x for x in found if SEVERITY_ORDER[x.severity] <= SEVERITY_ORDER[min_severity]]

    warnings = []
    if not statement:
        warnings.append("No supplier statements loaded; statement checks were skipped")
    if skipped_early:
        warnings.append(
            f"{skipped_early} paid document(s) issued before the bank history starts "
            f"({history_start.isoformat()}) were not checked"
        )
    return DomainResult[Reconciliation](
        value=Reconciliation(
            as_of=as_of,
            exceptions=shown,
            counts=counts,
            amount_by_severity=totals,
            shown_from=min_severity,
            checked={
                "transactions": len(txns),
                "invoices": len(invoices),
                "bills": len(bills),
                "statement_lines": len(statement),
            },
        ),
        drivers=[
            Driver(label=f"{x.severity}: {x.kind}", amount=x.amount, detail=x.reason)
            for x in shown[:5]
        ],
        data_coverage=DataCoverage(
            period_start=history_start, period_end=as_of, record_count=len(txns)
        ),
        warnings=warnings,
    )


def _ref(doc: Invoice | Bill, kind: DocumentKind) -> DocRef:
    return DocRef(kind=kind, id=doc.id, number=doc.number)


def _near_exception(
    t: Transaction,
    doc: Invoice | Bill,
    kind: DocumentKind,
    paid: Decimal,
    owed: Decimal,
    who: dict,
) -> ReconException:
    diff = paid - owed
    common = {
        "date": t.date,
        "documents": [_ref(doc, kind)],
        "transactions": [t.id],
        "difference": diff,
        **who,
    }
    what = "Receipt" if kind == "invoice" else "Payment"
    base = f"{what} {t.id} of {sgd(paid)} vs {kind} {doc.id}, owed {sgd(owed)}"
    if diff == 0:
        if kind == "invoice":
            step = (
                "Link the receipt to the invoice (mark_invoice_paid, owner) so receivables "
                "and the forecast stop counting it as owed."
            )
            tool = "mark_invoice_paid"
        else:
            step, tool = "Record the bill as paid in the accounting records.", None
        return ReconException(
            id=f"unlinked_match:{t.id}",
            kind="unlinked_match",
            severity="low",
            amount=paid,
            reason=f"{base}: same amount, but the two are not linked.",
            next_step=step,
            next_tool=tool,
            **common,
        )
    if diff < 0:
        step = (
            "Ask the customer about the shortfall (bank charges or a dispute?); the rest is "
            "still owed."
            if kind == "invoice"
            else "The supplier may still be owed the difference; check their statement."
        )
        return ReconException(
            id=f"short_payment:{t.id}",
            kind="short_payment",
            severity="medium",
            amount=-diff,
            reason=f"{base}: {sgd(-diff)} short.",
            next_step=step,
            **common,
        )
    if kind == "bill":
        return ReconException(
            id=f"bill_overpaid:{t.id}",
            kind="bill_overpaid",
            severity="high",
            amount=diff,
            reason=f"{base}: {sgd(diff)} paid too much.",
            next_step="Ask the supplier for a refund or a credit against the next bill.",
            **common,
        )
    return ReconException(
        id=f"invoice_overpaid:{t.id}",
        kind="invoice_overpaid",
        severity="medium",
        amount=diff,
        reason=f"{base}: the customer paid {sgd(diff)} too much.",
        next_step=(
            "Confirm with the customer; refund the extra or set it against their next invoice."
        ),
        **common,
    )


def _paid_unexplained(doc: Invoice | Bill, kind: DocumentKind, who: dict) -> ReconException:
    if kind == "invoice":
        return ReconException(
            id=f"invoice_paid_no_receipt:{doc.id}",
            kind="invoice_paid_no_receipt",
            severity="high",
            amount=doc.amount,
            date=doc.due_date,
            documents=[_ref(doc, kind)],
            reason=(
                f"Invoice {doc.id} ({sgd(doc.amount)}) is marked paid, but no receipt in the "
                "bank matches it."
            ),
            next_step=(
                "Check whether the customer really paid (another account, cash?); if not, "
                "reopen the invoice and chase it."
            ),
            **who,
        )
    return ReconException(
        id=f"bill_paid_no_payment:{doc.id}",
        kind="bill_paid_no_payment",
        severity="medium",
        amount=doc.amount,
        date=doc.due_date,
        documents=[_ref(doc, kind)],
        reason=f"Bill {doc.id} ({sgd(doc.amount)}) is marked paid, but no bank payment matches it.",
        next_step="Check whether it was paid from another account; if not, it is still owed.",
        **who,
    )


def _unclaimed(t: Transaction, who: dict) -> ReconException:
    size = abs(t.amount)
    when = t.date.isoformat()
    if t.counterparty_id is None and t.amount < 0:
        return ReconException(
            id=f"unexplained_payment:{t.id}",
            kind="unexplained_payment",
            severity="low",
            amount=size,
            date=t.date,
            transactions=[t.id],
            reason=f"Payment {t.id} of {sgd(size)} on {when} has no payee, category or document.",
            next_step=(
                "Find out what it was; it can be relabelled to a cost line or owner drawings "
                "with an adjustment."
            ),
            next_tool="draft_adjustment",
            **who,
        )
    severity: Severity = "medium" if size >= MATERIAL_UNCLAIMED else "low"
    if t.amount > 0:
        return ReconException(
            id=f"unclaimed_receipt:{t.id}",
            kind="unclaimed_receipt",
            severity=severity,
            amount=size,
            date=t.date,
            transactions=[t.id],
            reason=f"Receipt {t.id} of {sgd(size)} on {when} matches no invoice.",
            next_step=(
                "Find the invoice it pays or record one; if the money isn't yours, contact "
                "the bank."
            ),
            **who,
        )
    return ReconException(
        id=f"unclaimed_payment:{t.id}",
        kind="unclaimed_payment",
        severity=severity,
        amount=size,
        date=t.date,
        transactions=[t.id],
        reason=f"Payment {t.id} of {sgd(size)} on {when} matches no bill.",
        next_step="Find, or ask the supplier for, the bill this payment was for.",
        **who,
    )


def _number_key(number: str) -> str:
    return number.strip().casefold()


def _statement_check(
    line: SupplierStatementLine, bills: list[Bill], used: set[str], who: dict
) -> list[ReconException]:
    """Pass 5 for one statement line: find our bill by number, else by amount and date."""
    ref = StatementRef(id=line.id, number=line.number, description=line.description)
    free = [
        b for b in bills if b.counterparty_id == line.counterparty_id and f"stmt:{b.id}" not in used
    ]
    by_number = [b for b in free if _number_key(b.number) == _number_key(line.number)]
    bill = min(by_number, key=lambda b: (b.amount != line.amount, b.issue_date, b.id), default=None)
    renumbered = False
    if bill is None:
        bill = next(
            (b for b in free if b.amount == line.amount and b.issue_date == line.issue_date), None
        )
        renumbered = bill is not None
    if bill is None:
        return [
            ReconException(
                id=f"statement_bill_missing:{line.id}",
                kind="statement_bill_missing",
                severity="high",
                amount=line.amount,
                date=line.issue_date,
                statement_lines=[ref],
                reason=(
                    f"Statement line {line.id} lists a bill of {sgd(line.amount)} dated "
                    f"{line.issue_date.isoformat()} that is not in our bills."
                ),
                next_step=(
                    "Ask the supplier for a copy and check it was really ordered and received "
                    "before recording or paying it."
                ),
                **who,
            )
        ]
    used.add(f"stmt:{bill.id}")
    if renumbered:
        return [
            ReconException(
                id=f"statement_number_differs:{line.id}",
                kind="statement_number_differs",
                severity="low",
                amount=bill.amount,
                date=line.issue_date,
                documents=[_ref(bill, "bill")],
                statement_lines=[ref],
                reason=(
                    f"Statement line {line.id} and bill {bill.id} agree on amount "
                    f"({sgd(bill.amount)}) and date, but the bill numbers differ."
                ),
                next_step="Check the bill reference with the supplier and correct it.",
                **who,
            )
        ]
    diff = line.amount - bill.amount
    if diff == 0:
        return []
    material = (
        abs(diff) >= STATEMENT_MATERIAL or abs(diff) >= bill.amount * STATEMENT_MATERIAL_SHARE
    )
    return [
        ReconException(
            id=f"statement_amount_differs:{line.id}",
            kind="statement_amount_differs",
            severity="high" if material else "low",
            amount=abs(diff),
            difference=diff,
            date=line.issue_date,
            documents=[_ref(bill, "bill")],
            statement_lines=[ref],
            reason=(
                f"Statement line {line.id} says {sgd(line.amount)}; our bill {bill.id} says "
                f"{sgd(bill.amount)} (difference {sgd(diff)})."
            ),
            next_step=(
                "Compare both copies of the bill with the supplier; don't pay a difference "
                "until it is agreed."
            ),
            **who,
        )
    ]
