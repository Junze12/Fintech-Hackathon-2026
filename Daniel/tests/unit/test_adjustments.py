"""Chunk 13: recorded adjustments and saved forecast assumptions.

Every adjustment is non-cash and moves one pair of lines, so the balance sheet must still
balance and closing cash must still equal the bank in every month. The as-imported view must
equal the answer key exactly, whatever is applied. Values come from ground_truth.json plus the
known adjustment amount.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from copilot.analysis.statements import financial_statements, monthly_statements
from copilot.cashflow.forecast import forecast_13_weeks
from copilot.cashflow.scenarios import DelayReceipt, what_if
from copilot.runtime import open_scenario
from copilot.schemas import Role

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"


def truth(folder):
    return json.loads((folder / "ground_truth.json").read_text(encoding="utf-8"))


def session(folder=CRUNCH, role=Role.OWNER):
    return open_scenario(folder, role)


def confirm(s, result):
    assert result.outcome == "pending", result.message
    code = re.search(r"confirm (\d{4})", result.pending.prompt).group(1)
    return s.gateway.on_user_message(s.actor, f"confirm {code}")


def draft(s, **args):
    return s.gateway.call(s.actor, "draft_adjustment", args)


def apply(s, **args):
    r = draft(s, **args)
    assert r.outcome == "saved", r.message
    res = confirm(
        s, s.gateway.call(s.actor, "apply_adjustment", {"adjustment_id": r.data["adjustment_id"]})
    )
    assert res.outcome == "executed", res.message
    return r.data["adjustment_id"]


def months(s, view="with_adjustments"):
    g = s.gateway
    today = g.sandbox.today(s.actor.business_id)
    ms, _, reason = monthly_statements(g.store, s.actor.business_id, today, view)
    assert reason is None
    return {m.month: m for m in ms}


def assert_checks(s):
    for m in months(s).values():
        assert m.checks.balance_sheet_difference == 0, m.month
        assert m.checks.closing_cash_minus_bank == 0, m.month


def assert_as_imported_is_truth(s, folder=CRUNCH):
    key = truth(folder)["accrual"]["months"]
    for month, m in months(s, "as_imported").items():
        assert m.pnl.net_profit == Decimal(key[month]["pnl"]["net_profit"]), month
        assert m.balance_sheet.total_assets == Decimal(key[month]["balance_sheet"]["total_assets"])


ACCRUAL = dict(
    kind="accrued_cost",
    month="2026-09",
    amount="2000.00",
    line="professional_fees",
    reason="Accountant's September fee, billed in October",
)


# --- Double entry ------------------------------------------------------------------------


def test_accrued_cost_moves_profit_by_the_amount_and_balances():
    s = session()
    sep_truth = Decimal(truth(CRUNCH)["accrual"]["months"]["2026-09"]["pnl"]["net_profit"])
    apply(s, **ACCRUAL)
    m = months(s)
    assert m["2026-09"].pnl.net_profit == sep_truth - Decimal("2000.00")  # -6,105.30
    assert m["2026-09"].balance_sheet.accrued_costs == Decimal("2000.00")
    assert m["2026-09"].cash_flow.working_capital["accrued_costs"] == Decimal("2000.00")
    assert_checks(s)
    assert_as_imported_is_truth(s)


def test_accrual_reverses_next_month_so_the_total_is_unchanged():
    s = session()
    apply(s, **{**ACCRUAL, "month": "2026-08"})
    key = truth(CRUNCH)["accrual"]["months"]
    m = months(s)
    assert m["2026-08"].pnl.net_profit == Decimal(key["2026-08"]["pnl"]["net_profit"]) - 2000
    assert m["2026-09"].pnl.net_profit == Decimal(key["2026-09"]["pnl"]["net_profit"]) + 2000
    assert m["2026-09"].balance_sheet.accrued_costs == 0
    g = s.gateway
    today = g.sandbox.today(s.actor.business_id)
    year = financial_statements(g.store, s.actor.business_id, today, "last_12_months").value
    assert year.pnl.net_profit == Decimal("-22467.49")  # 12-month truth, unchanged
    assert year.adjustments.count == 1 and year.adjustments.difference == 0
    assert_checks(s)


def test_relabel_to_owner_drawings_raises_profit_not_equity():
    s = session()
    before = months(s)["2026-07"]
    apply(s, kind="relabel", transaction_id="t00158", to="owner_draw", reason="My own purchase")
    after = months(s)["2026-07"]
    assert after.pnl.net_profit - before.pnl.net_profit == Decimal("307.50")
    assert after.balance_sheet.total_equity == before.balance_sheet.total_equity
    assert after.balance_sheet.owner_drawings - before.balance_sheet.owner_drawings == Decimal(
        "307.50"
    )
    assert after.balance_sheet.cash == before.balance_sheet.cash
    assert_checks(s)


def test_relabel_between_cost_lines_keeps_profit():
    s = session()
    before = months(s)["2026-07"]
    apply(s, kind="relabel", transaction_id="t00158", to="software", reason="A software licence")
    after = months(s)["2026-07"]
    assert after.pnl.net_profit == before.pnl.net_profit
    assert after.pnl.operating_expenses["software"] - before.pnl.operating_expenses.get(
        "software", 0
    ) == Decimal("307.50")


def test_stock_count_moves_cost_of_sales_and_next_month():
    s = session()
    sep = months(s)["2026-09"]
    counted = sep.balance_sheet.inventory - Decimal("1500.00")
    apply(s, kind="stock_count", month="2026-09", amount=str(counted), reason="Recount: spoiled")
    after = months(s)["2026-09"]
    assert after.pnl.cost_of_sales - sep.pnl.cost_of_sales == Decimal("1500.00")
    assert after.balance_sheet.inventory == counted
    assert_checks(s)


def test_b2b_also_balances_with_every_kind():
    s = session(B2B)
    apply(s, **ACCRUAL)
    assert_checks(s)
    assert_as_imported_is_truth(s, B2B)


def test_undo_restores_the_answer_key():
    s = session()
    adj = apply(s, **ACCRUAL)
    res = confirm(s, s.gateway.call(s.actor, "undo_adjustment", {"adjustment_id": adj}))
    assert res.outcome == "executed"
    key = truth(CRUNCH)["accrual"]["months"]
    for month, m in months(s).items():
        assert m.pnl.net_profit == Decimal(key[month]["pnl"]["net_profit"])
    record = s.gateway.store.get_adjustment(s.actor.business_id, adj)
    assert record.status == "undone" and record.undone_by == s.actor.user_id  # kept


def test_statements_list_adjustments_and_both_profits():
    s = session()
    apply(s, **ACCRUAL)
    r = s.gateway.call(s.actor, "get_financial_statements", {"statement": "pnl"})
    summary = r.data.value.adjustments
    assert summary.net_profit_as_imported == Decimal("-4105.30")
    assert summary.net_profit_with_adjustments == Decimal("-6105.30")
    assert summary.difference == Decimal("-2000.00")
    llm = r.for_llm()["data"]["value"]["adjustments"]["applied"][0]
    assert llm["reason"].startswith("<untrusted>")  # typed text stays data
    imported = s.gateway.call(s.actor, "get_financial_statements", {"view": "as_imported"})
    assert imported.data.value.pnl.net_profit == Decimal("-4105.30")


def test_draft_changes_nothing_and_apply_restates_the_effect():
    s = session()
    r = draft(s, **ACCRUAL)
    assert months(s)["2026-09"].pnl.net_profit == Decimal("-4105.30")
    pending = s.gateway.call(
        s.actor, "apply_adjustment", {"adjustment_id": r.data["adjustment_id"]}
    )
    assert "goes from -S$4,105.30 to -S$6,105.30" in pending.pending.summary
    assert "Accountant" not in pending.pending.summary  # the free-text reason isn't restated


def test_no_money_moves():
    s = session()
    g, bid = s.gateway, s.actor.business_id
    before = g.sandbox.balances(bid, g.sandbox.today(bid))
    apply(s, **ACCRUAL)
    apply(s, kind="relabel", transaction_id="t00158", to="owner_draw", reason="My own purchase")
    assert g.sandbox.balances(bid, g.sandbox.today(bid)) == before


# --- Guards --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        ({**ACCRUAL, "amount": "-5000.00"}, "must be a positive amount"),
        ({**ACCRUAL, "month": "2026-05"}, "2026-05 is closed"),
        ({**ACCRUAL, "amount": "250000.01"}, "above the S$250,000.00 limit"),
        ({**ACCRUAL, "line": None}, "choose the cost line"),
        (
            {"kind": "accrued_cost", "amount": "10.00", "line": "other", "reason": "no month"},
            "needs the month",
        ),
        (
            {
                "kind": "relabel",
                "transaction_id": "t00201",
                "to": "owner_draw",
                "reason": "receipt",
            },
            "money in",
        ),
        (
            {"kind": "relabel", "transaction_id": "t99999", "to": "rent", "reason": "missing"},
            "not found",
        ),
        (
            {"kind": "relabel", "transaction_id": "t00158", "reason": "no target"},
            "choose the new category",
        ),
        (
            {"kind": "stock_count", "month": "2026-09", "amount": "-1.00", "reason": "negative"},
            "can't be negative",
        ),
    ],
)
def test_draft_guards(args, reason):
    s = session()
    r = draft(s, **{k: v for k, v in args.items() if v is not None})
    assert r.outcome == "blocked"
    assert reason in r.message


def test_relabel_of_a_bill_payment_is_blocked():
    s = session()
    g, bid = s.gateway, s.actor.business_id
    from copilot.analysis.adjustments import settled_bill_payments

    paid = sorted(settled_bill_payments(g.store, bid))
    txn = next(t for t in (g.store.get_transaction(bid, i) for i in paid) if t.date.month == 9)
    r = draft(s, kind="relabel", transaction_id=txn.id, to="rent", reason="try to move a bill")
    assert r.outcome == "blocked"
    assert "settles a supplier bill" in r.message or "can't be relabelled" in r.message


def test_reason_is_required_and_unknown_fields_rejected():
    s = session()
    assert draft(s, **{**ACCRUAL, "reason": "x"}).outcome == "invalid"
    assert draft(s, **ACCRUAL, applied=True).outcome == "invalid"


def test_second_relabel_and_second_stock_count_blocked_until_undone():
    s = session()
    apply(s, kind="relabel", transaction_id="t00158", to="owner_draw", reason="My own purchase")
    r = draft(s, kind="relabel", transaction_id="t00158", to="rent", reason="Actually rent")
    assert r.outcome == "blocked" and "already has an applied relabel" in r.message
    apply(s, kind="stock_count", month="2026-09", amount="100000.00", reason="first recount")
    r = draft(s, kind="stock_count", month="2026-09", amount="90000.00", reason="second recount")
    assert r.outcome == "blocked" and "already has an applied stock count" in r.message


def test_apply_twice_and_undo_a_draft_are_blocked():
    s = session()
    adj = apply(s, **ACCRUAL)
    r = s.gateway.call(s.actor, "apply_adjustment", {"adjustment_id": adj})
    assert r.outcome == "blocked" and "applied, not a draft" in r.message
    d = draft(s, **ACCRUAL).data["adjustment_id"]
    r = s.gateway.call(s.actor, "undo_adjustment", {"adjustment_id": d})
    assert r.outcome == "blocked" and "draft, not applied" in r.message


def test_closed_month_cannot_be_undone_after_the_clock_moves():
    s = session()
    adj = apply(s, **{**ACCRUAL, "month": "2026-07"})
    for _ in range(31):  # to 31 Oct: Oct is complete, so the open months become Aug-Oct
        assert s.gateway.advance_clock(s.actor, 1).ok
    r = s.gateway.call(s.actor, "undo_adjustment", {"adjustment_id": adj})
    assert r.outcome == "blocked" and "closed" in r.message


def test_roles():
    staff = session(role=Role.STAFF)
    r = draft(staff, **ACCRUAL)
    assert r.outcome == "saved"  # staff drafts...
    applied = staff.gateway.call(
        staff.actor, "apply_adjustment", {"adjustment_id": r.data["adjustment_id"]}
    )
    assert applied.outcome == "denied"  # ...but can't apply
    assert months(staff)["2026-09"].pnl.net_profit == Decimal("-4105.30")
    viewer = session(role=Role.VIEWER)
    assert draft(viewer, **ACCRUAL).outcome == "denied"
    assert viewer.gateway.call(viewer.actor, "list_adjustments", {}).ok


def test_business_scoping():
    s = session()
    d = draft(s, **ACCRUAL).data["adjustment_id"]
    other = open_scenario(B2B, Role.OWNER)
    # The other business's gateway can't see or apply this draft.
    r = other.gateway.call(other.actor, "apply_adjustment", {"adjustment_id": d})
    assert r.outcome == "blocked" and "not found" in r.message


def test_audit_trail():
    s = session()
    apply(s, **ACCRUAL)
    outcomes = [(e.tool, e.outcome) for e in s.gateway.audit.entries(s.actor.business_id)]
    assert ("draft_adjustment", "saved") in outcomes
    assert ("apply_adjustment", "pending") in outcomes
    assert ("apply_adjustment", "confirmed") in outcomes
    assert ("apply_adjustment", "executed") in outcomes


def test_list_adjustments_shows_uncategorised_payments_until_relabelled():
    s = session()
    r = s.gateway.call(s.actor, "list_adjustments", {})
    assert r.data["open_months"] == ["2026-07", "2026-08", "2026-09"]
    assert [c.transaction_id for c in r.data["uncategorised_payments"]] == ["t00158"]
    apply(s, kind="relabel", transaction_id="t00158", to="owner_draw", reason="My own purchase")
    r = s.gateway.call(s.actor, "list_adjustments", {})
    assert r.data["uncategorised_payments"] == []


def test_metrics_accrual_block_counts_adjustments():
    s = session()
    apply(s, **ACCRUAL)
    r = s.gateway.call(s.actor, "get_metrics", {"start": "2026-09-01", "end": "2026-09-30"})
    acc = r.data["accrual"]
    assert acc.net_profit == Decimal("-6105.30") and acc.adjustments_included == 1


# --- Saved assumptions ---------------------------------------------------------------------


def save(s, **args):
    return confirm(s, s.gateway.call(s.actor, "save_assumption", args))


def test_saved_delay_equals_the_same_what_if():
    s = session()
    g, bid = s.gateway, s.actor.business_id
    base = forecast_13_weeks(g.store, g.sandbox, bid)
    wi = what_if(g.store, bid, base, [DelayReceipt(customer_id="c-bayfront", days=21)])
    measured = 22  # cash_crunch: Bayfront's measured mean delay (ground truth observed 22.5)
    res = save(
        s,
        kind="payment_delay",
        customer_id="c-bayfront",
        days=measured + 21,
        reason="Bayfront warned us",
    )
    assert res.outcome == "executed"
    f = g.call(s.actor, "forecast_balance", {}).data.value
    assert f.low_point == wi.value.scenario_low  # -S$70,660.41 on 14 Nov
    assert f.low_point.balance == Decimal("-70660.41")
    assert f.low_point_without_saved == base.value.low_point
    assert "pays 43 days after the due date (measured 22)" in f.saved_assumptions[0]
    # What-if stays temporary: it never saved anything.
    assert len(g.store.list_assumptions(bid)) == 1


def test_recurring_change_and_remove():
    s = session()
    g, bid = s.gateway, s.actor.business_id
    res = save(
        s,
        kind="recurring_change",
        category="rent",
        monthly_amount="9000.00",
        start="2026-11-01",
        reason="New lease from November",
    )
    assert res.outcome == "executed"
    items = forecast_13_weeks(g.store, g.sandbox, bid).value.items
    rent = [i for i in items if i.ref == "rent"]
    assert rent and all(
        (i.amount == Decimal("-9000.00")) == (i.date.isoformat() >= "2026-11-01") for i in rent
    )
    aid = g.store.list_assumptions(bid, "active")[0].id
    res = confirm(s, g.call(s.actor, "remove_assumption", {"assumption_id": aid}))
    assert res.outcome == "executed"
    assert forecast_13_weeks(g.store, g.sandbox, bid).value.saved_assumptions == []
    assert g.store.get_assumption(bid, aid).status == "removed"  # kept


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        ({"kind": "payment_delay", "customer_id": "c-nobody", "days": 10}, "customer not found"),
        ({"kind": "payment_delay", "customer_id": "c-bayfront"}, "needs customer_id and days"),
        (
            {
                "kind": "recurring_change",
                "category": "marketing",
                "monthly_amount": "100.00",
                "start": "2026-11-01",
            },
            "no monthly recurring",
        ),
        (
            {
                "kind": "recurring_change",
                "category": "rent",
                "monthly_amount": "9000.00",
                "start": "2027-06-01",
            },
            "within the 13-week",
        ),
        (
            {
                "kind": "recurring_change",
                "category": "rent",
                "monthly_amount": "2000000.00",
                "start": "2026-11-01",
            },
            "above the",
        ),
    ],
)
def test_assumption_guards(args, reason):
    s = session()
    r = s.gateway.call(s.actor, "save_assumption", {**args, "reason": "testing the guard"})
    assert r.outcome == "blocked", r.message
    assert reason in r.message


def test_one_delay_per_customer_and_owner_only():
    s = session()
    save(s, kind="payment_delay", customer_id="c-bayfront", days=30, reason="first estimate")
    r = s.gateway.call(
        s.actor,
        "save_assumption",
        {
            "kind": "payment_delay",
            "customer_id": "c-bayfront",
            "days": 40,
            "reason": "second estimate",
        },
    )
    assert r.outcome == "blocked" and "remove it first" in r.message
    staff = session(role=Role.STAFF)
    r = staff.gateway.call(
        staff.actor,
        "save_assumption",
        {"kind": "payment_delay", "customer_id": "c-bayfront", "days": 40, "reason": "staff tries"},
    )
    assert r.outcome == "denied"


def test_unconfirmed_assumption_is_not_saved():
    s = session()
    r = s.gateway.call(
        s.actor,
        "save_assumption",
        {
            "kind": "payment_delay",
            "customer_id": "c-bayfront",
            "days": 0,
            "reason": "they pay on time now",
        },
    )
    assert r.outcome == "pending"
    res = s.gateway.on_user_message(s.actor, "yes do it")  # not the code
    assert res.outcome == "cancelled"
    assert s.gateway.store.list_assumptions(s.actor.business_id) == []
