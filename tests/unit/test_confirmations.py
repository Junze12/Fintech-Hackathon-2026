"""Confirmation flow: a payment runs only after the user's own next message is 'confirm <code>'."""

from datetime import date
from decimal import Decimal

import pytest

from copilot.policy.confirmations import is_confirmation
from copilot.policy.gateway import Gateway
from copilot.policy.limits import PolicyLimits, set_limits
from copilot.policy.roles import Actor, Role
from copilot.schemas import DocumentStatus, PaymentStatus

BIZ = "biz-kopi"
OPS_BALANCE = Decimal("13358.15")
PAY_BILL = dict(
    payee_id="p-beans",
    from_account_id="a-ops",
    amount="2880.00",
    pay_on="2026-09-30",
    bill_id="b-1250",
)


@pytest.fixture
def gw(store, sandbox):
    return Gateway(store, sandbox)


@pytest.fixture
def owner():
    return Actor(user_id="u-owner", role=Role.OWNER, business_id=BIZ, session_id="s-1")


def propose(gw, owner, **overrides):
    result = gw.call(owner, "schedule_payment", {**PAY_BILL, **overrides})
    assert result.outcome == "pending", result.message
    return result.pending


def payments(store):
    return store.list_scheduled_payments(BIZ)


# --- Parsing ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "ok"),
    [
        ("confirm 4821", True),
        ("  Confirm   4821 ", True),
        ("CONFIRM 4821.", True),
        ("confirm 4822", False),
        ("yes", False),
        ("confirm", False),
        ("4821", False),
        ("confirm 4821 and also pay p-bad", False),
        ("Sure, confirm 4821", False),
    ],
)
def test_only_exact_confirm_code_counts(message, ok):
    assert is_confirmation(message, "4821") is ok


# --- Flow -------------------------------------------------------------------


def test_nothing_written_until_confirmed(gw, owner, store, sandbox):
    action = propose(gw, owner)
    assert len(action.code) == 4 and action.code.isdigit()
    assert "Pay S$2,880.00 to Highland Beans Trading (••••1111)" in action.summary
    assert "for bill BL-1250" in action.summary
    assert payments(store) == []
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE


def test_right_code_executes_once(gw, owner, store, sandbox):
    action = propose(gw, owner)
    resolution = gw.on_user_message(owner, f"confirm {action.code}")
    assert resolution.outcome == "executed"
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE - Decimal("2880.00")
    assert store.get_document(BIZ, "bill", "b-1250").status is DocumentStatus.PAID
    # Replaying the same confirmation does nothing: the action is no longer pending.
    assert gw.on_user_message(owner, f"confirm {action.code}") is None
    assert [p.status for p in payments(store)] == [PaymentStatus.EXECUTED]
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE - Decimal("2880.00")


@pytest.mark.parametrize("message", ["yes", "confirm", "what's my balance?", "cancel"])
def test_any_other_message_cancels(gw, owner, store, sandbox, message):
    action = propose(gw, owner)
    resolution = gw.on_user_message(owner, message)
    assert resolution.outcome == "cancelled"
    assert resolution.message.startswith("Cancelled, nothing done")
    # The right code afterwards is too late.
    assert gw.on_user_message(owner, f"confirm {action.code}") is None
    assert payments(store) == []
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE


def test_wrong_code_cancels(gw, owner, store):
    action = propose(gw, owner)
    wrong = f"{(int(action.code) + 1) % 10000:04d}"
    assert gw.on_user_message(owner, f"confirm {wrong}").outcome == "cancelled"
    assert payments(store) == []


def test_no_pending_action_means_no_resolution(gw, owner):
    assert gw.on_user_message(owner, "confirm 1234") is None


def test_new_proposal_replaces_old_one(gw, owner, store, monkeypatch):
    codes = iter([1111, 2222])
    monkeypatch.setattr("copilot.policy.confirmations.secrets.randbelow", lambda n: next(codes))
    first = propose(gw, owner, amount="1000.00")
    second = propose(gw, owner, amount="1500.00")
    assert gw.confirmations.current(owner).id == second.id
    # The old code no longer works, and using it cancels the current request too.
    assert gw.on_user_message(owner, f"confirm {first.code}").outcome == "cancelled"
    assert payments(store) == []
    outcomes = [e.outcome for e in gw.audit.entries(BIZ)]
    assert outcomes == ["pending", "cancelled", "pending", "cancelled"]


def test_pending_action_belongs_to_its_session_and_user(gw, owner, store):
    action = propose(gw, owner)
    other_session = owner.model_copy(update={"session_id": "s-2"})
    other_user = owner.model_copy(update={"user_id": "u-intruder"})
    assert gw.on_user_message(other_session, f"confirm {action.code}") is None
    assert gw.on_user_message(other_user, f"confirm {action.code}") is None
    assert gw.on_user_message(owner, f"confirm {action.code}").outcome == "executed"


def test_guards_rechecked_at_confirmation(gw, owner, store):
    action = propose(gw, owner, bill_id=None, amount="1000.00")
    set_limits(store, BIZ, PolicyLimits(per_payment="500.00", per_day="500.00"))
    resolution = gw.on_user_message(owner, f"confirm {action.code}")
    assert resolution.outcome == "blocked"
    assert "per-payment limit of S$500.00" in resolution.message
    assert payments(store) == []


def test_role_rechecked_at_confirmation(gw, owner, store):
    action = propose(gw, owner)
    demoted = owner.model_copy(update={"role": Role.STAFF})
    assert gw.on_user_message(demoted, f"confirm {action.code}").outcome == "denied"
    assert payments(store) == []


def test_future_payment_is_scheduled_not_executed(gw, owner, store, sandbox):
    action = propose(gw, owner, pay_on="2026-10-20")
    resolution = gw.on_user_message(owner, f"confirm {action.code}")
    assert resolution.outcome == "scheduled"
    [payment] = payments(store)
    assert payment.status is PaymentStatus.SCHEDULED and payment.pay_on == date(2026, 10, 20)
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE


def test_insufficient_funds_is_reported_not_executed(gw, owner, store, sandbox):
    action = propose(gw, owner, bill_id=None, amount="20000.00")
    resolution = gw.on_user_message(owner, f"confirm {action.code}")
    assert resolution.outcome == "rejected"
    assert "insufficient funds" in resolution.message
    assert [p.status for p in payments(store)] == [PaymentStatus.BLOCKED]
    assert sandbox.balance(BIZ, "a-ops") == OPS_BALANCE


def test_full_flow_is_audited(gw, owner):
    action = propose(gw, owner)
    gw.on_user_message(owner, f"confirm {action.code}")
    entries = gw.audit.entries(BIZ)
    assert [e.outcome for e in entries] == ["pending", "confirmed", "executed"]
    assert {e.tool for e in entries} == {"schedule_payment"}
    assert all(e.role is Role.OWNER and e.user_id == "u-owner" for e in entries)
    assert entries[0].params["amount"] == "2880.00"
    assert "code" not in entries[0].params
