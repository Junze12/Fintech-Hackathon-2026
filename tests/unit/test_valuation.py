"""Chunk 14b: break-even per case and an estimated value of the business.

There is no answer key for a value, so it is checked by hand from the 3-year model's own
figures (DCF arithmetic, terminal value, bridge, break-even month), by the order of the cases
(Worst <= Expected <= Best) and by the "not meaningful" guards.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

import pytest
from pydantic import ValidationError

from copilot.agent import handle
from copilot.analysis.health import break_even_sales
from copilot.analysis.model import CASES, ModelInputs, financial_model
from copilot.analysis.valuation import ValueInputs, business_value
from copilot.runtime import open_scenario
from copilot.schemas import Role

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"
INJECTION = SYNTHETIC_DIR / "prompt_injection"
MESSY = SYNTHETIC_DIR / "messy_books"
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "samples" / "demo_business"
SEP = date(2026, 9, 30)
CENT = D("0.01")


def session(folder=CRUNCH, role=Role.OWNER):
    return open_scenario(folder, role)


def value(s, model_inputs=None, inputs=None):
    return business_value(s.gateway.store, s.actor.business_id, SEP, model_inputs, inputs)


def r2(x: D) -> D:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


@pytest.fixture(scope="module")
def crunch():
    s = session(CRUNCH)
    return s, value(s)


@pytest.fixture(scope="module")
def b2b():
    s = session(B2B)
    return s, value(s)


# --- Hand checks -----------------------------------------------------------------------------


def test_dcf_by_hand_on_b2b_expected(b2b):
    s, result = b2b
    model = financial_model(s.gateway.store, s.actor.business_id, SEP).value
    years = model.cases["expected"].years
    fcf = []
    for y in years:
        tax = r2(max(y.pnl.operating_profit, D(0)) * D("0.17"))
        fcf.append(y.cash_flow.operating + y.pnl.interest - tax)
    pv = [r2(f / D("1.2") ** n) for n, f in enumerate(fcf, start=1)]
    terminal = r2(fcf[2] * D("1.02") / D("0.18"))
    pv_terminal = r2(terminal / D("1.728"))
    ev = sum(pv) + pv_terminal

    v = result.value.valuation
    dcf = v.cases["expected"].dcf
    assert [y.free_cash_flow for y in v.cases["expected"].years] == fcf
    assert fcf == [D("90963.92"), D("78284.01"), D("65221.83")]
    assert dcf.present_value_years_1_3 == sum(pv) == D("167911.28")
    assert dcf.terminal_value == terminal == D("369590.37")
    assert dcf.present_value_terminal == pv_terminal == D("213883.32")
    assert dcf.enterprise_value == ev == D("381794.60")
    assert dcf.terminal_share == D("0.5602")  # under 60%: no warning for Expected
    bridge = v.bridge
    assert bridge.net_debt == bridge.loans + bridge.other_borrowings - bridge.cash
    assert bridge.cash == D("194994.50") and bridge.loans == 0
    assert dcf.equity_value == ev - bridge.net_debt == D("576789.10")


def test_multiple_by_hand_on_b2b_expected(b2b):
    _, result = b2b
    case = result.value.valuation.cases["expected"]
    m = case.multiple
    y1 = case.years[0]
    assert m.year1_ebitda == y1.ebitda == D("109989.84")
    assert m.ebitda_margin == D("0.0917")
    assert m.enterprise_value == m.year1_ebitda * 4 == D("439959.36")
    assert m.equity_value == D("634953.86")


def test_break_even_by_hand_on_b2b_expected(b2b):
    s, result = b2b
    model = financial_model(s.gateway.store, s.actor.business_id, SEP, include_monthly=True).value
    months = model.cases["expected"].monthly
    margin = (100 - model.cases["expected"].cost_of_sales_pct) / 100  # 81.95%
    be = result.value.break_even.cases["expected"]
    assert be.gross_margin == margin == D("0.8195")
    fixed = sum((m.pnl.total_operating_expenses for m in months[:12]), D(0)) / 12
    year1 = be.years[0]
    assert year1.break_even_monthly_sales == r2(fixed / margin) == D("90398.67")
    assert year1.avg_monthly_sales == D("99930.88")
    assert year1.headroom == D("9532.21")
    assert be.first_month_reached == "2026-10" and be.months_below == 0
    first = be.monthly[0]
    assert first.break_even_sales == r2(months[0].pnl.total_operating_expenses / margin)


def test_cash_crunch_expected_never_breaks_even_and_has_no_meaningful_value(crunch):
    _, result = crunch
    be = result.value.break_even.cases["expected"]
    assert be.first_month_reached is None and be.months_below == 36
    assert "below break-even for all 3 years" in be.status
    assert be.years[0].break_even_monthly_sales == D("129721.65")
    case = result.value.valuation.cases["expected"]
    assert case.dcf.equity_value is None and case.dcf.terminal_value is None
    assert "-S$48,104.67" in case.dcf.not_meaningful
    assert case.multiple.year1_ebitda == D("470.28") and case.multiple.ebitda_margin == D("0.0003")
    assert (
        case.multiple.equity_value is None and "under 2% of sales" in case.multiple.not_meaningful
    )
    assert all(c.equity_value is None for c in case.sensitivity.discount_rate_pct)
    # Best case: a value, mostly after year 3, so warned.
    best = result.value.valuation.cases["best"]
    assert best.dcf.equity_value == D("1152458.86") and best.dcf.terminal_share == D("0.6715")
    assert any(w.startswith("Best case: 67% of the DCF value") for w in result.warnings)
    assert not any(w.startswith("Expected case:") for w in result.warnings)
    assert result.value.valuation.book_equity == D("275619.06")


def test_worst_case_loss_gives_not_meaningful_multiple(crunch):
    _, result = crunch
    m = result.value.valuation.cases["worst"].multiple
    assert m.year1_ebitda < 0 and m.equity_value is None and "loss" in m.not_meaningful


def test_today_shows_both_bases_without_mixing(crunch):
    s, result = crunch
    today = result.value.break_even
    health = break_even_sales(s.gateway.store, s.actor.business_id, SEP).value
    assert today.today_cash.basis == "cash"
    assert today.today_cash.break_even_monthly_sales == health.break_even_monthly_sales
    assert today.today_cash.headroom == health.headroom == D("8203.85")
    acc = today.today_accrual
    assert acc.basis == "accrual" and acc.period_start == date(2025, 10, 1)
    assert acc.gross_margin == D("0.4937") and acc.avg_monthly_fixed_costs == D("63997.84")
    assert acc.break_even_monthly_sales == r2(D("767974.09") / 12 / D("0.4937")) == D("129629.01")
    assert acc.headroom == D("-2658.64")  # below on accrual, above on cash


# --- Order of the cases ----------------------------------------------------------------------


@pytest.mark.parametrize("folder", [CRUNCH, B2B, INJECTION, MESSY])
def test_worst_expected_best_order(folder):
    v = value(session(folder)).value
    be = [v.break_even.cases[c] for c in CASES]
    for w, e, b in zip(*(c.monthly for c in be), strict=True):
        assert w.break_even_sales >= e.break_even_sales >= b.break_even_sales
        assert w.sales - w.break_even_sales <= e.sales - e.break_even_sales
        assert e.sales - e.break_even_sales <= b.sales - b.break_even_sales
    val = [v.valuation.cases[c] for c in CASES]
    for i in range(3):
        assert val[0].years[i].free_cash_flow <= val[1].years[i].free_cash_flow
        assert val[1].years[i].free_cash_flow <= val[2].years[i].free_cash_flow
        assert val[0].years[i].ebitda <= val[1].years[i].ebitda <= val[2].years[i].ebitda
    values = [c.dcf.enterprise_value for c in val]
    shown = [x for x in values if x is not None]
    assert shown == sorted(shown)
    assert values[2] is not None  # Best always has a value on our fixtures
    if values[0] is not None:
        assert values[1] is not None  # meaningful in Worst => meaningful in Expected


def test_sensitivity_rows_hold_the_headline_and_move_the_right_way(b2b):
    _, result = b2b
    case = result.value.valuation.cases["expected"]
    sens = case.sensitivity
    assert [c.input for c in sens.discount_rate_pct] == [15, 20, 25]
    assert [c.input for c in sens.terminal_growth_pct] == [0, 2, 3]
    assert [c.input for c in sens.ebitda_multiple] == [3, 4, 5]
    assert sens.discount_rate_pct[1].equity_value == case.dcf.equity_value
    assert sens.terminal_growth_pct[1].equity_value == case.dcf.equity_value
    assert sens.ebitda_multiple[1].equity_value == case.multiple.equity_value
    rates = [c.equity_value for c in sens.discount_rate_pct]
    assert rates == sorted(rates, reverse=True)  # higher rate, lower value
    growth = [c.equity_value for c in sens.terminal_growth_pct]
    assert growth == sorted(growth)
    assert str(sens.discount_rate_pct[1].input) == "20"  # shown as 20, not 20.00


# --- Overrides -------------------------------------------------------------------------------


def test_discount_rate_override_matches_the_sensitivity_cell(b2b):
    s, base = b2b
    at15 = value(s, inputs=ValueInputs(discount_rate_pct=D("15"))).value.valuation
    expected = base.value.valuation.cases["expected"]
    assert at15.cases["expected"].dcf.equity_value == expected.sensitivity.discount_rate_pct[
        0
    ].equity_value == D("712649.62")  # fmt: skip
    rate = next(i for i in at15.inputs if i.key == "discount_rate_pct")
    assert rate.value == 15 and rate.source == "your figure for this question"
    default = next(i for i in base.value.valuation.inputs if i.key == "discount_rate_pct")
    assert default.source.startswith("our assumption, not data")


def test_owner_salary_lowers_ebitda_tax_and_cash_flow(b2b):
    s, base = b2b
    paid = value(s, inputs=ValueInputs(owner_salary_monthly=D("8000.00")))
    y1 = paid.value.valuation.cases["expected"].years[0]
    before = base.value.valuation.cases["expected"].years[0]
    assert y1.owner_salary == D("96000.00")
    assert y1.ebitda == before.ebitda - 96000
    assert y1.operating_profit == D("-2260.16") and y1.tax == 0  # 93,739.84 - 96,000
    assert y1.free_cash_flow == D("106899.69") - 96000 == D("10899.69")
    assert not any("No owner salary deducted" in w for w in paid.warnings)
    assert any("No owner salary deducted" in w for w in base.warnings)


def test_model_drivers_pass_through(crunch):
    s, _ = crunch
    grown = value(s, model_inputs=ModelInputs(sales_growth_pct=D("10"))).value
    growth = next(d for d in grown.valuation.model_drivers if d.key == "sales_growth_pct")
    assert growth.expected == 10 and growth.source == "your figure for this question"
    assert grown.break_even.cases["expected"].first_month_reached == "2026-10"


def test_bad_inputs_are_refused(crunch):
    s, _ = crunch
    with pytest.raises(ValueError, match="must be below the discount rate"):
        value(s, inputs=ValueInputs(discount_rate_pct=D("5"), terminal_growth_pct=D("5")))
    for bad in (
        {"discount_rate_pct": D("4")},
        {"terminal_growth_pct": D("6")},
        {"ebitda_multiple": D("11")},
        {"owner_salary_monthly": D("-1.00")},
    ):
        with pytest.raises(ValidationError):
            ValueInputs(**bad)


def test_no_accrual_books_gives_the_reason():
    r = value(session(SAMPLE))
    assert r.value is None and r.warnings


def test_model_numbers_unchanged(crunch):
    s, _ = crunch
    model = financial_model(s.gateway.store, s.actor.business_id, SEP).value
    outlook = model.cases["expected"].outlook
    assert outlook.net_profit_by_year[0] == D("-21818.79")
    assert outlook.cash_end_of_year[2] == D("2454.35")


# --- Tool, mock route, API -------------------------------------------------------------------


def test_tool_filters_case_and_part_and_hides_monthly_points():
    s = session(B2B, Role.VIEWER)
    gw, actor = s.gateway, s.actor
    r = gw.call(actor, "get_break_even_and_value", {"case": "expected", "part": "valuation"})
    assert r.ok, r.message
    v = r.data.value
    assert v.break_even is None and set(v.valuation.cases) == {"expected"}
    r = gw.call(actor, "get_break_even_and_value", {"part": "break_even"})
    assert r.data.value.valuation is None
    assert all(c.monthly == [] for c in r.data.value.break_even.cases.values())
    r = gw.call(actor, "get_break_even_and_value", {"monthly": True})
    assert all(len(c.monthly) == 36 for c in r.data.value.break_even.cases.values())
    bad = gw.call(
        actor, "get_break_even_and_value", {"discount_rate_pct": "5", "terminal_growth_pct": "5"}
    )
    assert not bad.ok and "below the discount rate" in bad.message


def test_mock_routes_value_questions_and_keeps_plain_break_even_on_health():
    s = session(B2B)
    reply = handle("What is the business worth?", s)
    assert "Estimated value" in reply.text and "not a price" in reply.text
    assert "S$576,789.10" in reply.text
    corrected = handle("Use a 15% discount rate instead.", s)
    assert "S$712,649.62" in corrected.text
    plain = handle("How much do we need to sell each month to break even?", session(CRUNCH))
    assert "Debt service cover" in plain.text
    when = handle("When will we break even?", session(CRUNCH))
    assert "below break-even for all 3 years" in when.text


def test_valuation_endpoint():
    from test_api import signed_in

    c = signed_in("viewer", scenario="concentrated_b2b")
    d = c.get("/api/valuation").json()
    assert d["ok"], d["message"]
    v = d["data"]["value"]
    assert len(v["break_even"]["cases"]["expected"]["monthly"]) == 36  # chart line
    card = v["valuation"]
    assert card["cases"]["expected"]["dcf"]["equity_value"] == "576789.10"  # money as text
    assert {i["key"] for i in card["inputs"]} >= {"discount_rate_pct", "ebitda_multiple"}
    at15 = c.get("/api/valuation", params={"discount_rate_pct": "15"}).json()
    assert at15["data"]["value"]["valuation"]["cases"]["expected"]["dcf"]["equity_value"] == (
        "712649.62"
    )
    assert not c.get(
        "/api/valuation", params={"discount_rate_pct": "5", "terminal_growth_pct": "5"}
    ).json()["ok"]
    assert c.get("/api/valuation", params={"ebitda_multiple": "x"}).status_code == 422
