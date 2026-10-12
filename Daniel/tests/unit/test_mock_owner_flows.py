"""The rule-based assistant on the poisoned scenario: new owner actions, flagged text shown."""

import re
from decimal import Decimal

import pytest

from copilot.agent import handle
from copilot.agent.mock_rules import FLAG_NOTE
from copilot.runtime import ROOT, open_scenario
from copilot.schemas import Role

POISONED = ROOT / "data" / "synthetic" / "prompt_injection"


@pytest.fixture
def owner():
    return open_scenario(POISONED, Role.OWNER)


def code(reply):
    return re.search(r"confirm (\d{4})", reply.pending_prompt).group(1)


def test_unmatched_receipts_point_out_injected_text(owner):
    text = handle("Any unmatched receipts?", owner).text
    assert "S$8,005.63 from Kallang Corner Stores" in text
    assert FLAG_NOTE + "FAST Kallang Corner Stores INV-1064" in text


def test_mark_invoice_paid_with_the_receipt(owner):
    store, biz = owner.gateway.store, owner.actor.business_id
    before = owner.gateway.sandbox.balances(biz)
    reply = handle("Mark INV-1064 paid", owner)
    assert "which becomes fully paid. No money moves." in reply.pending_prompt
    done = handle(f"confirm {code(reply)}", owner)
    assert done.notices == ("Invoice INV-1064 is now paid. No money moved.",)
    assert store.get_document(biz, "invoice", "i-0064").amount_paid == Decimal("8005.63")
    assert owner.gateway.sandbox.balances(biz) == before
    assert "already matched" in handle("Any unmatched receipts?", owner).text


def test_no_matching_receipt_changes_nothing(owner):
    text = handle("Mark INV-1057 paid", owner).text
    assert "can't see a receipt from Bayfront Grocers" in text and "Nothing was changed" in text


def test_send_reminder_then_weekly_limit(owner):
    reply = handle("Send the reminder for INV-1057", owner)
    assert "to Bayfront Grocers Pte. Ltd., the customer on that invoice" in reply.pending_prompt
    sent = handle(f"confirm {code(reply)}", owner)
    assert "sent to Bayfront Grocers Pte. Ltd. (simulated)" in sent.notices[0]
    again = handle("Send the reminder for INV-1057", owner)
    assert "next one can go from 2026-10-07" in again.text


@pytest.mark.parametrize("role", [Role.VIEWER, Role.STAFF])
def test_lower_roles_are_told_who_can(role):
    s = open_scenario(POISONED, role)
    assert "Only the owner" in handle("Send the reminder for INV-1057", s).text
    assert "Only the owner" in handle("Mark INV-1064 paid", s).text
