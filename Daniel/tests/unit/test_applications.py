"""Financing applications through the policy gateway: staff pre-fill, owner submits with a
confirmation code, eligibility is re-checked at submission, and nothing is ever 'approved'."""

import sqlite3

import pytest

from copilot.ingest import ingest_folder
from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor
from copilot.schemas import ApplicationStatus, Role


@pytest.fixture
def setup(load_scenario):
    s = load_scenario("cash_crunch")
    gw = Gateway(s.store, s.sandbox)

    def actor(role):
        return Actor(
            user_id=f"u-{role.label}", role=role, business_id=s.business_id, session_id="s"
        )

    return s, gw, actor


def audit_outcomes(store, tool):
    rows = store.conn.execute(
        "SELECT outcome FROM audit_log WHERE tool = ? ORDER BY rowid", (tool,)
    ).fetchall()
    return [r["outcome"] for r in rows]


def test_roles(setup):
    s, gw, actor = setup
    assert gw.call(actor(Role.VIEWER), "prefill_application", {"product_id": "trade"}).outcome == (
        "denied"
    )
    staff = gw.call(actor(Role.STAFF), "prefill_application", {"product_id": "trade"})
    assert staff.outcome == "saved" and staff.data.status is ApplicationStatus.DRAFT
    submit = gw.call(actor(Role.STAFF), "submit_application", {"application_id": staff.data.id})
    assert submit.outcome == "denied"


def test_ineligible_or_unknown_products_are_blocked(setup):
    s, gw, actor = setup
    micro = gw.call(actor(Role.STAFF), "prefill_application", {"product_id": "micro"})
    assert micro.outcome == "blocked" and "14 staff" in micro.message
    unknown = gw.call(actor(Role.STAFF), "prefill_application", {"product_id": "nope"})
    assert unknown.outcome == "blocked"
    saved = {a.product_id for a in s.store.list_applications(s.business_id)}
    assert not saved & {"micro", "nope"}


def test_owner_submits_only_with_the_code_and_it_is_never_approved(setup):
    s, gw, actor = setup
    owner = actor(Role.OWNER)
    draft = gw.call(owner, "prefill_application", {"product_id": "invoice"}).data
    pending = gw.call(owner, "submit_application", {"application_id": draft.id})
    assert pending.outcome == "pending"
    summary = pending.pending.summary
    assert "total cost S$183.82" in summary and "EIR 18.59%" in summary
    assert "Approval is the lender's decision" in summary
    assert s.store.get_application(s.business_id, draft.id).status is ApplicationStatus.DRAFT

    done = gw.on_user_message(owner, f"confirm {pending.pending.code}")
    assert done.outcome == "executed" and "approved" not in done.message.lower()
    app = s.store.get_application(s.business_id, draft.id)
    assert app.status is ApplicationStatus.SUBMITTED and app.submitted_by == owner.user_id

    again = gw.call(owner, "submit_application", {"application_id": draft.id})
    assert again.outcome == "blocked" and "already submitted" in again.message
    assert audit_outcomes(s.store, "submit_application")[-4:] == [
        "pending",
        "confirmed",
        "executed",
        "blocked",
    ]


def test_a_wrong_code_cancels(setup):
    s, gw, actor = setup
    owner = actor(Role.OWNER)
    draft = gw.call(owner, "prefill_application", {"product_id": "trade"}).data
    gw.call(owner, "submit_application", {"application_id": draft.id})
    assert gw.on_user_message(owner, "confirm 0000").outcome == "cancelled"
    assert s.store.get_application(s.business_id, draft.id).status is ApplicationStatus.DRAFT


def test_eligibility_is_checked_again_at_submission(setup):
    s, gw, actor = setup
    owner = actor(Role.OWNER)
    draft = gw.call(owner, "prefill_application", {"product_id": "wc-efs"}).data
    s.store.conn.execute(
        "UPDATE businesses SET local_shareholding_pct = '20' WHERE id = ?", (s.business_id,)
    )
    try:
        blocked = gw.call(owner, "submit_application", {"application_id": draft.id})
        assert blocked.outcome == "blocked"
        assert "no longer eligible: local shareholding: 20%" in blocked.message
    finally:
        s.store.conn.execute(
            "UPDATE businesses SET local_shareholding_pct = '70' WHERE id = ?", (s.business_id,)
        )


def test_another_business_cannot_submit_this_draft(setup, sample_dir):
    s, gw, actor = setup
    draft = gw.call(actor(Role.OWNER), "prefill_application", {"product_id": "trade"}).data
    ingest_folder(s.store, sample_dir)  # a second business (biz-kopi) in the same database
    other = Actor(user_id="u-x", role=Role.OWNER, business_id="biz-kopi", session_id="x")
    result = gw.call(other, "submit_application", {"application_id": draft.id})
    assert result.outcome == "blocked" and "not found" in result.message


def test_the_database_refuses_any_status_but_draft_or_submitted(setup):
    s, gw, actor = setup
    draft = gw.call(actor(Role.OWNER), "prefill_application", {"product_id": "trade"}).data
    with pytest.raises(sqlite3.IntegrityError):
        s.store.conn.execute(
            "UPDATE financing_applications SET status = 'approved' WHERE id = ?", (draft.id,)
        )
