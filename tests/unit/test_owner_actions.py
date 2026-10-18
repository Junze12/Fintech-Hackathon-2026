"""Owner actions added in 4d: send a reminder draft, mark an invoice paid from a bank receipt."""

from datetime import date
from decimal import Decimal

import pytest

from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor, Role
from copilot.schemas import DocumentStatus, Transaction, TransactionSource

BIZ = "biz-kopi"


def actor(role, session="s-1"):
    return Actor(user_id=f"u-{role.label}", role=role, business_id=BIZ, session_id=session)


@pytest.fixture
def gw(store, sandbox):
    return Gateway(store, sandbox)


def confirm(gw, who, result):
    assert result.outcome == "pending", result.message
    return gw.on_user_message(who, f"confirm {result.pending.code}")


def receipt(store, txn_id="t-recv", amount="1850.00", counterparty="c-events", day=20):
    store.add_transaction(
        Transaction(
            id=txn_id,
            business_id=BIZ,
            account_id="a-ops",
            date=date(2026, 9, day),
            amount=Decimal(amount),
            description="IBG CR SUNRISE EVENTS",
            counterparty_id=counterparty,
            source=TransactionSource.IMPORTED,
        )
    )


# --- send_reminder ----------------------------------------------------------------


def draft(gw, invoice_id="i-0098"):
    result = gw.call(actor(Role.STAFF), "draft_reminder", {"invoice_id": invoice_id})
    assert result.outcome == "saved"
    return result.data.id


def test_staff_drafts_owner_sends_with_code(gw, store, sandbox):
    rid = draft(gw)
    assert gw.call(actor(Role.STAFF), "send_reminder", {"reminder_id": rid}).outcome == "denied"
    result = gw.call(actor(Role.OWNER), "send_reminder", {"reminder_id": rid})
    assert "Sunrise Events" in result.pending.summary and "anyone else" in result.pending.summary
    assert store.get_reminder(BIZ, rid).status == "draft"  # nothing sent before the code
    resolution = confirm(gw, actor(Role.OWNER), result)
    assert resolution.outcome == "executed"
    sent = store.get_reminder(BIZ, rid)
    assert (sent.status, sent.sent_on, sent.sent_by) == ("sent", date(2026, 9, 30), "u-owner")
    assert [e.action for e in sandbox.events(BIZ)][-1] == "send_reminder"


def test_reminder_has_no_recipient_argument(gw):
    rid = draft(gw)
    args = {"reminder_id": rid, "to": "attacker@example.com"}
    result = gw.call(actor(Role.OWNER), "send_reminder", args)
    assert result.outcome == "invalid" and "Extra inputs" in result.message


def test_one_reminder_per_invoice_per_week(gw, sandbox):
    owner = actor(Role.OWNER)
    first, second = draft(gw), draft(gw)
    confirm(gw, owner, gw.call(owner, "send_reminder", {"reminder_id": first}))
    again = gw.call(owner, "send_reminder", {"reminder_id": first})
    assert again.outcome == "blocked" and "already sent" in again.message
    spam = gw.call(owner, "send_reminder", {"reminder_id": second})
    assert spam.outcome == "blocked" and "next one can go from 2026-10-07" in spam.message
    sandbox.advance(BIZ, 7)
    assert gw.call(owner, "send_reminder", {"reminder_id": second}).outcome == "pending"


def test_no_reminder_for_a_paid_invoice(gw, store):
    rid = draft(gw, "i-0104")
    store.update_document(BIZ, "invoice", "i-0104", Decimal("7020.00"), DocumentStatus.PAID)
    result = gw.call(actor(Role.OWNER), "send_reminder", {"reminder_id": rid})
    assert result.outcome == "blocked" and "not open" in result.message


# --- mark_invoice_paid ----------------------------------------------------------


def receipt_ids(gw):
    return {r.transaction_id for r in gw.call(actor(Role.VIEWER), "list_receipts", {}).data}


def test_list_receipts_shows_only_unlinked_customer_money(gw, store):
    # The sample's older receipts are for invoices not in the file, so they count as unlinked;
    # settled receipts (INV-0103's S$6,880.00) and money out never do.
    before = receipt_ids(gw)
    assert all(store.get_transaction(BIZ, t).amount > 0 for t in before)
    settled = next(t for t in store.list_transactions(BIZ) if t.amount == Decimal("6880.00"))
    assert settled.id not in before
    receipt(store)
    assert receipt_ids(gw) == before | {"t-recv"}
    view = next(
        r
        for r in gw.call(actor(Role.VIEWER), "list_receipts", {}).data
        if r.transaction_id == "t-recv"
    )
    assert (view.amount, view.customer_name) == (Decimal("1850.00"), "Sunrise Events")


def test_mark_paid_links_receipt_and_moves_no_money(gw, store, sandbox):
    receipt(store)
    before = sandbox.balances(BIZ)
    owner = actor(Role.OWNER)
    args = {"invoice_id": "i-0098", "transaction_id": "t-recv"}
    assert gw.call(actor(Role.STAFF), "mark_invoice_paid", args).outcome == "denied"
    result = gw.call(owner, "mark_invoice_paid", args)
    assert "becomes fully paid. No money moves." in result.pending.summary
    assert confirm(gw, owner, result).outcome == "executed"
    invoice = store.get_document(BIZ, "invoice", "i-0098")
    assert (invoice.status, invoice.amount_paid) == (DocumentStatus.PAID, Decimal("1850.00"))
    assert sandbox.balances(BIZ) == before
    assert store.receipt_links(BIZ) == {"t-recv": "i-0098"}
    assert "t-recv" not in receipt_ids(gw)


def test_part_payment_leaves_invoice_open(gw, store):
    receipt(store, amount="1000.00")
    owner = actor(Role.OWNER)
    result = gw.call(
        owner, "mark_invoice_paid", {"invoice_id": "i-0098", "transaction_id": "t-recv"}
    )
    assert "S$850.00 still outstanding" in result.pending.summary
    confirm(gw, owner, result)
    invoice = store.get_document(BIZ, "invoice", "i-0098")
    assert (invoice.status, invoice.amount_paid) == (DocumentStatus.OPEN, Decimal("1000.00"))


@pytest.mark.parametrize(
    ("setup", "args", "fragment"),
    [
        ({"counterparty": "c-pantry"}, {}, "not from invoice INV-0098's customer"),
        ({"amount": "2000.00"}, {}, "more than invoice INV-0098's outstanding S$1,850.00"),
        (
            {"counterparty": "c-pantry", "amount": "100.00", "day": 1},
            {"invoice_id": "i-0104"},
            "dated before invoice INV-0104 was issued",
        ),
        ({}, {"transaction_id": "nope"}, "bank transaction not found"),
        ({}, {"invoice_id": "i-0103"}, "is paid, not open"),
    ],
)
def test_mark_paid_guards(gw, store, setup, args, fragment):
    receipt(store, **setup)
    call = {"invoice_id": "i-0098", "transaction_id": "t-recv", **args}
    result = gw.call(actor(Role.OWNER), "mark_invoice_paid", call)
    assert result.outcome == "blocked" and fragment in result.message


def test_money_out_and_settled_receipts_cannot_be_reused(gw, store):
    owner = actor(Role.OWNER)
    out = store.list_transactions(BIZ)[0]
    assert out.amount < 0
    result = gw.call(owner, "mark_invoice_paid", {"invoice_id": "i-0098", "transaction_id": out.id})
    assert "money out, not a receipt" in result.message
    # The receipt that settled paid invoice INV-0103 can't be used again for INV-0104.
    settled = next(t for t in store.list_transactions(BIZ) if t.amount == Decimal("6880.00"))
    again = gw.call(
        owner, "mark_invoice_paid", {"invoice_id": "i-0104", "transaction_id": settled.id}
    )
    assert again.outcome == "blocked" and "already settles another" in again.message


def test_a_receipt_links_only_once(gw, store):
    receipt(store, amount="900.00")
    owner = actor(Role.OWNER)
    args = {"invoice_id": "i-0098", "transaction_id": "t-recv"}
    confirm(gw, owner, gw.call(owner, "mark_invoice_paid", args))
    again = gw.call(owner, "mark_invoice_paid", args)
    assert (
        again.outcome == "blocked" and "already recorded against invoice INV-0098" in again.message
    )


def test_sandbox_receipts_are_linked_automatically(store, sandbox):
    sandbox.record_invoice_receipt(BIZ, "i-0104", Decimal("7020.00"), "a-ops")
    assert list(store.receipt_links(BIZ).values()) == ["i-0104"]
