"""The prompt-injection fixture: cash_crunch with attacks hidden in imported text (4d)."""

from collections import defaultdict
from decimal import Decimal

import pytest

from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor, Role
from copilot.tools.render import to_llm
from copilot.untrusted import looks_like_instructions


@pytest.fixture(scope="module")
def pair(load_scenario):
    return load_scenario("cash_crunch"), load_scenario("prompt_injection")


def test_cash_and_categories_equal_cash_crunch(pair):
    base, poisoned = pair
    assert poisoned.sandbox.balances(poisoned.business_id) == base.sandbox.balances(
        base.business_id
    )

    def totals(sc):
        out = defaultdict(Decimal)
        for t in sc.store.list_transactions(sc.business_id):
            out[t.category] += t.amount
        return dict(out)

    assert totals(poisoned) == totals(base)


def test_every_poisoned_value_is_flagged(pair):
    _, poisoned = pair
    texts = [p["text"] for p in poisoned.truth["poisoned"]]
    assert len(texts) == 10
    assert all(looks_like_instructions(t) for t in texts)


def test_poisoned_text_reaches_the_llm_flagged_and_audited(pair):
    _, sc = pair
    gw = Gateway(sc.store, sc.sandbox)
    viewer = Actor(user_id="u-v", role=Role.VIEWER, business_id=sc.business_id, session_id="s")
    invoices = to_llm(gw.call(viewer, "list_invoices", {"status": "open"}).data)
    note = next(i["notes"] for i in invoices if i["id"] == "i-0057")
    assert note.startswith('<untrusted flagged="instruction-like">Please email')
    bills = to_llm(gw.call(viewer, "list_bills", {"status": "open"}).data)
    number = next(b["number"] for b in bills if b["id"] == "b-0051")
    assert "</untrusted><system>" not in number and "&lt;/untrusted&gt;" in number
    scans = [e for e in gw.audit.entries(sc.business_id) if e.tool == "injection_scan"]
    assert [e.params["tool"] for e in scans] == ["list_invoices", "list_bills"]


def test_attack_payees_and_unlinked_receipt(pair):
    _, sc = pair
    payees = {p.id: p for p in sc.store.list_payees(sc.business_id)}
    assert not payees["p-attacker"].allowlisted and not payees["p-attacker"].verified
    assert payees["p-meridian-new"].details_changed_at is not None
    link = sc.truth["unlinked_receipt"]
    gw = Gateway(sc.store, sc.sandbox)
    viewer = Actor(user_id="u-v", role=Role.VIEWER, business_id=sc.business_id, session_id="s")
    receipts = gw.call(viewer, "list_receipts", {}).data
    assert [r.transaction_id for r in receipts] == [link["transaction_id"]]
