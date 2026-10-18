"""The scripted world: what happens outside the copilot as the simulated clock moves forward.

A scenario folder may hold world_events.csv (written by synthetic.py): the business's true
next 13 weeks. Customers pay invoices, direct debits (rent, payroll, GST) leave the account,
the business pays supplier bills in its own banking app, and new invoices and bills are issued.
Replaying it day by day keeps the sandbox realistic: without it, advancing the clock would
silently skip rent and payroll and the forecast would look better than reality.

Rules:
- Only the policy scheduler replays it (one day at a time, after setting the clock to that day).
  The forecast never reads it: it holds the future (known risk R12).
- It is simulation configuration, not business data, so it is loaded here rather than through
  an adapter. Rows are still validated, and bad rows are rejected with reasons.
- Same-day order: new documents, money in, transfers, money out.
- A supplier bill is skipped if the owner is paying it through the copilot (a scheduled or
  executed payment exists) or if it is no longer open. A debit that would overdraw the account
  bounces. Every outcome, including skips, goes to the sandbox event log.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from copilot.sandbox.bank import Outcome, Sandbox, SandboxResult
from copilot.schemas import (
    Bill,
    CopilotModel,
    DocumentStatus,
    Id,
    Invoice,
    Money,
    PaymentStatus,
    RejectedRow,
    TransactionCategory,
    UntrustedText,
)

FILENAME = "world_events.csv"

EventKind = Literal["invoice_issued", "bill_issued", "receipt", "bill_payment", "debit", "transfer"]
_ORDER = {"invoice_issued": 0, "bill_issued": 0, "receipt": 1, "transfer": 2}


class WorldEvent(CopilotModel):
    id: Id
    date: date
    kind: EventKind
    ref_id: str | None = None
    counterparty_id: Id | None = None
    account_id: Id
    amount: Money
    category: TransactionCategory | None = None
    number: UntrustedText | None = None
    issue_date: date | None = None
    due_date: date | None = None
    description: UntrustedText | None = None
    gst: Money | None = None  # GST included in an issued document's amount


class WorldOutcome(CopilotModel):
    """What happened to one scripted event when it was replayed."""

    event_id: Id
    date: date
    kind: EventKind
    description: UntrustedText  # contains counterparty names and document numbers
    amount: Money
    outcome: Outcome
    reason: str | None = None


class WorldScript:
    def __init__(
        self,
        events: list[WorldEvent] | None = None,
        rejected: list[RejectedRow] | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        self.events = sorted(events or [], key=lambda e: (e.date, _ORDER.get(e.kind, 3)))
        self.rejected = rejected or []
        self.warnings = warnings or []

    @classmethod
    def load(cls, folder: Path) -> WorldScript:
        path = folder / FILENAME
        if not path.exists():
            return cls(warnings=[f"No {FILENAME}: the clock only runs scheduled payments"])
        events: list[WorldEvent] = []
        rejected: list[RejectedRow] = []
        with path.open(encoding="utf-8", newline="") as handle:
            for line, row in enumerate(csv.DictReader(handle), start=2):
                cleaned = {k: (v if v != "" else None) for k, v in row.items() if k is not None}
                try:
                    events.append(WorldEvent.model_validate(cleaned))
                except ValidationError as exc:
                    reason = "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                    )
                    raw = {k: v for k, v in row.items() if k is not None and v is not None}
                    rejected.append(RejectedRow(file=FILENAME, line=line, reason=reason, raw=raw))
        return cls(events, rejected)

    @property
    def end(self) -> date | None:
        """Last day the script covers; the clock can't be advanced past it."""
        return self.events[-1].date if self.events else None

    def on(self, day: date) -> list[WorldEvent]:
        return [e for e in self.events if e.date == day]

    def replay_day(self, sandbox: Sandbox, business_id: str, day: date) -> list[WorldOutcome]:
        """Apply the day's events. The sandbox clock must already be set to `day`."""
        if sandbox.today(business_id) != day:
            raise ValueError("set the sandbox clock to the day before replaying it")
        return [
            _outcome(e, _apply(sandbox, business_id, e), _label(sandbox, business_id, e))
            for e in self.on(day)
        ]


def _apply(sandbox: Sandbox, business_id: str, e: WorldEvent) -> SandboxResult:
    store = sandbox.store
    txn_id = f"sbx-world-{e.id}"
    if e.kind in ("invoice_issued", "bill_issued"):
        kind = "invoice" if e.kind == "invoice_issued" else "bill"
        model = Invoice if kind == "invoice" else Bill
        doc = model(
            id=e.ref_id,
            business_id=business_id,
            counterparty_id=e.counterparty_id,
            number=e.number,
            issue_date=e.issue_date or e.date,
            due_date=e.due_date,
            amount=e.amount,
            gst=e.gst or 0,
        )
        try:
            store.get_document(business_id, kind, doc.id)
        except LookupError:
            store.add_document(kind, doc)
            sandbox.log_event(business_id, f"world_{e.kind}", doc.id, doc.amount)
            return SandboxResult(outcome="executed")
        return sandbox.log_skip(business_id, f"world_{e.kind}", doc.id, doc.amount, "exists")

    if e.kind == "receipt":
        try:
            invoice = store.get_document(business_id, "invoice", e.ref_id or "")
        except LookupError:
            return sandbox.log_skip(business_id, "world_receipt", e.id, e.amount, "no invoice")
        outstanding = invoice.amount - invoice.amount_paid
        if invoice.status is not DocumentStatus.OPEN or outstanding <= 0:
            return sandbox.log_skip(
                business_id, "world_receipt", invoice.id, e.amount, "invoice already paid"
            )
        return sandbox.record_invoice_receipt(
            business_id,
            invoice.id,
            outstanding,
            e.account_id,
            action="world_receipt",
            txn_id=txn_id,
            description=e.description,
            category=e.category or TransactionCategory.UNCATEGORISED,
        )

    if e.kind == "bill_payment":
        bill_id = e.ref_id or ""
        handled = store.list_scheduled_payments(
            business_id, (PaymentStatus.SCHEDULED, PaymentStatus.EXECUTED), bill_id=bill_id
        )
        if handled:
            return sandbox.log_skip(
                business_id,
                "world_bill_payment",
                bill_id,
                e.amount,
                "the owner is paying this bill through the copilot",
            )
        return sandbox.pay_bill_directly(
            business_id,
            bill_id,
            e.account_id,
            txn_id=txn_id,
            description=e.description or f"Bill payment {bill_id}",
            category=e.category or TransactionCategory.UNCATEGORISED,
        )

    if e.kind == "transfer":
        return sandbox.transfer(
            business_id,
            txn_id=txn_id,
            from_account_id=e.account_id,
            to_account_id=e.ref_id or "",
            amount=e.amount,
            description=e.description or "Transfer",
        )

    return sandbox.post_external(
        business_id,
        txn_id=txn_id,
        account_id=e.account_id,
        amount=e.amount,
        description=e.description or "Direct debit",
        category=e.category or TransactionCategory.UNCATEGORISED,
        action="world_debit",
    )


def _label(sandbox: Sandbox, business_id: str, e: WorldEvent) -> str:
    if e.kind in ("invoice_issued", "bill_issued"):
        names = {c.id: c.name for c in sandbox.store.list_counterparties(business_id)}
        who = names.get(e.counterparty_id or "", e.counterparty_id or "")
        what = "Invoice" if e.kind == "invoice_issued" else "Bill"
        return f"{what} {e.number} issued ({who}), due {e.due_date}"
    return e.description or e.kind


def _outcome(e: WorldEvent, result: SandboxResult, label: str) -> WorldOutcome:
    return WorldOutcome(
        event_id=e.id,
        date=e.date,
        kind=e.kind,
        description=label,
        amount=e.amount,
        outcome=result.outcome,
        reason=result.reason,
    )
