from datetime import date, datetime
from decimal import Decimal

import pytest

from copilot.schemas import (
    SGT,
    DocumentStatus,
    PaymentStatus,
    ScheduledPayment,
    TransactionSource,
)

BIZ = "biz-kopi"
OPS_BALANCE_SEP30 = Decimal("13358.15")  # 40,000 + 27,230 in - 53,871.85 out


def schedule(store, pid="sp1", amount="2880.00", bill_id="b-1250", pay_on=date(2026, 9, 30)):
    store.add_scheduled_payment(
        ScheduledPayment(
            id=pid,
            business_id=BIZ,
            payee_id="p-beans",
            from_account_id="a-ops",
            amount=amount,
            pay_on=pay_on,
            status=PaymentStatus.SCHEDULED,
            bill_id=bill_id,
            reference="BL-1250",
            created_at=datetime(2026, 9, 30, 10, 0, tzinfo=SGT),
        )
    )


# --- Clock and balances -----------------------------------------------------


def test_clock_defaults_to_latest_data_and_advances(sandbox):
    assert sandbox.today(BIZ) == date(2026, 9, 30)
    assert sandbox.advance(BIZ, 7) == date(2026, 10, 7)
    assert sandbox.today(BIZ) == date(2026, 10, 7)
    with pytest.raises(ValueError):
        sandbox.advance(BIZ, -1)


def test_balances(sandbox):
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE_SEP30
    assert sandbox.balance(BIZ, "a-ops", as_of=date(2026, 7, 1)) == Decimal("35500.00")
    assert sandbox.balances(BIZ) == {"a-ops": OPS_BALANCE_SEP30, "a-res": Decimal("12000.00")}


# --- Payments ---------------------------------------------------------------


def test_execute_payment(sandbox, store):
    schedule(store)
    result = sandbox.execute_payment(BIZ, "sp1")
    assert result.outcome == "executed"
    assert result.balance_after == OPS_BALANCE_SEP30 - Decimal("2880.00")
    assert sandbox.balance(BIZ, "a-ops") == result.balance_after

    txn = next(t for t in store.list_transactions(BIZ) if t.id == result.transaction_id)
    assert txn.source is TransactionSource.SANDBOX
    assert txn.amount == Decimal("-2880.00")
    assert "Highland Beans" in txn.description

    assert store.get_scheduled_payment(BIZ, "sp1").status is PaymentStatus.EXECUTED
    bill = store.get_document(BIZ, "bill", "b-1250")
    assert bill.status is DocumentStatus.PAID
    assert bill.amount_paid == Decimal("2880.00")


def test_payment_cannot_execute_twice(sandbox, store):
    schedule(store)
    assert sandbox.execute_payment(BIZ, "sp1").outcome == "executed"
    second = sandbox.execute_payment(BIZ, "sp1")
    assert second.outcome == "rejected"
    assert "executed" in second.reason
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE_SEP30 - Decimal("2880.00")


def test_insufficient_funds_blocks(sandbox, store):
    schedule(store, amount="50000.00", bill_id=None)
    result = sandbox.execute_payment(BIZ, "sp1")
    assert result.outcome == "blocked"
    assert result.reason == "insufficient funds"
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE_SEP30
    assert store.get_scheduled_payment(BIZ, "sp1").status is PaymentStatus.BLOCKED
    assert sandbox.events(BIZ)[-1].outcome == "blocked"


def test_unconfirmed_payment_is_rejected(sandbox, store):
    schedule(store)
    store.update_payment_status(BIZ, "sp1", PaymentStatus.PENDING_CONFIRMATION)
    assert sandbox.execute_payment(BIZ, "sp1").outcome == "rejected"


def test_future_payment_is_not_due(sandbox, store):
    schedule(store, pay_on=date(2026, 10, 20))
    result = sandbox.execute_payment(BIZ, "sp1")
    assert result.outcome == "rejected"
    assert "not due" in result.reason
    sandbox.advance(BIZ, 20)
    assert sandbox.execute_payment(BIZ, "sp1").outcome == "executed"


def test_payment_larger_than_bill_is_rejected(sandbox, store):
    schedule(store, amount="3000.00")
    assert sandbox.execute_payment(BIZ, "sp1").outcome == "rejected"


def test_unknown_payment_is_rejected(sandbox):
    assert sandbox.execute_payment(BIZ, "nope").reason == "payment not found"


# --- Receipts ---------------------------------------------------------------


def test_invoice_receipt(sandbox, store):
    result = sandbox.record_invoice_receipt(BIZ, "i-0104", Decimal("7020.00"), "a-ops")
    assert result.outcome == "executed"
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE_SEP30 + Decimal("7020.00")
    assert store.get_document(BIZ, "invoice", "i-0104").status is DocumentStatus.PAID


def test_partial_then_overpayment(sandbox, store):
    assert sandbox.record_invoice_receipt(BIZ, "i-0098", Decimal("1000"), "a-ops").outcome == (
        "executed"
    )
    invoice = store.get_document(BIZ, "invoice", "i-0098")
    assert invoice.status is DocumentStatus.OPEN and invoice.amount_paid == Decimal("1000")
    over = sandbox.record_invoice_receipt(BIZ, "i-0098", Decimal("900"), "a-ops")
    assert over.outcome == "rejected"


@pytest.mark.parametrize("amount", ["0", "-5", "10.001"])
def test_bad_receipt_amounts(sandbox, amount):
    result = sandbox.record_invoice_receipt(BIZ, "i-0104", Decimal(amount), "a-ops")
    assert result.outcome == "rejected"


def test_receipt_on_paid_invoice_is_rejected(sandbox):
    assert sandbox.record_invoice_receipt(BIZ, "i-0103", Decimal("1"), "a-ops").outcome == (
        "rejected"
    )


# --- Event log --------------------------------------------------------------


def test_every_attempt_is_logged(sandbox, store):
    schedule(store)
    sandbox.execute_payment(BIZ, "sp1")
    sandbox.execute_payment(BIZ, "sp1")
    sandbox.execute_payment(BIZ, "nope")
    sandbox.record_invoice_receipt(BIZ, "i-0104", Decimal("100"), "a-ops")
    events = sandbox.events(BIZ)
    assert [(e.action, e.outcome) for e in events] == [
        ("execute_payment", "executed"),
        ("execute_payment", "rejected"),
        ("execute_payment", "rejected"),
        ("record_invoice_receipt", "executed"),
    ]
    assert events[0].amount == Decimal("2880.00")
    assert events[0].sim_date == date(2026, 9, 30)
    assert events[0].logged_at.utcoffset().total_seconds() == 8 * 3600
