"""The sandbox bank: simulated accounts, a ledger and a clock.

This is the mechanical bank. It does NOT check roles, limits, allowlists or user
confirmation - that is the policy layer's job. Agent tools must never call it directly;
every write goes through policy/ first.

What it does guarantee:
- Executed payments and receipts become normal Transaction rows (source=sandbox) in the
  same table as imported history, so balances, analysis and forecasts see them at once.
- A payment that would overdraw the account is blocked, not executed.
- A payment can only execute once (it must be in status 'scheduled', and its ledger
  entry id is derived from the payment id, so the database rejects a second posting).
- Every attempt, successful or not, is written to the sandbox event log.
- Every posted transaction is categorised on the way in with the same deterministic rules
  used at import (categorize.classify), so analysis sees a paid bill as e.g. cogs at once.
  What no rule matches stays uncategorised and is flagged downstream, never guessed.

Activity outside the copilot (customers paying, direct debits, the business paying a bill in
its own banking app) comes from the scripted world (sandbox/world.py) through the
post_external / pay_bill_directly / transfer methods. It is logged with a "world_" action so
the evidence log separates what the world did from what the copilot did.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from copilot.categorize import classify
from copilot.schemas import (
    SGT,
    CopilotModel,
    DocumentStatus,
    Id,
    Money,
    PaymentStatus,
    Timestamp,
    Transaction,
    TransactionCategory,
    TransactionSource,
)
from copilot.store import NotFoundError, Store, from_cents, to_cents

_SANDBOX_SCHEMA = """
CREATE TABLE IF NOT EXISTS sandbox_clock (
    business_id TEXT PRIMARY KEY REFERENCES businesses(id),
    today TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sandbox_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id TEXT NOT NULL REFERENCES businesses(id),
    sim_date TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    action TEXT NOT NULL,
    object_id TEXT NOT NULL,
    amount_cents INTEGER,
    outcome TEXT NOT NULL,
    reason TEXT
);
"""

_DESCRIPTION_MAX = 500

Outcome = Literal["executed", "blocked", "rejected", "skipped"]


class SandboxResult(CopilotModel):
    """What happened when the sandbox was asked to do something."""

    outcome: Outcome
    reason: str | None = None
    transaction_id: Id | None = None
    balance_after: Money | None = None


class SandboxEvent(CopilotModel):
    """One line of the sandbox bank's operation log (execution evidence, deliverable #6)."""

    seq: int
    business_id: Id
    sim_date: date
    logged_at: Timestamp
    action: str
    object_id: str
    amount: Money | None = None
    outcome: Outcome
    reason: str | None = None


class Sandbox:
    def __init__(self, store: Store) -> None:
        self.store = store
        store.conn.executescript(_SANDBOX_SCHEMA)

    # --- Clock ----------------------------------------------------------------

    def today(self, business_id: str) -> date:
        """The simulated 'today'. First call fixes it to the latest data date."""
        row = self.store.conn.execute(
            "SELECT today FROM sandbox_clock WHERE business_id = ?", (business_id,)
        ).fetchone()
        if row is not None:
            return date.fromisoformat(row["today"])
        start = self.store.latest_transaction_date(business_id) or self._earliest_opening(
            business_id
        )
        self.set_today(business_id, start)
        return start

    def set_today(self, business_id: str, today: date) -> None:
        self.store.conn.execute(
            "INSERT INTO sandbox_clock VALUES (?, ?) "
            "ON CONFLICT(business_id) DO UPDATE SET today = excluded.today",
            (business_id, today.isoformat()),
        )

    def advance(self, business_id: str, days: int) -> date:
        if days < 0:
            raise ValueError("the sandbox clock only moves forward")
        new_today = self.today(business_id) + timedelta(days=days)
        self.set_today(business_id, new_today)
        return new_today

    def _earliest_opening(self, business_id: str) -> date:
        accounts = self.store.list_accounts(business_id)
        if not accounts:
            raise NotFoundError(f"no accounts for business {business_id}")
        return min(a.opening_date for a in accounts)

    # --- Balances -------------------------------------------------------------

    def balance(self, business_id: str, account_id: str, as_of: date | None = None) -> Decimal:
        """Opening balance plus every transaction up to and including as_of (default: today)."""
        as_of = as_of or self.today(business_id)
        account = self.store.get_account(business_id, account_id)
        return account.opening_balance + self.store.sum_transactions(business_id, account_id, as_of)

    def balances(self, business_id: str, as_of: date | None = None) -> dict[str, Decimal]:
        as_of = as_of or self.today(business_id)
        return {
            a.id: self.balance(business_id, a.id, as_of)
            for a in self.store.list_accounts(business_id)
        }

    def _categorised(self, txn: Transaction) -> Transaction:
        """Apply the import-time categorisation rules to a transaction about to be posted."""
        if txn.category is not TransactionCategory.UNCATEGORISED:
            return txn
        counterparty = None
        if txn.counterparty_id is not None:
            counterparty = next(
                (
                    c
                    for c in self.store.list_counterparties(txn.business_id)
                    if c.id == txn.counterparty_id
                ),
                None,
            )
        category, _rule = classify(txn, counterparty)
        return txn.model_copy(update={"category": category})

    # --- Payments -------------------------------------------------------------

    def execute_payment(self, business_id: str, payment_id: str) -> SandboxResult:
        """Execute a scheduled payment now. Never raises for business failures."""
        action = "execute_payment"
        today = self.today(business_id)
        try:
            payment = self.store.get_scheduled_payment(business_id, payment_id)
        except NotFoundError:
            return self._reject(business_id, action, payment_id, None, "payment not found")

        if payment.status is not PaymentStatus.SCHEDULED:
            return self._reject(
                business_id,
                action,
                payment_id,
                payment.amount,
                f"payment is {payment.status.value}, not scheduled",
            )
        if payment.pay_on > today:
            return self._reject(
                business_id,
                action,
                payment_id,
                payment.amount,
                f"payment is not due until {payment.pay_on.isoformat()}",
            )

        bill = None
        if payment.bill_id is not None:
            bill = self.store.get_document(business_id, "bill", payment.bill_id)
            if payment.amount > bill.amount - bill.amount_paid:
                return self._reject(
                    business_id,
                    action,
                    payment_id,
                    payment.amount,
                    "payment exceeds the bill's outstanding amount",
                )

        balance = self.balance(business_id, payment.from_account_id, today)
        if balance - payment.amount < 0:
            with self.store.transaction():
                self.store.update_payment_status(business_id, payment_id, PaymentStatus.BLOCKED)
                self._log(
                    business_id,
                    action,
                    payment_id,
                    payment.amount,
                    "blocked",
                    "insufficient funds",
                )
            return SandboxResult(
                outcome="blocked", reason="insufficient funds", balance_after=balance
            )

        payee = self.store.get_payee(business_id, payment.payee_id)
        description = f"Payment to {payee.name}"
        if payment.reference:
            description += f" (ref {payment.reference})"
        txn = Transaction(
            id=f"sbx-pay-{payment_id}",
            business_id=business_id,
            account_id=payment.from_account_id,
            date=today,
            amount=-payment.amount,
            description=description[:_DESCRIPTION_MAX],
            counterparty_id=bill.counterparty_id if bill is not None else None,
            source=TransactionSource.SANDBOX,
        )
        with self.store.transaction():
            self.store.add_transaction(self._categorised(txn))
            self.store.update_payment_status(business_id, payment_id, PaymentStatus.EXECUTED)
            if bill is not None:
                paid = bill.amount_paid + payment.amount
                status = DocumentStatus.PAID if paid == bill.amount else DocumentStatus.OPEN
                self.store.update_document(business_id, "bill", bill.id, paid, status)
            self._log(business_id, action, payment_id, payment.amount, "executed", None)
        return SandboxResult(
            outcome="executed",
            transaction_id=txn.id,
            balance_after=balance - payment.amount,
        )

    # --- Receipts -------------------------------------------------------------

    def record_invoice_receipt(
        self,
        business_id: str,
        invoice_id: str,
        amount: Decimal,
        account_id: str,
        *,
        action: str = "record_invoice_receipt",
        txn_id: str | None = None,
        description: str | None = None,
        category: TransactionCategory = TransactionCategory.UNCATEGORISED,
    ) -> SandboxResult:
        """A customer pays (part of) an invoice into one of the business's accounts."""
        today = self.today(business_id)
        if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
            return self._reject(
                business_id, action, invoice_id, None, "amount must have at most 2 decimal places"
            )
        try:
            invoice = self.store.get_document(business_id, "invoice", invoice_id)
            self.store.get_account(business_id, account_id)
        except NotFoundError as exc:
            return self._reject(business_id, action, invoice_id, amount, f"{exc} not found")

        if invoice.status is not DocumentStatus.OPEN:
            return self._reject(
                business_id, action, invoice_id, amount, f"invoice is {invoice.status.value}"
            )
        if amount <= 0 or amount > invoice.amount - invoice.amount_paid:
            return self._reject(
                business_id,
                action,
                invoice_id,
                amount,
                "amount must be positive and no more than the outstanding balance",
            )

        txn = Transaction(
            id=txn_id or f"sbx-rcpt-{uuid4().hex[:12]}",
            business_id=business_id,
            account_id=account_id,
            date=today,
            amount=amount,
            description=(description or f"Receipt for invoice {invoice.number}")[:_DESCRIPTION_MAX],
            counterparty_id=invoice.counterparty_id,
            category=category,
            source=TransactionSource.SANDBOX,
        )
        paid = invoice.amount_paid + amount
        status = DocumentStatus.PAID if paid == invoice.amount else DocumentStatus.OPEN
        with self.store.transaction():
            self.store.add_transaction(self._categorised(txn))
            self.store.update_document(business_id, "invoice", invoice_id, paid, status)
            self.store.link_receipt(
                business_id, txn.id, invoice_id, amount, "sandbox", datetime.now(SGT)
            )
            self._log(business_id, action, invoice_id, amount, "executed", None)
        return SandboxResult(
            outcome="executed",
            transaction_id=txn.id,
            balance_after=self.balance(business_id, account_id, today),
        )

    # --- Activity outside the copilot (scripted world) -------------------------

    def post_external(
        self,
        business_id: str,
        *,
        txn_id: str,
        account_id: str,
        amount: Decimal,
        description: str,
        category: TransactionCategory,
        action: str,
    ) -> SandboxResult:
        """Money in or out that the business didn't make through the copilot (e.g. a direct
        debit). A debit that would overdraw the account bounces."""
        today = self.today(business_id)
        if self.store.has_transaction(business_id, txn_id):
            return self._reject(business_id, action, txn_id, amount, "already posted")
        balance = self.balance(business_id, account_id, today)
        if amount < 0 and balance + amount < 0:
            return self._bounce(business_id, action, txn_id, -amount, balance)
        txn = Transaction(
            id=txn_id,
            business_id=business_id,
            account_id=account_id,
            date=today,
            amount=amount,
            description=description[:_DESCRIPTION_MAX],
            category=category,
            source=TransactionSource.SANDBOX,
        )
        with self.store.transaction():
            self.store.add_transaction(self._categorised(txn))
            self._log(business_id, action, txn_id, abs(amount), "executed", None)
        return SandboxResult(
            outcome="executed", transaction_id=txn_id, balance_after=balance + amount
        )

    def pay_bill_directly(
        self,
        business_id: str,
        bill_id: str,
        account_id: str,
        *,
        txn_id: str,
        description: str,
        category: TransactionCategory = TransactionCategory.UNCATEGORISED,
    ) -> SandboxResult:
        """The business pays a bill's outstanding balance outside the copilot (its own banking
        routine). Bounces if the account can't cover it; the bill then stays open."""
        action = "world_bill_payment"
        today = self.today(business_id)
        try:
            bill = self.store.get_document(business_id, "bill", bill_id)
        except NotFoundError:
            return self._reject(business_id, action, bill_id, None, "bill not found")
        outstanding = bill.amount - bill.amount_paid
        if bill.status is not DocumentStatus.OPEN or outstanding <= 0:
            return self._skip(business_id, action, bill_id, None, f"bill is {bill.status.value}")
        balance = self.balance(business_id, account_id, today)
        if balance - outstanding < 0:
            return self._bounce(business_id, action, bill_id, outstanding, balance)
        txn = Transaction(
            id=txn_id,
            business_id=business_id,
            account_id=account_id,
            date=today,
            amount=-outstanding,
            description=description[:_DESCRIPTION_MAX],
            counterparty_id=bill.counterparty_id,
            category=category,
            source=TransactionSource.SANDBOX,
        )
        with self.store.transaction():
            self.store.add_transaction(self._categorised(txn))
            self.store.update_document(
                business_id, "bill", bill_id, bill.amount, DocumentStatus.PAID
            )
            self._log(business_id, action, bill_id, outstanding, "executed", None)
        return SandboxResult(
            outcome="executed", transaction_id=txn_id, balance_after=balance - outstanding
        )

    def transfer(
        self,
        business_id: str,
        *,
        txn_id: str,
        from_account_id: str,
        to_account_id: str,
        amount: Decimal,
        description: str,
    ) -> SandboxResult:
        """Move money between two of the business's own accounts (total cash is unchanged)."""
        action = "world_transfer"
        today = self.today(business_id)
        if self.store.has_transaction(business_id, f"{txn_id}-out"):
            return self._reject(business_id, action, txn_id, amount, "already posted")
        balance = self.balance(business_id, from_account_id, today)
        if balance - amount < 0:
            return self._bounce(business_id, action, txn_id, amount, balance)
        legs = [
            (f"{txn_id}-out", from_account_id, -amount),
            (f"{txn_id}-in", to_account_id, amount),
        ]
        with self.store.transaction():
            for leg_id, account_id, leg_amount in legs:
                self.store.add_transaction(
                    Transaction(
                        id=leg_id,
                        business_id=business_id,
                        account_id=account_id,
                        date=today,
                        amount=leg_amount,
                        description=description[:_DESCRIPTION_MAX],
                        category=TransactionCategory.TRANSFER,
                        source=TransactionSource.SANDBOX,
                    )
                )
            self._log(business_id, action, txn_id, amount, "executed", None)
        return SandboxResult(
            outcome="executed", transaction_id=f"{txn_id}-out", balance_after=balance - amount
        )

    def log_skip(
        self, business_id: str, action: str, object_id: str, amount: Decimal | None, reason: str
    ) -> SandboxResult:
        """Record that a scripted event was deliberately not applied, and why."""
        return self._skip(business_id, action, object_id, amount, reason)

    def log_event(
        self, business_id: str, action: str, object_id: str, amount: Decimal | None
    ) -> None:
        """Record a non-money event (e.g. a new invoice was issued)."""
        self._log(business_id, action, object_id, amount, "executed", None)

    def _bounce(
        self, business_id: str, action: str, object_id: str, amount: Decimal, balance: Decimal
    ) -> SandboxResult:
        self._log(business_id, action, object_id, amount, "blocked", "insufficient funds")
        return SandboxResult(outcome="blocked", reason="insufficient funds", balance_after=balance)

    def _skip(
        self, business_id: str, action: str, object_id: str, amount: Decimal | None, reason: str
    ) -> SandboxResult:
        self._log(business_id, action, object_id, amount, "skipped", reason)
        return SandboxResult(outcome="skipped", reason=reason)

    # --- Event log ------------------------------------------------------------

    def events(self, business_id: str) -> list[SandboxEvent]:
        rows = self.store.conn.execute(
            "SELECT * FROM sandbox_events WHERE business_id = ? ORDER BY seq", (business_id,)
        )
        return [
            SandboxEvent(
                seq=r["seq"],
                business_id=r["business_id"],
                sim_date=date.fromisoformat(r["sim_date"]),
                logged_at=datetime.fromisoformat(r["logged_at"]),
                action=r["action"],
                object_id=r["object_id"],
                amount=from_cents(r["amount_cents"]) if r["amount_cents"] is not None else None,
                outcome=r["outcome"],
                reason=r["reason"],
            )
            for r in rows
        ]

    def _log(
        self,
        business_id: str,
        action: str,
        object_id: str,
        amount: Decimal | None,
        outcome: Outcome,
        reason: str | None,
    ) -> None:
        self.store.conn.execute(
            "INSERT INTO sandbox_events "
            "(business_id, sim_date, logged_at, action, object_id, amount_cents, outcome, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                business_id,
                self.today(business_id).isoformat(),
                datetime.now(SGT).isoformat(),
                action,
                object_id,
                to_cents(amount) if amount is not None else None,
                outcome,
                reason,
            ),
        )

    def _reject(
        self,
        business_id: str,
        action: str,
        object_id: str,
        amount: Decimal | None,
        reason: str,
    ) -> SandboxResult:
        self._log(business_id, action, object_id, amount, "rejected", reason)
        return SandboxResult(outcome="rejected", reason=reason)
