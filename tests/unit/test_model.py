"""Chunk 14a: the 3-year model in Worst / Expected / Best cases.

There is no answer key for the future, so the model is checked by its own accounting (both
checks 0.00 every month), a hand-check of a flat month, the order of the cases, and the timing
it shares with the books and the 13-week forecast (loan, GST, CPF, depreciation, open
documents).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest
from pydantic import ValidationError

from copilot.analysis.model import (
    CASES,
    ModelEvent,
    ModelInputs,
    _base,
    financial_model,
)
from copilot.analysis.statements import monthly_statements
from copilot.cashflow.forecast import (
    bill_payment_date,
    forecast_13_weeks,
    gst_return,
    receipt_date,
)
from copilot.runtime import open_scenario
from copilot.schemas import Role

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"
INJECTION = SYNTHETIC_DIR / "prompt_injection"
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "samples" / "demo_business"
SEP = date(2026, 9, 30)


def session(folder=CRUNCH, role=Role.OWNER):
    return open_scenario(folder, role)


def model(s, inputs=None, monthly=True):
    return financial_model(
        s.gateway.store, s.actor.business_id, SEP, inputs, include_monthly=monthly
    )


def confirm(s, result):
    assert result.outcome == "pending", result.message
    code = re.search(r"confirm (\d{4})", result.pending.prompt).group(1)
    return s.gateway.on_user_message(s.actor, f"confirm {code}")


def assert_checks(value):
    for case in CASES:
        for m in value.cases[case].monthly:
            assert m.checks.balance_sheet_difference == 0, (case, m.month)
            assert m.checks.indirect_minus_direct_cash == 0, (case, m.month)
            assert m.cash_flow.closing_cash == m.balance_sheet.cash == m.direct_cash.closing_cash


# --- Both checks, every month, every case ------------------------------------------------


@pytest.mark.parametrize("folder", [CRUNCH, B2B, INJECTION], ids=lambda p: p.name)
def test_both_checks_hold_every_month(folder):
    v = model(session(folder)).value
    assert v.first_month == "2026-10" and v.last_month == "2029-09"
    assert all(len(v.cases[c].monthly) == 36 for c in CASES)
    assert_checks(v)


def test_checks_hold_with_an_applied_adjustment_and_a_saved_assumption():
    s = session()
    r = s.gateway.call(
        s.actor,
        "draft_adjustment",
        {
            "kind": "accrued_cost",
            "month": "2026-09",
            "amount": "2000.00",
            "line": "professional_fees",
            "reason": "September audit fee, billed in October",
        },
    )
    adj = s.gateway.call(s.actor, "apply_adjustment", {"adjustment_id": r.data["adjustment_id"]})
    assert confirm(s, adj).outcome == "executed"
    args = {
        "kind": "payment_delay",
        "customer_id": "c-bayfront",
        "days": 43,
        "reason": "slower lately",
    }
    assert confirm(s, s.gateway.call(s.actor, "save_assumption", args)).outcome == "executed"
    v = model(s).value
    assert_checks(v)
    # The accrued fee is owed at the start and paid in month 1, with no effect on profit.
    oct_ = v.cases["expected"].monthly[0]
    assert oct_.direct_cash.accrued_costs_settled == D("-2000.00")
    assert oct_.balance_sheet.accrued_costs == 0
    bayfront = next(c for c in v.customers if c.id == "c-bayfront")
    assert (bayfront.delay_worst, bayfront.delay_expected, bayfront.delay_best) == (58, 43, 0)
    assert "saved assumption" in bayfront.delay_source


def test_saved_rent_change_is_used_from_its_start_month():
    s = session()
    args = {
        "kind": "recurring_change",
        "category": "rent",
        "monthly_amount": "9000.00",
        "start": "2026-11-01",
        "reason": "New lease",
    }
    assert confirm(s, s.gateway.call(s.actor, "save_assumption", args)).outcome == "executed"
    months = model(s).value.cases["expected"].monthly
    assert months[0].pnl.operating_expenses["rent"] == D("12500.00")
    assert months[1].pnl.operating_expenses["rent"] == D("9000.00")
    assert months[12].pnl.operating_expenses["rent"] == D("9270.00")  # +3% from year 2


# --- Flat hand-check ---------------------------------------------------------------------


def test_flat_month_rebuilt_by_hand():
    """Growth 0 and cost increase 0: Sep 2028 (after the loan's last instalment and the
    scanners' last depreciation) must equal the last-12-month averages, line by line."""
    s = session()
    hist, _, _ = monthly_statements(s.gateway.store, s.actor.business_id, SEP)
    last12 = hist[-12:]

    def avg(get):
        return (sum((get(m) for m in last12), D(0)) / 12).quantize(D("0.01"))

    inputs = ModelInputs(sales_growth_pct=D("0"), cost_increase_pct=D("0"))
    v = model(s, inputs).value
    expected = v.cases["expected"].monthly
    m = expected[23]
    assert m.month == "2028-09"
    revenue = avg(lambda x: x.pnl.revenue)  # S$126,970.37
    assert m.pnl.revenue == revenue
    cos = (revenue * D("50.63") / 100).quantize(D("0.01"))
    assert m.pnl.cost_of_sales == cos
    opex = {
        line: avg(lambda x, line=line: x.pnl.operating_expenses.get(line, D(0)))
        for line in ("rent", "utilities", "software", "other")
    }
    payroll = D("39232.39") + D("4216.22") + D("3583.78")  # Sep 2026 run: net pay + CPF
    depreciation = m.pnl.operating_expenses["depreciation"]
    assert depreciation in (D("1291.66"), D("1291.67"))  # racking 375 + van 916.67
    assert m.pnl.interest == 0  # TL-20817 ended May 2028
    hand = revenue - cos - sum(opex.values()) - payroll - depreciation
    assert m.pnl.net_profit == hand
    # Flat: every month of year 1 is the same sales figure, and year 3 the same again.
    assert {x.pnl.revenue for x in expected} == {revenue}


# --- Worst <= Expected <= Best ------------------------------------------------------------


@pytest.mark.parametrize("folder", [CRUNCH, B2B, INJECTION], ids=lambda p: p.name)
def test_cases_are_in_order_every_month(folder):
    v = model(session(folder)).value
    worst, expected, best = (v.cases[c].monthly for c in CASES)
    for w, e, b in zip(worst, expected, best, strict=True):
        assert w.balance_sheet.cash <= e.balance_sheet.cash <= b.balance_sheet.cash, e.month
        assert w.pnl.net_profit <= e.pnl.net_profit <= b.pnl.net_profit, e.month


def test_drivers_and_their_sources():
    v = model(session(), monthly=False).value
    d = {x.key: x for x in v.drivers}
    assert (d["sales_growth_pct"].worst, d["sales_growth_pct"].expected) == (
        D("-10.23"),
        D("-0.23"),
    )
    assert d["sales_growth_pct"].best == D("9.77")
    assert "last 6 months" in d["sales_growth_pct"].source
    assert (d["cost_of_sales_pct"].worst, d["cost_of_sales_pct"].expected) == (
        D("53.63"),
        D("50.63"),
    )
    assert d["cost_of_sales_pct"].best == D("47.63")
    rise = d["cost_increase_pct"]
    assert (rise.worst, rise.expected, rise.best) == (D("5"), D("3"), D("2"))
    assert rise.source == "our assumption, not data"
    delays = {c.id: (c.delay_worst, c.delay_expected, c.delay_best) for c in v.customers}
    assert delays["c-bayfront"] == (37, 22, 0)
    assert v.cases["expected"].monthly == []  # monthly rows only when asked


def test_override_replaces_expected_and_rederives_worst_and_best():
    inputs = ModelInputs(sales_growth_pct=D("10"), cost_of_sales_pct=D("45"), customer_delay_days=5)
    v = model(session(), inputs, monthly=False).value
    d = {x.key: x for x in v.drivers}
    assert (d["sales_growth_pct"].worst, d["sales_growth_pct"].best) == (D("0"), D("20"))
    assert (d["cost_of_sales_pct"].worst, d["cost_of_sales_pct"].best) == (D("48"), D("42"))
    assert d["sales_growth_pct"].source == "your figure for this question"
    assert all((c.delay_worst, c.delay_expected, c.delay_best) == (20, 5, 0) for c in v.customers)
    y1 = v.cases["expected"].outlook.year1_revenue_vs_last_12_months
    assert y1 == D("0.1000")


def test_events_and_drawings_apply_to_every_case():
    plain = model(session(), monthly=True).value
    inputs = ModelInputs(
        owner_drawings=D("3000.00"),
        events=[
            ModelEvent(label="new hire", month="2027-01", amount=D("-5000.00"), repeat="monthly"),
            ModelEvent(label="grant", month="2027-03", amount=D("10000.00")),
        ],
    )
    v = model(session(), inputs).value
    assert_checks(v)
    for case in CASES:
        before, after = plain.cases[case].monthly, v.cases[case].monthly
        assert before[2].pnl.net_profit - after[2].pnl.net_profit == 0  # Dec 2026: nothing yet
        assert before[3].pnl.net_profit - after[3].pnl.net_profit == D("5000.00")  # hire
        assert after[3].pnl.operating_expenses["planned_events"] == D("5000.00")
        assert after[5].pnl.other_income == D("10000.00")  # grant in Mar 2027
        drawn = before[0].balance_sheet.cash - after[0].balance_sheet.cash
        assert drawn == D("3000.00")


def test_bad_inputs_are_rejected():
    with pytest.raises(ValidationError):
        ModelInputs(sales_growth_pct=D("500"))
    with pytest.raises(ValidationError):
        ModelInputs(customer_delay_days=-3)
    with pytest.raises(ValidationError):
        ModelInputs(events=[ModelEvent(label="x", month="2027-01", amount=D("-1"))] * 6)
    late = ModelInputs(events=[ModelEvent(label="far", month="2031-01", amount=D("-1.00"))])
    with pytest.raises(ValueError, match="2026-10 to 2029-09"):
        model(session(), late)


def test_no_opening_balance_sheet_gives_the_reason():
    s = session(SAMPLE)
    r = financial_model(s.gateway.store, s.actor.business_id, s.gateway.today(s.actor))
    assert r.value is None
    assert "opening balance sheet" in r.warnings[0]


# --- Timing shared with the books and the 13-week forecast ---------------------------------


def test_loan_follows_the_lenders_schedule():
    s = session()
    rows = {
        f"{r.due_date.year}-{r.due_date.month:02d}": r
        for r in s.gateway.store.list_loan_schedule(s.actor.business_id)
    }
    for case in CASES:
        for m in model(s).value.cases[case].monthly:
            row = rows.get(m.month)
            if row is not None:
                assert m.pnl.interest == row.interest
                assert m.cash_flow.financing_loan_principal == -row.principal
                assert m.balance_sheet.loans == row.balance_after
                assert m.direct_cash.loan_repayments == -row.instalment
            else:  # after May 2028
                assert m.month > "2028-05" and m.balance_sheet.loans == 0
                assert m.direct_cash.loan_repayments == 0


def test_gst_is_paid_quarterly_and_october_matches_the_return():
    s = session()
    st, bid = s.gateway.store, s.actor.business_id
    q3 = gst_return(st.list_invoices(bid), st.list_bills(bid), date(2026, 7, 1), SEP)
    assert q3 == D("9867.75")
    for case in CASES:
        months = model(s).value.cases[case].monthly
        assert months[0].direct_cash.gst_paid == -q3
        for prev, m in zip(months, months[1:], strict=False):
            if int(m.month[5:]) in (1, 4, 7, 10):
                assert m.direct_cash.gst_paid == -prev.balance_sheet.gst_payable
            else:
                assert m.direct_cash.gst_paid == 0


def test_cpf_is_owed_at_month_end_and_paid_the_month_after():
    months = model(session()).value.cases["expected"].monthly
    assert months[0].balance_sheet.cpf_payable == D("7800.00")
    assert months[12].balance_sheet.cpf_payable == D("8034.00")  # +3% in year 2
    for prev, m in zip(months, months[1:], strict=False):
        net_pay = m.pnl.operating_expenses["payroll"] - m.balance_sheet.cpf_payable
        assert m.direct_cash.payroll_paid == -(net_pay + prev.balance_sheet.cpf_payable)


def test_depreciation_steps_down_when_the_scanners_are_written_off():
    months = {m.month: m for m in model(session()).value.cases["expected"].monthly}
    assert months["2027-06"].pnl.operating_expenses["depreciation"] == D("1625.00")
    assert months["2027-07"].pnl.operating_expenses["depreciation"] in (
        D("1291.66"),
        D("1291.67"),
    )


@pytest.mark.parametrize("folder", [CRUNCH, B2B], ids=lambda p: p.name)
def test_open_documents_are_timed_like_the_13_week_forecast(folder):
    s = session(folder)
    st, bid = s.gateway.store, s.actor.business_id
    base = _base(st, bid, SEP)
    forecast = forecast_13_weeks(st, s.gateway.sandbox, bid).value
    when = {it.ref: it.date for it in forecast.items if it.source in ("open_invoice", "open_bill")}
    expected = {c.id: c.delay_expected for c in model(s, monthly=False).value.customers}
    assert base.open_invoices and base.bill_payments
    for due, cid, _, ref in base.open_invoices:
        assert receipt_date(due, expected.get(cid, base.delays.get(cid, 0)), SEP) == when[ref]
    bills = {b.id: b for b in st.list_bills(bid)}
    for d in base.bill_payments:
        assert d.when == bill_payment_date(bills[d.ref].due_date, SEP) == when[d.ref]
    # And the money adds up to the balance sheet the model opens from.
    opening = base.opening.balance_sheet
    assert sum(a for *_, a, _ in base.open_invoices) == opening.receivables
    assert -sum(d.amount for d in base.bill_payments) == opening.payables


def test_s85k_stock_bill_pauses_purchases_and_is_paid_in_november():
    months = model(session()).value.cases["expected"].monthly
    assert months[0].pnl.purchases == 0  # 30 Sep stock S$117,843.55 covers October
    assert months[1].pnl.purchases > 0
    assert months[0].balance_sheet.payables == D("85000.00")  # MFI-88120, due 5 Nov
    assert months[1].direct_cash.supplier_payments <= D("-85000.00")


def test_tool_through_the_gateway_for_a_viewer():
    s = session(role=Role.VIEWER)
    r = s.gateway.call(s.actor, "get_financial_model", {})
    assert r.ok, r.message
    v = r.data.value
    assert set(v.cases) == set(CASES) and all(not c.monthly for c in v.cases.values())
    one = s.gateway.call(
        s.actor, "get_financial_model", {"case": "worst", "view": "monthly", "year": 2}
    )
    assert one.ok and set(one.data.value.cases) == {"worst"}
    rows = one.data.value.cases["worst"].monthly
    assert [m.month for m in rows][0] == "2027-10" and len(rows) == 12
    bad = s.gateway.call(s.actor, "get_financial_model", {"view": "monthly"})
    assert not bad.ok


def test_loan_list_shows_the_balance_and_last_payment():
    (loan,) = model(session(), monthly=False).value.loans
    assert (loan.id, loan.balance_at_start, loan.last_payment_month) == (
        "TL-20817",
        D("79406.52"),
        "2028-05",
    )
    assert model(session(B2B), monthly=False).value.loans == []
