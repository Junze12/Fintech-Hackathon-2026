"""Advancing the simulated clock (policy/scheduler.py via Gateway.advance_clock): the world
plays out, the owner's scheduled payments run after the guard is re-checked (known risk R8),
alerts are re-evaluated, and every step is audited."""

from datetime import date
from decimal import Decimal

import pytest

from copilot.cashflow.forecast import daily_balances
from copilot.runtime import SCENARIOS, open_scenario
from copilot.schemas import DocumentStatus, PaymentStatus, Role

FOLDER = SCENARIOS["Straits Harbour Distribution (cash crunch)"]
BIZ = "biz-straits"


@pytest.fixture
def owner():
    return open_scenario(FOLDER, Role.OWNER)


def schedule_and_confirm(session, **args):
    gw, actor = session.gateway, session.actor
    result = gw.call(actor, "schedule_payment", {"from_account_id": "a-ops", **args})
    assert result.outcome == "pending", result.message
    resolution = gw.on_user_message(actor, f"confirm {result.pending.code}")
    assert resolution.outcome == "scheduled", resolution.message
    return resolution.data["payment_id"]


def audit(session, tool):
    return [e for e in session.gateway.audit.entries(BIZ) if e.tool == tool]


@pytest.mark.parametrize("days", [0, -1, 29, True, 2.5])
def test_bad_day_counts_are_refused_and_audited(owner, days):
    report = owner.gateway.advance_clock(owner.actor, days)
    assert not report.ok and "1 to 28" in report.message
    assert owner.gateway.today(owner.actor) == date(2026, 9, 30)
    assert audit(owner, "advance_clock")[-1].outcome == "invalid"


def test_cannot_run_past_the_end_of_the_script(owner):
    for _ in range(3):
        assert owner.gateway.advance_clock(owner.actor, 28).ok  # to 2026-12-23
    report = owner.gateway.advance_clock(owner.actor, 7)
    assert not report.ok and "ends on 2026-12-27" in report.message


def test_any_role_can_advance_and_it_is_not_an_llm_tool():
    viewer = open_scenario(FOLDER, Role.VIEWER)
    assert viewer.gateway.advance_clock(viewer.actor, 1).ok
    owner = open_scenario(FOLDER, Role.OWNER)
    assert "advance_clock" not in {t["name"] for t in owner.gateway.specs(owner.actor)}
    assert owner.gateway.call(owner.actor, "advance_clock", {"days": 7}).outcome == "invalid"


def test_one_week_report(owner):
    report = owner.gateway.advance_clock(owner.actor, 7)
    assert report.ok and (report.start, report.end) == (date(2026, 9, 30), date(2026, 10, 7))
    assert "Customers paid S$12,328.58" in report.message  # Kallang INV-1065 on 10-06
    assert "S$87,411.06 went out" in report.message
    # INV-1061 (Bayfront, due 10-04) is newly overdue; INV-1057 was already overdue.
    keys = {a.key for a in report.new_alerts}
    assert "overdue:i-0061" in keys and "overdue:i-0057" not in keys
    entry = audit(owner, "advance_clock")[-1]
    assert entry.outcome == "executed" and entry.params == {"days": 7}


def test_forecast_after_a_week_still_sees_the_5_november_breach(owner):
    owner.gateway.advance_clock(owner.actor, 7)
    forecast = owner.gateway.call(owner.actor, "forecast_balance", {}).data.value
    first_negative = next(d for d, b in daily_balances(forecast) if b < 0)
    assert abs((first_negative - date(2026, 11, 5)).days) <= 7


def test_scheduled_payment_runs_on_its_date_and_the_world_leaves_the_bill_alone(owner):
    pid = schedule_and_confirm(
        owner, payee_id="p-meridian", amount="61898.43", pay_on="2026-10-02", bill_id="b-0048"
    )
    report = owner.gateway.advance_clock(owner.actor, 3)
    [run] = report.payments
    assert (run.payment_id, run.date, run.outcome) == (pid, date(2026, 10, 2), "executed")
    assert "bill BL-5048" in run.description
    store = owner.gateway.store
    assert store.get_scheduled_payment(BIZ, pid).status is PaymentStatus.EXECUTED
    assert store.get_document(BIZ, "bill", "b-0048").status is DocumentStatus.PAID
    world = [o for o in report.world if "BL-5048" in o.description]
    assert [o.outcome for o in world] == ["skipped"]  # paid once, by the copilot
    [entry] = audit(owner, "execute_scheduled_payment")
    assert (entry.user_id, entry.outcome) == ("system-scheduler", "executed")


def test_r8_payment_blocked_if_payee_details_change_after_confirmation(owner):
    pid = schedule_and_confirm(
        owner, payee_id="p-meridian", amount="61898.43", pay_on="2026-10-02", bill_id="b-0048"
    )
    store = owner.gateway.store
    store.conn.execute(  # a "supplier changed their bank account" event after confirmation
        "UPDATE payees SET details_changed_at = ? WHERE business_id = ? AND id = ?",
        ("2026-10-01T10:00:00+08:00", BIZ, "p-meridian"),
    )
    report = owner.gateway.advance_clock(owner.actor, 1)  # to 10-01: not due yet
    assert report.payments == []
    before = owner.gateway.sandbox.balance(BIZ, "a-ops", date(2026, 10, 1))
    report = owner.gateway.advance_clock(owner.actor, 1)  # 10-02: due
    [run] = report.payments
    assert run.outcome == "blocked" and "bank details were changed" in run.reason
    assert store.get_scheduled_payment(BIZ, pid).status is PaymentStatus.BLOCKED
    assert owner.gateway.sandbox.balance(BIZ, "a-ops", date(2026, 10, 2)) == before  # no money
    [entry] = audit(owner, "execute_scheduled_payment")
    assert entry.outcome == "blocked" and "re-verified" in entry.reason
    assert "1 scheduled payment(s) stopped" in report.message


def test_payment_does_not_count_against_its_own_daily_limit(owner):
    # S$60k alone is within the S$100k daily limit; counted twice it would be S$120k.
    pid = schedule_and_confirm(owner, payee_id="p-landlord", amount="60000.00", pay_on="2026-10-02")
    [run] = owner.gateway.advance_clock(owner.actor, 2).payments
    assert run.payment_id == pid and run.outcome == "executed"


def test_insufficient_funds_is_reported_as_rejected(owner):
    pid = schedule_and_confirm(owner, payee_id="p-landlord", amount="75000.00", pay_on="2026-10-04")
    report = owner.gateway.advance_clock(owner.actor, 4)
    [run] = report.payments
    assert run.payment_id == pid and run.outcome == "rejected"
    assert run.reason == "insufficient funds"
    assert owner.gateway.store.get_scheduled_payment(BIZ, pid).status is PaymentStatus.BLOCKED
    assert audit(owner, "execute_scheduled_payment")[-1].outcome == "rejected"


def test_scheduled_payment_appears_in_the_forecast_once(owner):
    gw, actor = owner.gateway, owner.actor
    before = gw.call(actor, "forecast_balance", {}).data.value
    schedule_and_confirm(
        owner, payee_id="p-meridian", amount="61898.43", pay_on="2026-10-08", bill_id="b-0048"
    )
    after = gw.call(actor, "forecast_balance", {}).data.value
    sources = {it.source for it in after.items if "BL-5048" in it.label}
    assert sources == {"scheduled_payment"}  # the open-bill item is replaced, not doubled
    assert after.weeks[-1].end_balance == before.weeks[-1].end_balance
    moved = Decimal("61898.43")
    assert after.weeks[0].end_balance == before.weeks[0].end_balance + moved  # paid in week 2
