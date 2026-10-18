"""The audit log is tamper-evident: editing, deleting or reordering a row breaks the chain."""

import pytest

from copilot.policy.audit import GENESIS
from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor, Role

BIZ = "biz-kopi"
OWNER = Actor(user_id="u-owner", role=Role.OWNER, business_id=BIZ, session_id="s-1")


@pytest.fixture
def gw(store, sandbox):
    gw = Gateway(store, sandbox)
    gw.call(OWNER, "get_cash_position", {})
    gw.call(OWNER, "schedule_payment", {"payee_id": "p-bad", "amount": "1.00"})
    gw.call(OWNER, "list_bills", {"status": "open"})
    gw.call(OWNER, "set_cash_floor", {"floor": "1000.00"})
    return gw


def seqs(gw):
    return [e.seq for e in gw.audit.entries(BIZ)]


def test_an_untouched_log_verifies(gw):
    check = gw.audit.verify_chain(BIZ)
    assert check.ok and check.entries == 4
    assert check.head == gw.audit.entries(BIZ)[-1].row_hash != GENESIS
    assert gw.audit.verify_chain("biz-nobody").head == GENESIS


def test_editing_a_row_is_detected(gw, store):
    second = seqs(gw)[1]
    store.conn.execute("UPDATE audit_log SET outcome = 'executed' WHERE seq = ?", (second,))
    check = gw.audit.verify_chain(BIZ)
    assert not check.ok and check.first_bad_seq == second
    assert check.problem == "this row was changed after it was written"


def test_deleting_a_row_is_detected(gw, store):
    s = seqs(gw)
    store.conn.execute("DELETE FROM audit_log WHERE seq = ?", (s[1],))
    check = gw.audit.verify_chain(BIZ)
    assert not check.ok and check.first_bad_seq == s[2]
    assert "removed or reordered" in check.problem


def test_reordering_rows_is_detected(gw, store):
    s = seqs(gw)
    store.conn.execute("UPDATE audit_log SET seq = 1000 WHERE seq = ?", (s[0],))
    assert not gw.audit.verify_chain(BIZ).ok


def test_deleting_the_newest_row_changes_the_head(gw, store):
    """Tail deletion leaves a valid shorter chain; only a recorded head hash reveals it."""
    head = gw.audit.verify_chain(BIZ).head
    store.conn.execute("DELETE FROM audit_log WHERE seq = ?", (seqs(gw)[-1],))
    check = gw.audit.verify_chain(BIZ)
    assert check.ok and check.head != head
