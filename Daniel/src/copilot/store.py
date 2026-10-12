"""SQLite repository for all business data.

Rules enforced here (CLAUDE.md non-negotiable rule 3 and Conventions):
- Every method takes business_id as its first argument and every query filters on it.
  There is no method that reads across businesses.
- Tables use (business_id, id) primary keys, and foreign keys include business_id, so a
  row can't reference another business's account, counterparty, payee or bill.
- Money is stored as INTEGER cents. to_cents / from_cents are the only conversion points.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from copilot.schemas import (
    Account,
    Adjustment,
    ApplicationStatus,
    Bill,
    Business,
    Counterparty,
    DocumentStatus,
    FinancingApplication,
    FixedAsset,
    ForecastAssumption,
    ImportResult,
    InventorySnapshot,
    Invoice,
    Loan,
    LoanInstalment,
    OpeningBalance,
    Payee,
    PaymentStatus,
    PayrollRun,
    Reminder,
    ScheduledPayment,
    Transaction,
    TransactionCategory,
)

DocumentKind = Literal["invoice", "bill"]
_DOC_TABLES: dict[str, str] = {"invoice": "invoices", "bill": "bills"}
_DOC_MODELS: dict[str, type[Invoice] | type[Bill]] = {"invoice": Invoice, "bill": Bill}


class NotFoundError(LookupError):
    """No record with that id exists for that business."""


def to_cents(amount: Decimal) -> int:
    scaled = amount * 100
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{amount} has more than 2 decimal places")
    return int(scaled)


def from_cents(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    uen TEXT NOT NULL,
    industry TEXT NOT NULL,
    incorporated_on TEXT NOT NULL,
    employee_count INTEGER NOT NULL,
    local_shareholding_pct TEXT NOT NULL,
    registered_in_sg INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    currency TEXT NOT NULL,
    opening_balance_cents INTEGER NOT NULL,
    opening_date TEXT NOT NULL,
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS counterparties (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    payment_terms_days INTEGER NOT NULL,
    default_category TEXT,
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS payees (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    account_number TEXT NOT NULL,
    bank_name TEXT NOT NULL,
    allowlisted INTEGER NOT NULL,
    verified INTEGER NOT NULL,
    details_changed_at TEXT,
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS transactions (
    business_id TEXT NOT NULL,
    id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT NOT NULL,
    counterparty_id TEXT,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, account_id) REFERENCES accounts(business_id, id),
    FOREIGN KEY (business_id, counterparty_id) REFERENCES counterparties(business_id, id)
);
CREATE INDEX IF NOT EXISTS transactions_by_date ON transactions(business_id, date);
CREATE TABLE IF NOT EXISTS invoices (
    business_id TEXT NOT NULL,
    id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    amount_paid_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    gst_cents INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, counterparty_id) REFERENCES counterparties(business_id, id)
);
CREATE TABLE IF NOT EXISTS bills (
    business_id TEXT NOT NULL,
    id TEXT NOT NULL,
    counterparty_id TEXT NOT NULL,
    number TEXT NOT NULL,
    issue_date TEXT NOT NULL,
    due_date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    amount_paid_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    gst_cents INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, counterparty_id) REFERENCES counterparties(business_id, id)
);
CREATE TABLE IF NOT EXISTS scheduled_payments (
    business_id TEXT NOT NULL,
    id TEXT NOT NULL,
    payee_id TEXT NOT NULL,
    from_account_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    pay_on TEXT NOT NULL,
    status TEXT NOT NULL,
    bill_id TEXT,
    reference TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, payee_id) REFERENCES payees(business_id, id),
    FOREIGN KEY (business_id, from_account_id) REFERENCES accounts(business_id, id),
    FOREIGN KEY (business_id, bill_id) REFERENCES bills(business_id, id)
);
CREATE TABLE IF NOT EXISTS alert_rules (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    user_id TEXT NOT NULL,
    floor_cents INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (business_id, user_id)
);
CREATE TABLE IF NOT EXISTS financing_applications (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    need_amount_cents INTEGER NOT NULL CHECK (need_amount_cents > 0),
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    term_months INTEGER NOT NULL CHECK (term_months >= 1),
    draw_date TEXT NOT NULL,
    need_days INTEGER NOT NULL CHECK (need_days >= 1),
    need_months INTEGER NOT NULL CHECK (need_months >= 1),
    purpose TEXT NOT NULL,
    -- approval is the lender's decision: no other status can be stored
    status TEXT NOT NULL CHECK (status IN ('draft', 'submitted')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    submitted_by TEXT,
    submitted_at TEXT,
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS reminders (
    business_id TEXT NOT NULL,
    id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    tone TEXT NOT NULL CHECK (tone IN ('friendly', 'firm')),
    body TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'sent')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_by TEXT,
    sent_on TEXT,
    sent_at TEXT,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, invoice_id) REFERENCES invoices(business_id, id)
);
-- Which bank receipt paid (part of) which invoice. One receipt pays at most one invoice.
CREATE TABLE IF NOT EXISTS invoice_receipt_links (
    business_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    invoice_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    linked_by TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (business_id, transaction_id),
    FOREIGN KEY (business_id, transaction_id) REFERENCES transactions(business_id, id),
    FOREIGN KEY (business_id, invoice_id) REFERENCES invoices(business_id, id)
);
-- Accrual inputs (chunk 11): read-only after import.
CREATE TABLE IF NOT EXISTS opening_balances (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    line TEXT NOT NULL,
    as_of TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    PRIMARY KEY (business_id, line)
);
CREATE TABLE IF NOT EXISTS inventory_snapshots (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    date TEXT NOT NULL,
    value_cents INTEGER NOT NULL CHECK (value_cents >= 0),
    PRIMARY KEY (business_id, date)
);
CREATE TABLE IF NOT EXISTS fixed_assets (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    name TEXT NOT NULL,
    acquired_on TEXT NOT NULL,
    cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
    residual_value_cents INTEGER NOT NULL CHECK (residual_value_cents >= 0),
    useful_life_months INTEGER NOT NULL CHECK (useful_life_months >= 1),
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS loans (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    lender TEXT NOT NULL,
    principal_cents INTEGER NOT NULL CHECK (principal_cents > 0),
    annual_rate_pct TEXT NOT NULL,
    start_date TEXT NOT NULL,
    term_months INTEGER NOT NULL CHECK (term_months >= 1),
    instalment_cents INTEGER NOT NULL CHECK (instalment_cents > 0),
    PRIMARY KEY (business_id, id)
);
CREATE TABLE IF NOT EXISTS loan_schedule (
    business_id TEXT NOT NULL,
    loan_id TEXT NOT NULL,
    instalment_no INTEGER NOT NULL CHECK (instalment_no >= 1),
    due_date TEXT NOT NULL,
    instalment_cents INTEGER NOT NULL,
    interest_cents INTEGER NOT NULL,
    principal_cents INTEGER NOT NULL,
    balance_after_cents INTEGER NOT NULL,
    PRIMARY KEY (business_id, loan_id, instalment_no),
    FOREIGN KEY (business_id, loan_id) REFERENCES loans(business_id, id)
);
CREATE TABLE IF NOT EXISTS payroll_runs (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    period TEXT NOT NULL,
    gross_pay_cents INTEGER NOT NULL,
    employee_cpf_cents INTEGER NOT NULL,
    employer_cpf_cents INTEGER NOT NULL,
    net_pay_cents INTEGER NOT NULL,
    pay_date TEXT NOT NULL,
    cpf_due_date TEXT NOT NULL,
    PRIMARY KEY (business_id, period)
);
-- Owner edits (chunk 13): kept beside the imported data, never deleted; undo changes status.
CREATE TABLE IF NOT EXISTS adjustments (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('accrued_cost', 'relabel', 'stock_count')),
    month TEXT NOT NULL,
    amount_cents INTEGER,
    line TEXT,
    transaction_id TEXT,
    to_category TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'applied', 'undone')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    applied_by TEXT,
    applied_at TEXT,
    undone_by TEXT,
    undone_at TEXT,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, transaction_id) REFERENCES transactions(business_id, id)
);
CREATE TABLE IF NOT EXISTS forecast_assumptions (
    business_id TEXT NOT NULL REFERENCES businesses(id),
    id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('payment_delay', 'recurring_change')),
    counterparty_id TEXT,
    days INTEGER,
    category TEXT,
    amount_cents INTEGER,
    start TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'removed')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    removed_by TEXT,
    removed_at TEXT,
    PRIMARY KEY (business_id, id),
    FOREIGN KEY (business_id, counterparty_id) REFERENCES counterparties(business_id, id)
);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:", any_thread: bool = False) -> None:
        """any_thread=True lets one session's store be used from successive threads (Streamlit
        runs each rerun on a new thread). Never share one Store between concurrent users."""
        # isolation_level=None: autocommit per statement; multi-step work uses transaction().
        self.conn = sqlite3.connect(
            str(path), isolation_level=None, check_same_thread=not any_thread
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self._depth = 0

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """All statements inside succeed together or not at all. Safe to nest."""
        outermost = self._depth == 0
        if outermost:
            self.conn.execute("BEGIN")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if outermost:
                self.conn.execute("ROLLBACK")
            raise
        self._depth -= 1
        if outermost:
            self.conn.execute("COMMIT")

    # --- Import ---------------------------------------------------------------

    def save_import(self, result: ImportResult) -> None:
        with self.transaction():
            self.add_business(result.business)
            for account in result.accounts:
                self.add_account(account)
            for counterparty in result.counterparties:
                self.add_counterparty(counterparty)
            for payee in result.payees:
                self.add_payee(payee)
            for txn in result.transactions:
                self.add_transaction(txn)
            for invoice in result.invoices:
                self.add_document("invoice", invoice)
            for bill in result.bills:
                self.add_document("bill", bill)
            for line in result.opening_balances:
                self.add_opening_balance(line)
            for snapshot in result.inventory_snapshots:
                self.add_inventory_snapshot(snapshot)
            for asset in result.fixed_assets:
                self.add_fixed_asset(asset)
            for loan in result.loans:
                self.add_loan(loan)
            for instalment in result.loan_schedule:
                self.add_loan_instalment(instalment)
            for run in result.payroll_runs:
                self.add_payroll_run(run)

    # --- Businesses -----------------------------------------------------------

    def add_business(self, business: Business) -> None:
        self.conn.execute(
            "INSERT INTO businesses VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                business.id,
                business.name,
                business.uen,
                business.industry,
                business.incorporated_on.isoformat(),
                business.employee_count,
                str(business.local_shareholding_pct),
                int(business.registered_in_sg),
            ),
        )

    def get_business(self, business_id: str) -> Business:
        row = self._one("SELECT * FROM businesses WHERE id = ?", (business_id,), business_id)
        return Business(
            id=row["id"],
            name=row["name"],
            uen=row["uen"],
            industry=row["industry"],
            incorporated_on=date.fromisoformat(row["incorporated_on"]),
            employee_count=row["employee_count"],
            local_shareholding_pct=Decimal(row["local_shareholding_pct"]),
            registered_in_sg=bool(row["registered_in_sg"]),
        )

    # --- Accounts, counterparties, payees ---------------------------------------

    def add_account(self, account: Account) -> None:
        self.conn.execute(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                account.business_id,
                account.id,
                account.name,
                account.bank_name,
                account.account_number.get_secret_value(),
                account.currency,
                to_cents(account.opening_balance),
                account.opening_date.isoformat(),
            ),
        )

    def list_accounts(self, business_id: str) -> list[Account]:
        rows = self.conn.execute(
            "SELECT * FROM accounts WHERE business_id = ? ORDER BY id", (business_id,)
        )
        return [self._account(r) for r in rows]

    def get_account(self, business_id: str, account_id: str) -> Account:
        row = self._one(
            "SELECT * FROM accounts WHERE business_id = ? AND id = ?",
            (business_id, account_id),
            account_id,
        )
        return self._account(row)

    def add_counterparty(self, counterparty: Counterparty) -> None:
        self.conn.execute(
            "INSERT INTO counterparties VALUES (?, ?, ?, ?, ?, ?)",
            (
                counterparty.business_id,
                counterparty.id,
                counterparty.name,
                counterparty.kind.value,
                counterparty.payment_terms_days,
                counterparty.default_category.value if counterparty.default_category else None,
            ),
        )

    def set_counterparty_category(
        self, business_id: str, counterparty_id: str, category: TransactionCategory | None
    ) -> None:
        """Set (or clear) the category every transaction with this counterparty defaults to."""
        cursor = self.conn.execute(
            "UPDATE counterparties SET default_category = ? WHERE business_id = ? AND id = ?",
            (category.value if category else None, business_id, counterparty_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(counterparty_id)

    def list_counterparties(self, business_id: str) -> list[Counterparty]:
        rows = self.conn.execute(
            "SELECT * FROM counterparties WHERE business_id = ? ORDER BY id", (business_id,)
        )
        return [Counterparty(**dict(r)) for r in rows]

    def add_payee(self, payee: Payee) -> None:
        self.conn.execute(
            "INSERT INTO payees VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payee.business_id,
                payee.id,
                payee.name,
                payee.account_number.get_secret_value(),
                payee.bank_name,
                int(payee.allowlisted),
                int(payee.verified),
                payee.details_changed_at.isoformat() if payee.details_changed_at else None,
            ),
        )

    def list_payees(self, business_id: str) -> list[Payee]:
        rows = self.conn.execute(
            "SELECT * FROM payees WHERE business_id = ? ORDER BY id", (business_id,)
        )
        return [self._payee(r) for r in rows]

    def get_payee(self, business_id: str, payee_id: str) -> Payee:
        row = self._one(
            "SELECT * FROM payees WHERE business_id = ? AND id = ?",
            (business_id, payee_id),
            payee_id,
        )
        return self._payee(row)

    # --- Transactions ---------------------------------------------------------

    def add_transaction(self, txn: Transaction) -> None:
        self.conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                txn.business_id,
                txn.id,
                txn.account_id,
                txn.date.isoformat(),
                to_cents(txn.amount),
                txn.description,
                txn.counterparty_id,
                txn.category.value,
                txn.source.value,
            ),
        )

    def list_transactions(
        self,
        business_id: str,
        start: date | None = None,
        end: date | None = None,
        account_id: str | None = None,
    ) -> list[Transaction]:
        """Transactions for one business, optionally within [start, end] and one account."""
        sql = "SELECT * FROM transactions WHERE business_id = ?"
        params: list[str] = [business_id]
        if start is not None:
            sql += " AND date >= ?"
            params.append(start.isoformat())
        if end is not None:
            sql += " AND date <= ?"
            params.append(end.isoformat())
        if account_id is not None:
            sql += " AND account_id = ?"
            params.append(account_id)
        sql += " ORDER BY date, id"
        return [self._transaction(r) for r in self.conn.execute(sql, params)]

    def update_categories(
        self, business_id: str, categories: dict[str, TransactionCategory]
    ) -> None:
        """Set the category of several transactions at once (all or nothing)."""
        with self.transaction():
            for txn_id, category in categories.items():
                cursor = self.conn.execute(
                    "UPDATE transactions SET category = ? WHERE business_id = ? AND id = ?",
                    (category.value, business_id, txn_id),
                )
                if cursor.rowcount == 0:
                    raise NotFoundError(txn_id)

    def sum_transactions(self, business_id: str, account_id: str, as_of: date) -> Decimal:
        """Net of all transactions on one account up to and including as_of."""
        (cents,) = self.conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions "
            "WHERE business_id = ? AND account_id = ? AND date <= ?",
            (business_id, account_id, as_of.isoformat()),
        ).fetchone()
        return from_cents(cents)

    def get_transaction(self, business_id: str, txn_id: str) -> Transaction:
        row = self._one(
            "SELECT * FROM transactions WHERE business_id = ? AND id = ?",
            (business_id, txn_id),
            txn_id,
        )
        return self._transaction(row)

    def has_transaction(self, business_id: str, txn_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM transactions WHERE business_id = ? AND id = ?", (business_id, txn_id)
        ).fetchone()
        return row is not None

    def latest_transaction_date(self, business_id: str) -> date | None:
        (latest,) = self.conn.execute(
            "SELECT MAX(date) FROM transactions WHERE business_id = ?", (business_id,)
        ).fetchone()
        return date.fromisoformat(latest) if latest else None

    # --- Invoices and bills ---------------------------------------------------

    def add_document(self, kind: DocumentKind, doc: Invoice | Bill) -> None:
        self.conn.execute(
            f"INSERT INTO {_DOC_TABLES[kind]} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                doc.business_id,
                doc.id,
                doc.counterparty_id,
                doc.number,
                doc.issue_date.isoformat(),
                doc.due_date.isoformat(),
                to_cents(doc.amount),
                to_cents(doc.amount_paid),
                doc.status.value,
                doc.notes,
                to_cents(doc.gst),
            ),
        )

    def list_invoices(
        self, business_id: str, status: DocumentStatus | None = None
    ) -> list[Invoice]:
        return self._list_documents("invoice", business_id, status)  # type: ignore[return-value]

    def list_bills(self, business_id: str, status: DocumentStatus | None = None) -> list[Bill]:
        return self._list_documents("bill", business_id, status)  # type: ignore[return-value]

    def get_document(self, business_id: str, kind: DocumentKind, doc_id: str) -> Invoice | Bill:
        row = self._one(
            f"SELECT * FROM {_DOC_TABLES[kind]} WHERE business_id = ? AND id = ?",
            (business_id, doc_id),
            doc_id,
        )
        return self._document(kind, row)

    def update_document(
        self,
        business_id: str,
        kind: DocumentKind,
        doc_id: str,
        amount_paid: Decimal,
        status: DocumentStatus,
    ) -> None:
        current = self.get_document(business_id, kind, doc_id)
        # Re-validate the new state through the model before writing it.
        current.model_validate(
            {**current.model_dump(), "amount_paid": amount_paid, "status": status}
        )
        self.conn.execute(
            f"UPDATE {_DOC_TABLES[kind]} SET amount_paid_cents = ?, status = ? "
            "WHERE business_id = ? AND id = ?",
            (to_cents(amount_paid), status.value, business_id, doc_id),
        )

    def link_receipt(
        self,
        business_id: str,
        transaction_id: str,
        invoice_id: str,
        amount: Decimal,
        linked_by: str,
        linked_at: datetime,
    ) -> None:
        """Record that a bank receipt paid (part of) an invoice. A receipt links only once."""
        self.conn.execute(
            "INSERT INTO invoice_receipt_links VALUES (?, ?, ?, ?, ?, ?)",
            (
                business_id,
                transaction_id,
                invoice_id,
                to_cents(amount),
                linked_by,
                linked_at.isoformat(),
            ),
        )

    def receipt_links(self, business_id: str) -> dict[str, str]:
        """transaction id -> invoice id, for every receipt already linked to an invoice."""
        rows = self.conn.execute(
            "SELECT transaction_id, invoice_id FROM invoice_receipt_links WHERE business_id = ?",
            (business_id,),
        )
        return {r["transaction_id"]: r["invoice_id"] for r in rows}

    # --- Scheduled payments ---------------------------------------------------

    def add_scheduled_payment(self, payment: ScheduledPayment) -> None:
        self.conn.execute(
            "INSERT INTO scheduled_payments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                payment.business_id,
                payment.id,
                payment.payee_id,
                payment.from_account_id,
                to_cents(payment.amount),
                payment.pay_on.isoformat(),
                payment.status.value,
                payment.bill_id,
                payment.reference,
                payment.created_at.isoformat(),
            ),
        )

    def get_scheduled_payment(self, business_id: str, payment_id: str) -> ScheduledPayment:
        row = self._one(
            "SELECT * FROM scheduled_payments WHERE business_id = ? AND id = ?",
            (business_id, payment_id),
            payment_id,
        )
        return self._scheduled_payment(row)

    def list_scheduled_payments(
        self,
        business_id: str,
        statuses: tuple[PaymentStatus, ...] | None = None,
        pay_on: date | None = None,
        bill_id: str | None = None,
    ) -> list[ScheduledPayment]:
        sql = "SELECT * FROM scheduled_payments WHERE business_id = ?"
        params: list[str] = [business_id]
        if statuses is not None:
            sql += f" AND status IN ({', '.join('?' for _ in statuses)})"
            params += [s.value for s in statuses]
        if pay_on is not None:
            sql += " AND pay_on = ?"
            params.append(pay_on.isoformat())
        if bill_id is not None:
            sql += " AND bill_id = ?"
            params.append(bill_id)
        sql += " ORDER BY pay_on, id"
        return [self._scheduled_payment(r) for r in self.conn.execute(sql, params)]

    @staticmethod
    def _scheduled_payment(row: sqlite3.Row) -> ScheduledPayment:
        return ScheduledPayment(
            business_id=row["business_id"],
            id=row["id"],
            payee_id=row["payee_id"],
            from_account_id=row["from_account_id"],
            amount=from_cents(row["amount_cents"]),
            pay_on=date.fromisoformat(row["pay_on"]),
            status=PaymentStatus(row["status"]),
            bill_id=row["bill_id"],
            reference=row["reference"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_payment_status(
        self, business_id: str, payment_id: str, status: PaymentStatus
    ) -> None:
        cursor = self.conn.execute(
            "UPDATE scheduled_payments SET status = ? WHERE business_id = ? AND id = ?",
            (status.value, business_id, payment_id),
        )
        if cursor.rowcount == 0:
            raise NotFoundError(payment_id)

    # --- Personal alert rules ---------------------------------------------------

    def set_alert_floor(
        self, business_id: str, user_id: str, floor: Decimal, updated_at: datetime
    ) -> None:
        self.conn.execute(
            "INSERT INTO alert_rules VALUES (?, ?, ?, ?) ON CONFLICT(business_id, user_id) "
            "DO UPDATE SET floor_cents = excluded.floor_cents, updated_at = excluded.updated_at",
            (business_id, user_id, to_cents(floor), updated_at.isoformat()),
        )

    def get_alert_floor(self, business_id: str, user_id: str) -> Decimal | None:
        row = self.conn.execute(
            "SELECT floor_cents FROM alert_rules WHERE business_id = ? AND user_id = ?",
            (business_id, user_id),
        ).fetchone()
        return from_cents(row["floor_cents"]) if row is not None else None

    # --- Financing applications -----------------------------------------------

    def add_application(self, app: FinancingApplication) -> None:
        self.conn.execute(
            f"INSERT INTO financing_applications VALUES ({', '.join('?' * 15)})",
            (
                app.business_id,
                app.id,
                app.product_id,
                to_cents(app.need_amount),
                to_cents(app.amount),
                app.term_months,
                app.draw_date.isoformat(),
                app.need_days,
                app.need_months,
                app.purpose,
                app.status.value,
                app.created_by,
                app.created_at.isoformat(),
                app.submitted_by,
                app.submitted_at.isoformat() if app.submitted_at else None,
            ),
        )

    def get_application(self, business_id: str, application_id: str) -> FinancingApplication:
        row = self._one(
            "SELECT * FROM financing_applications WHERE business_id = ? AND id = ?",
            (business_id, application_id),
            application_id,
        )
        return self._application(row)

    def list_applications(self, business_id: str) -> list[FinancingApplication]:
        rows = self.conn.execute(
            "SELECT * FROM financing_applications WHERE business_id = ? ORDER BY created_at, id",
            (business_id,),
        ).fetchall()
        return [self._application(r) for r in rows]

    def mark_application_submitted(
        self, business_id: str, application_id: str, user_id: str, at: datetime
    ) -> None:
        cur = self.conn.execute(
            "UPDATE financing_applications SET status = 'submitted', submitted_by = ?, "
            "submitted_at = ? WHERE business_id = ? AND id = ? AND status = 'draft'",
            (user_id, at.isoformat(), business_id, application_id),
        )
        if cur.rowcount != 1:
            raise NotFoundError(f"draft application {application_id}")

    # --- Payment reminders -----------------------------------------------------

    def add_reminder(self, reminder: Reminder) -> None:
        self.conn.execute(
            "INSERT INTO reminders VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)",
            (
                reminder.business_id,
                reminder.id,
                reminder.invoice_id,
                reminder.tone,
                reminder.body,
                reminder.status,
                reminder.created_by,
                reminder.created_at.isoformat(),
            ),
        )

    def get_reminder(self, business_id: str, reminder_id: str) -> Reminder:
        row = self._one(
            "SELECT * FROM reminders WHERE business_id = ? AND id = ?",
            (business_id, reminder_id),
            reminder_id,
        )
        return self._reminder(row)

    def list_reminders(self, business_id: str, invoice_id: str | None = None) -> list[Reminder]:
        sql = "SELECT * FROM reminders WHERE business_id = ?"
        params = [business_id]
        if invoice_id is not None:
            sql += " AND invoice_id = ?"
            params.append(invoice_id)
        rows = self.conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
        return [self._reminder(r) for r in rows]

    def mark_reminder_sent(
        self, business_id: str, reminder_id: str, user_id: str, sent_on: date, at: datetime
    ) -> None:
        cur = self.conn.execute(
            "UPDATE reminders SET status = 'sent', sent_by = ?, sent_on = ?, sent_at = ? "
            "WHERE business_id = ? AND id = ? AND status = 'draft'",
            (user_id, sent_on.isoformat(), at.isoformat(), business_id, reminder_id),
        )
        if cur.rowcount != 1:
            raise NotFoundError(f"draft reminder {reminder_id}")

    # --- Adjustments and saved assumptions (chunk 13) ---------------------------

    def add_adjustment(self, adj: Adjustment) -> None:
        self.conn.execute(
            "INSERT INTO adjustments VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)",
            (
                adj.business_id,
                adj.id,
                adj.kind,
                adj.month,
                to_cents(adj.amount) if adj.amount is not None else None,
                adj.line.value if adj.line else None,
                adj.transaction_id,
                adj.to_category.value if adj.to_category else None,
                adj.reason,
                adj.status,
                adj.created_by,
                adj.created_at.isoformat(),
            ),
        )

    def get_adjustment(self, business_id: str, adjustment_id: str) -> Adjustment:
        row = self._one(
            "SELECT * FROM adjustments WHERE business_id = ? AND id = ?",
            (business_id, adjustment_id),
            adjustment_id,
        )
        return self._adjustment(row)

    def list_adjustments(self, business_id: str, status: str | None = None) -> list[Adjustment]:
        sql = "SELECT * FROM adjustments WHERE business_id = ?"
        params = [business_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
        return [self._adjustment(r) for r in rows]

    def set_adjustment_status(
        self,
        business_id: str,
        adjustment_id: str,
        status: Literal["applied", "undone"],
        user_id: str,
        at: datetime,
    ) -> None:
        before = "draft" if status == "applied" else "applied"
        column = "applied" if status == "applied" else "undone"
        cur = self.conn.execute(
            f"UPDATE adjustments SET status = ?, {column}_by = ?, {column}_at = ? "
            "WHERE business_id = ? AND id = ? AND status = ?",
            (status, user_id, at.isoformat(), business_id, adjustment_id, before),
        )
        if cur.rowcount != 1:
            raise NotFoundError(f"{before} adjustment {adjustment_id}")

    def add_assumption(self, a: ForecastAssumption) -> None:
        self.conn.execute(
            "INSERT INTO forecast_assumptions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)",
            (
                a.business_id,
                a.id,
                a.kind,
                a.counterparty_id,
                a.days,
                a.category.value if a.category else None,
                to_cents(a.amount) if a.amount is not None else None,
                a.start.isoformat() if a.start else None,
                a.reason,
                a.status,
                a.created_by,
                a.created_at.isoformat(),
            ),
        )

    def get_assumption(self, business_id: str, assumption_id: str) -> ForecastAssumption:
        row = self._one(
            "SELECT * FROM forecast_assumptions WHERE business_id = ? AND id = ?",
            (business_id, assumption_id),
            assumption_id,
        )
        return self._assumption(row)

    def list_assumptions(
        self, business_id: str, status: str | None = None
    ) -> list[ForecastAssumption]:
        sql = "SELECT * FROM forecast_assumptions WHERE business_id = ?"
        params = [business_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        rows = self.conn.execute(sql + " ORDER BY created_at, id", params).fetchall()
        return [self._assumption(r) for r in rows]

    def remove_assumption(
        self, business_id: str, assumption_id: str, user_id: str, at: datetime
    ) -> None:
        cur = self.conn.execute(
            "UPDATE forecast_assumptions SET status = 'removed', removed_by = ?, removed_at = ? "
            "WHERE business_id = ? AND id = ? AND status = 'active'",
            (user_id, at.isoformat(), business_id, assumption_id),
        )
        if cur.rowcount != 1:
            raise NotFoundError(f"active assumption {assumption_id}")

    # --- Row mapping ----------------------------------------------------------

    @staticmethod
    def _adjustment(row: sqlite3.Row) -> Adjustment:
        def ts(name: str) -> datetime | None:
            return datetime.fromisoformat(row[name]) if row[name] else None

        return Adjustment(
            business_id=row["business_id"],
            id=row["id"],
            kind=row["kind"],
            month=row["month"],
            amount=from_cents(row["amount_cents"]) if row["amount_cents"] is not None else None,
            line=TransactionCategory(row["line"]) if row["line"] else None,
            transaction_id=row["transaction_id"],
            to_category=TransactionCategory(row["to_category"]) if row["to_category"] else None,
            reason=row["reason"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_by=row["applied_by"],
            applied_at=ts("applied_at"),
            undone_by=row["undone_by"],
            undone_at=ts("undone_at"),
        )

    @staticmethod
    def _assumption(row: sqlite3.Row) -> ForecastAssumption:
        return ForecastAssumption(
            business_id=row["business_id"],
            id=row["id"],
            kind=row["kind"],
            counterparty_id=row["counterparty_id"],
            days=row["days"],
            category=TransactionCategory(row["category"]) if row["category"] else None,
            amount=from_cents(row["amount_cents"]) if row["amount_cents"] is not None else None,
            start=date.fromisoformat(row["start"]) if row["start"] else None,
            reason=row["reason"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            removed_by=row["removed_by"],
            removed_at=datetime.fromisoformat(row["removed_at"]) if row["removed_at"] else None,
        )

    @staticmethod
    def _reminder(row: sqlite3.Row) -> Reminder:
        return Reminder(
            business_id=row["business_id"],
            id=row["id"],
            invoice_id=row["invoice_id"],
            tone=row["tone"],
            body=row["body"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            sent_by=row["sent_by"],
            sent_on=date.fromisoformat(row["sent_on"]) if row["sent_on"] else None,
            sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
        )

    @staticmethod
    def _application(row: sqlite3.Row) -> FinancingApplication:
        return FinancingApplication(
            business_id=row["business_id"],
            id=row["id"],
            product_id=row["product_id"],
            need_amount=from_cents(row["need_amount_cents"]),
            amount=from_cents(row["amount_cents"]),
            term_months=row["term_months"],
            draw_date=date.fromisoformat(row["draw_date"]),
            need_days=row["need_days"],
            need_months=row["need_months"],
            purpose=row["purpose"],
            status=ApplicationStatus(row["status"]),
            created_by=row["created_by"],
            created_at=datetime.fromisoformat(row["created_at"]),
            submitted_by=row["submitted_by"],
            submitted_at=(
                datetime.fromisoformat(row["submitted_at"]) if row["submitted_at"] else None
            ),
        )

    # --- Accrual inputs (chunk 11): written once by save_import, then read-only -------

    def add_opening_balance(self, line: OpeningBalance) -> None:
        self.conn.execute(
            "INSERT INTO opening_balances VALUES (?, ?, ?, ?)",
            (line.business_id, line.line.value, line.as_of.isoformat(), to_cents(line.amount)),
        )

    def list_opening_balances(self, business_id: str) -> list[OpeningBalance]:
        rows = self.conn.execute(
            "SELECT * FROM opening_balances WHERE business_id = ? ORDER BY rowid", (business_id,)
        )
        return [
            OpeningBalance(
                business_id=r["business_id"],
                as_of=date.fromisoformat(r["as_of"]),
                line=r["line"],
                amount=from_cents(r["amount_cents"]),
            )
            for r in rows
        ]

    def add_inventory_snapshot(self, snapshot: InventorySnapshot) -> None:
        self.conn.execute(
            "INSERT INTO inventory_snapshots VALUES (?, ?, ?)",
            (snapshot.business_id, snapshot.date.isoformat(), to_cents(snapshot.value)),
        )

    def list_inventory_snapshots(self, business_id: str) -> list[InventorySnapshot]:
        rows = self.conn.execute(
            "SELECT * FROM inventory_snapshots WHERE business_id = ? ORDER BY date",
            (business_id,),
        )
        return [
            InventorySnapshot(
                business_id=r["business_id"],
                date=date.fromisoformat(r["date"]),
                value=from_cents(r["value_cents"]),
            )
            for r in rows
        ]

    def add_fixed_asset(self, asset: FixedAsset) -> None:
        self.conn.execute(
            "INSERT INTO fixed_assets VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                asset.business_id,
                asset.id,
                asset.name,
                asset.acquired_on.isoformat(),
                to_cents(asset.cost),
                to_cents(asset.residual_value),
                asset.useful_life_months,
            ),
        )

    def list_fixed_assets(self, business_id: str) -> list[FixedAsset]:
        rows = self.conn.execute(
            "SELECT * FROM fixed_assets WHERE business_id = ? ORDER BY acquired_on, id",
            (business_id,),
        )
        return [
            FixedAsset(
                business_id=r["business_id"],
                id=r["id"],
                name=r["name"],
                acquired_on=date.fromisoformat(r["acquired_on"]),
                cost=from_cents(r["cost_cents"]),
                residual_value=from_cents(r["residual_value_cents"]),
                useful_life_months=r["useful_life_months"],
            )
            for r in rows
        ]

    def add_loan(self, loan: Loan) -> None:
        self.conn.execute(
            "INSERT INTO loans VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                loan.business_id,
                loan.id,
                loan.lender,
                to_cents(loan.principal),
                str(loan.annual_rate_pct),
                loan.start_date.isoformat(),
                loan.term_months,
                to_cents(loan.instalment),
            ),
        )

    def list_loans(self, business_id: str) -> list[Loan]:
        rows = self.conn.execute(
            "SELECT * FROM loans WHERE business_id = ? ORDER BY start_date, id", (business_id,)
        )
        return [
            Loan(
                business_id=r["business_id"],
                id=r["id"],
                lender=r["lender"],
                principal=from_cents(r["principal_cents"]),
                annual_rate_pct=Decimal(r["annual_rate_pct"]),
                start_date=date.fromisoformat(r["start_date"]),
                term_months=r["term_months"],
                instalment=from_cents(r["instalment_cents"]),
            )
            for r in rows
        ]

    def add_loan_instalment(self, row: LoanInstalment) -> None:
        self.conn.execute(
            "INSERT INTO loan_schedule VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.business_id,
                row.loan_id,
                row.instalment_no,
                row.due_date.isoformat(),
                to_cents(row.instalment),
                to_cents(row.interest),
                to_cents(row.principal),
                to_cents(row.balance_after),
            ),
        )

    def list_loan_schedule(
        self, business_id: str, loan_id: str | None = None
    ) -> list[LoanInstalment]:
        sql = "SELECT * FROM loan_schedule WHERE business_id = ?"
        params: list[str] = [business_id]
        if loan_id is not None:
            sql += " AND loan_id = ?"
            params.append(loan_id)
        sql += " ORDER BY loan_id, instalment_no"
        return [
            LoanInstalment(
                business_id=r["business_id"],
                loan_id=r["loan_id"],
                instalment_no=r["instalment_no"],
                due_date=date.fromisoformat(r["due_date"]),
                instalment=from_cents(r["instalment_cents"]),
                interest=from_cents(r["interest_cents"]),
                principal=from_cents(r["principal_cents"]),
                balance_after=from_cents(r["balance_after_cents"]),
            )
            for r in self.conn.execute(sql, params)
        ]

    def add_payroll_run(self, run: PayrollRun) -> None:
        self.conn.execute(
            "INSERT INTO payroll_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run.business_id,
                run.period,
                to_cents(run.gross_pay),
                to_cents(run.employee_cpf),
                to_cents(run.employer_cpf),
                to_cents(run.net_pay),
                run.pay_date.isoformat(),
                run.cpf_due_date.isoformat(),
            ),
        )

    def list_payroll_runs(self, business_id: str) -> list[PayrollRun]:
        rows = self.conn.execute(
            "SELECT * FROM payroll_runs WHERE business_id = ? ORDER BY period", (business_id,)
        )
        return [
            PayrollRun(
                business_id=r["business_id"],
                period=r["period"],
                gross_pay=from_cents(r["gross_pay_cents"]),
                employee_cpf=from_cents(r["employee_cpf_cents"]),
                employer_cpf=from_cents(r["employer_cpf_cents"]),
                net_pay=from_cents(r["net_pay_cents"]),
                pay_date=date.fromisoformat(r["pay_date"]),
                cpf_due_date=date.fromisoformat(r["cpf_due_date"]),
            )
            for r in rows
        ]

    def _one(self, sql: str, params: tuple, what: str) -> sqlite3.Row:
        row = self.conn.execute(sql, params).fetchone()
        if row is None:
            raise NotFoundError(what)
        return row

    @staticmethod
    def _account(row: sqlite3.Row) -> Account:
        return Account(
            business_id=row["business_id"],
            id=row["id"],
            name=row["name"],
            bank_name=row["bank_name"],
            account_number=row["account_number"],
            currency=row["currency"],
            opening_balance=from_cents(row["opening_balance_cents"]),
            opening_date=date.fromisoformat(row["opening_date"]),
        )

    @staticmethod
    def _payee(row: sqlite3.Row) -> Payee:
        changed = row["details_changed_at"]
        return Payee(
            business_id=row["business_id"],
            id=row["id"],
            name=row["name"],
            account_number=row["account_number"],
            bank_name=row["bank_name"],
            allowlisted=bool(row["allowlisted"]),
            verified=bool(row["verified"]),
            details_changed_at=datetime.fromisoformat(changed) if changed else None,
        )

    @staticmethod
    def _transaction(row: sqlite3.Row) -> Transaction:
        return Transaction(
            business_id=row["business_id"],
            id=row["id"],
            account_id=row["account_id"],
            date=date.fromisoformat(row["date"]),
            amount=from_cents(row["amount_cents"]),
            description=row["description"],
            counterparty_id=row["counterparty_id"],
            category=row["category"],
            source=row["source"],
        )

    def _list_documents(
        self, kind: DocumentKind, business_id: str, status: DocumentStatus | None
    ) -> list[Invoice | Bill]:
        sql = f"SELECT * FROM {_DOC_TABLES[kind]} WHERE business_id = ?"
        params: list[str] = [business_id]
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        sql += " ORDER BY due_date, id"
        return [self._document(kind, r) for r in self.conn.execute(sql, params)]

    @staticmethod
    def _document(kind: DocumentKind, row: sqlite3.Row) -> Invoice | Bill:
        return _DOC_MODELS[kind](
            business_id=row["business_id"],
            id=row["id"],
            counterparty_id=row["counterparty_id"],
            number=row["number"],
            issue_date=date.fromisoformat(row["issue_date"]),
            due_date=date.fromisoformat(row["due_date"]),
            amount=from_cents(row["amount_cents"]),
            amount_paid=from_cents(row["amount_paid_cents"]),
            status=DocumentStatus(row["status"]),
            notes=row["notes"],
            gst=from_cents(row["gst_cents"]),
        )
