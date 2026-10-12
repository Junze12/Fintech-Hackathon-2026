"""Policy guards and limits, on the sample business (today = 2026-09-30)."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from copilot.ingest import ingest_folder
from copilot.policy.guards import (
    check_floor,
    check_payment,
    check_reminder,
    check_scheduled_execution,
)
from copilot.policy.limits import DEFAULT_PER_DAY, PolicyLimits, get_limits, set_limits
from copilot.policy.roles import TIERS, Actor, Role, has_role
from copilot.schemas import SGT, Payee, PaymentStatus, ScheduledPayment
from copilot.tools.write_tools import DraftReminderInput, SchedulePaymentInput, SetCashFloorInput

BIZ = "biz-kopi"
TODAY = date(2026, 9, 30)
CASH_CRUNCH = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "cash_crunch"


def pay(**overrides):
    fields = dict(payee_id="p-beans", from_account_id="a-ops", amount="2880.00", pay_on=TODAY)
    fields.update(overrides)
    return SchedulePaymentInput(**fields)


def committed(store, pid, amount, pay_on=TODAY, bill_id=None, status=PaymentStatus.SCHEDULED):
    store.add_scheduled_payment(
        ScheduledPayment(
            id=pid,
            business_id=BIZ,
            payee_id="p-beans",
            from_account_id="a-ops",
            amount=amount,
            pay_on=pay_on,
            status=status,
            bill_id=bill_id,
            created_at=datetime(2026, 9, 30, 9, 0, tzinfo=SGT),
        )
    )


# --- Roles ------------------------------------------------------------------


def test_roles_are_ordered_and_tiers_documented():
    owner = Actor(user_id="u", role=Role.OWNER, business_id=BIZ, session_id="s")
    viewer = owner.model_copy(update={"role": Role.VIEWER})
    assert has_role(owner, Role.STAFF) and has_role(owner, Role.OWNER)
    assert has_role(viewer, Role.VIEWER) and not has_role(viewer, Role.STAFF)
    assert set(TIERS) == set(Role)
    assert "Schedule payments" in TIERS[Role.OWNER]


# --- Payments: happy path ---------------------------------------------------


def test_valid_payment_passes(store, sandbox):
    assert check_payment(store, sandbox, BIZ, pay(bill_id="b-1250")) == []


# --- Payee checks (induced transfers) ----------------------------------------


def add_payee(store, pid, allowlisted=True, verified=True, changed_at=None):
    store.add_payee(
        Payee(
            id=pid,
            business_id=BIZ,
            name="Highland Beans Trading",
            account_number="999-000000-1",
            bank_name="Example Bank",
            allowlisted=allowlisted,
            verified=verified,
            details_changed_at=changed_at,
        )
    )


def test_non_allowlisted_unverified_payee_blocked(store, sandbox):
    add_payee(store, "p-new", allowlisted=False, verified=False)
    reasons = check_payment(store, sandbox, BIZ, pay(payee_id="p-new"))
    assert reasons == ["payee is not on the allowlist", "payee's bank details are not verified"]


def test_allowlisted_but_unverified_payee_blocked(store, sandbox):
    add_payee(store, "p-unverified", verified=False)
    reasons = check_payment(store, sandbox, BIZ, pay(payee_id="p-unverified"))
    assert reasons == ["payee's bank details are not verified"]


def test_changed_bank_details_blocked(store, sandbox):
    add_payee(store, "p-changed", changed_at=datetime(2026, 9, 28, 14, 0, tzinfo=SGT))
    reasons = check_payment(store, sandbox, BIZ, pay(payee_id="p-changed"))
    assert len(reasons) == 1 and "changed on 2026-09-28" in reasons[0]


def test_unknown_payee_and_account(store, sandbox):
    assert check_payment(store, sandbox, BIZ, pay(payee_id="p-nope")) == ["payee not found"]
    assert "account not found" in check_payment(store, sandbox, BIZ, pay(from_account_id="a-x"))


def test_other_business_ids_are_not_found(store, sandbox):
    """A payee or bill id from another business can't be used, even in the same database."""
    ingest_folder(store, CASH_CRUNCH)
    assert check_payment(store, sandbox, BIZ, pay(payee_id="p-meridian")) == ["payee not found"]
    assert "bill not found" in check_payment(store, sandbox, BIZ, pay(bill_id="b-0048"))


# --- Limits -----------------------------------------------------------------


def test_default_limits():
    assert PolicyLimits(per_payment="75000.00", per_day="100000.00").per_day == DEFAULT_PER_DAY


@pytest.mark.parametrize(("amount", "blocked"), [("75000.00", False), ("75000.01", True)])
def test_per_payment_limit_boundary(store, sandbox, amount, blocked):
    reasons = check_payment(store, sandbox, BIZ, pay(amount=amount))
    assert any("per-payment limit of S$75,000.00" in r for r in reasons) is blocked


def test_daily_limit_counts_committed_payments_same_day(store, sandbox):
    committed(store, "sp-a", "60000.00")
    committed(store, "sp-b", "30000.00", status=PaymentStatus.EXECUTED)
    committed(store, "sp-c", "50000.00", status=PaymentStatus.CANCELLED)  # doesn't count
    committed(store, "sp-d", "50000.00", pay_on=date(2026, 10, 1))  # other day
    assert check_payment(store, sandbox, BIZ, pay(amount="10000.00")) == []
    reasons = check_payment(store, sandbox, BIZ, pay(amount="10000.01"))
    assert reasons == [
        "payments dated 2026-09-30 would total S$100,000.01, above the daily limit of S$100,000.00"
    ]


def test_limits_are_per_business(store, sandbox):
    set_limits(store, BIZ, PolicyLimits(per_payment="1000.00", per_day="1500.00"))
    assert get_limits(store, BIZ).per_payment == Decimal("1000.00")
    assert get_limits(store, "other-biz").per_payment == Decimal("75000.00")
    assert any("per-payment" in r for r in check_payment(store, sandbox, BIZ, pay()))


# --- Dates and bills --------------------------------------------------------


def test_past_date_blocked(store, sandbox):
    reasons = check_payment(store, sandbox, BIZ, pay(pay_on=date(2026, 9, 29)))
    assert reasons == ["payment date 2026-09-29 is in the past"]


def test_bill_overpayment_and_already_scheduled(store, sandbox):
    reasons = check_payment(store, sandbox, BIZ, pay(bill_id="b-1250", amount="2880.01"))
    assert any("unpaid balance of S$2,880.00" in r for r in reasons)
    committed(store, "sp-half", "1000.00", bill_id="b-1250")
    assert check_payment(store, sandbox, BIZ, pay(bill_id="b-1250", amount="1880.00")) == []
    reasons = check_payment(store, sandbox, BIZ, pay(bill_id="b-1250", amount="1880.01"))
    assert any("S$1,000.00 is already scheduled" in r for r in reasons)


def test_bill_must_belong_to_the_payee(store, sandbox):
    reasons = check_payment(
        store, sandbox, BIZ, pay(payee_id="p-landlord", bill_id="b-1250", amount="100.00")
    )
    assert reasons == ["bill BL-1250 is from a different supplier than this payee"]


# --- Reminders --------------------------------------------------------------


def test_reminder_needs_open_invoice(store, sandbox):
    assert check_reminder(store, sandbox, BIZ, DraftReminderInput(invoice_id="i-0098")) == []
    assert check_reminder(store, sandbox, BIZ, DraftReminderInput(invoice_id="i-0103")) == [
        "invoice INV-0103 is paid, not open"
    ]
    assert check_reminder(store, sandbox, BIZ, DraftReminderInput(invoice_id="i-x")) == [
        "invoice not found"
    ]


# --- set_cash_floor and the execution-time payment check (4b-1) -----------------------


@pytest.mark.parametrize(
    ("floor", "blocked"),
    [("0.00", False), ("50000.00", False), ("10000000.00", False), ("10000000.01", True)],
)
def test_floor_guard(store, sandbox, floor, blocked):
    assert bool(check_floor(store, sandbox, BIZ, SetCashFloorInput(floor=floor))) is blocked
    assert check_floor(store, sandbox, BIZ, SetCashFloorInput(floor="-1.00")) == [
        "the floor can't be negative"
    ]


def test_execution_check_leaves_the_payment_itself_out_of_the_sums(store, sandbox):
    # S$60k + S$30k dated the same day = S$90k, within the S$100k daily limit.
    committed(store, "sp-a", Decimal("60000.00"))
    committed(store, "sp-b", Decimal("30000.00"))
    payment = store.get_scheduled_payment(BIZ, "sp-a")
    assert check_scheduled_execution(store, sandbox, BIZ, payment) == []
    # Asking for it again as a NEW payment would double-count it: 60 + 30 + 60 > 100.
    assert check_payment(store, sandbox, BIZ, pay(amount="60000.00")) != []


def test_execution_check_sees_a_payee_that_changed_after_confirmation(store, sandbox):
    committed(store, "sp-a", Decimal("100.00"))
    store.conn.execute(
        "UPDATE payees SET details_changed_at = ? WHERE business_id = ? AND id = ?",
        ("2026-09-30T10:00:00+08:00", BIZ, "p-beans"),
    )
    reasons = check_scheduled_execution(
        store, sandbox, BIZ, store.get_scheduled_payment(BIZ, "sp-a")
    )
    assert any("bank details were changed" in r for r in reasons)
