"""Financing (chunk 4c): catalogue, eligibility, costs and EIR, needs and ranking.

Cost figures are checked by hand: an annuity's instalment against the textbook formula, a
flat rate against its known effective rate, and XIRR against a one-year 10% loan.
"""

from datetime import date
from decimal import Decimal

import pytest

from copilot.analysis.metrics import period_metrics
from copilot.cashflow.forecast import forecast_13_weeks
from copilot.cashflow.recommend import FundingNeed
from copilot.financing.catalogue import load_catalogue, parse_catalogue
from copilot.financing.costs import quote, xirr
from copilot.financing.eligibility import business_facts, check
from copilot.financing.ranking import match_financing
from copilot.schemas import EligibilityMetric, FinancingProduct

D = Decimal
CATALOGUE = load_catalogue()


def need(amount, months, days=None, lower_bound=False):
    return FundingNeed(
        amount=D(amount),
        target=D("0"),
        draw_date=date(2026, 11, 2),
        repay_date=None,
        duration_days=days or months * 30,
        duration_months=months,
        duration_is_lower_bound=lower_bound,
        purpose="test",
        basis="stated by the user",
    )


def variant(product_id, **changes):
    base = CATALOGUE.get(product_id).model_dump()
    return FinancingProduct.model_validate({**base, "id": "t-" + product_id, **changes})


# --- catalogue ---------------------------------------------------------------------


def test_catalogue_loads_seven_products():
    assert len(CATALOGUE.products) == 7 and CATALOGUE.rejected == []
    assert "fictional" in CATALOGUE.disclaimer and "lender's decision" in CATALOGUE.disclaimer


def test_bad_entries_are_rejected_with_reasons():
    good = CATALOGUE.get("micro").model_dump(mode="json")
    personal = {
        **good,
        "id": "bad-rule",
        "eligibility_rules": [
            {"metric": "owner_age", "operator": ">=", "threshold": "21", "description": "x"}
        ],
    }
    ranges = {**good, "id": "bad-range", "min_amount": "900000.00"}
    cat = parse_catalogue({"products": [good, personal, ranges, good]})
    assert [p.id for p in cat.products] == ["micro"]
    reasons = {r.raw["id"]: r.reason for r in cat.rejected}
    assert "metric" in reasons["bad-rule"]
    assert "min_amount" in reasons["bad-range"]
    assert reasons["micro"] == "duplicate id"


def test_no_personal_characteristics_can_be_checked():
    personal = {"age", "gender", "nationality", "religion", "race", "marital", "citizenship"}
    for metric in EligibilityMetric:
        assert not personal & set(metric.value.split("_")), metric


# --- eligibility -------------------------------------------------------------------


@pytest.fixture
def crunch(load_scenario):
    return load_scenario("cash_crunch")


def test_facts_come_from_the_records(crunch):
    s = crunch
    facts = business_facts(s.store, s.sandbox, s.business_id, s.as_of).value
    year = period_metrics(s.store, s.business_id, date(2025, 10, 1), s.as_of).value
    assert facts.value(EligibilityMetric.MONTHS_OPERATING) == 99  # since 2018-06-11
    assert facts.value(EligibilityMetric.EMPLOYEE_COUNT) == 14
    assert facts.value(EligibilityMetric.LOCAL_SHAREHOLDING_PCT) == 70
    assert facts.value(EligibilityMetric.ANNUAL_REVENUE) == year.revenue
    assert facts.value(EligibilityMetric.GROSS_MARGIN) == year.gross_margin
    assert facts.value(EligibilityMetric.REGISTERED_IN_SG) is True
    open_invoices = s.store.list_invoices(s.business_id)
    assert facts.financeable_receivables == sum(
        i.amount - i.amount_paid for i in open_invoices if i.status.value == "open"
    )


def test_failing_rule_gives_a_plain_reason(crunch):
    s = crunch
    facts = business_facts(s.store, s.sandbox, s.business_id, s.as_of).value
    micro = check(CATALOGUE.get("micro"), facts)
    assert not micro.eligible
    assert micro.reasons == ["employees: 14 staff; needs at most 10 staff"]
    assert check(CATALOGUE.get("wc-efs"), facts).eligible


def test_unknown_fact_means_not_eligible(crunch):
    s = crunch
    facts = business_facts(s.store, s.sandbox, s.business_id, s.as_of).value
    unknown = facts.model_copy(
        update={
            "facts": [
                f.model_copy(update={"value": None})
                if f.metric is EligibilityMetric.ANNUAL_REVENUE
                else f
                for f in facts.facts
            ]
        }
    )
    result = check(CATALOGUE.get("term"), unknown)
    assert not result.eligible and "can't verify annual revenue" in result.reasons[0]


def test_invoice_financing_is_capped_by_receivables(crunch):
    s = crunch
    facts = business_facts(s.store, s.sandbox, s.business_id, s.as_of).value
    result = check(CATALOGUE.get("invoice"), facts)
    assert result.max_amount == (facts.financeable_receivables * D("0.8")).quantize(D("0.01"))


# --- costs and EIR -----------------------------------------------------------------


def test_xirr_of_a_one_year_ten_percent_loan():
    flows = [(date(2026, 1, 1), D("1000")), (date(2027, 1, 1), D("-1100"))]
    assert abs(xirr(flows) - D("0.10")) < D("0.0000001")


def test_reducing_balance_annuity_matches_the_formula():
    product = variant("wc-efs", fees=[], min_amount="1000.00")
    q = quote(product, need("12000.00", 12))
    r = D("0.075") / 12
    assert q.instalment == (D("12000") * r / (1 - (1 + r) ** -12)).quantize(D("0.01"))
    assert q.instalment == D("1041.09")
    assert sum(f.principal for f in q.flows if f.kind == "repayment") == D("12000.00")
    assert q.total_cost == q.total_interest == D("493.07")
    assert D("7.70") <= q.eir_pct <= D("7.85")  # (1 + 0.075/12)^12 - 1 = 7.76%, by calendar days


def test_flat_rate_costs_much_more_than_it_sounds():
    q = quote(variant("term", fees=[]), need("50000.00", 12))
    assert q.total_interest == D("2750.00")  # 50,000 x 5.5% x 1 year
    assert D("10.3") <= q.eir_pct <= D("10.6")  # a 5.5% flat rate is about 10.5% effective


def test_fees_are_grossed_up_and_included_in_the_cost():
    q = quote(CATALOGUE.get("revolver"), need("13260.76", 1, days=22))
    assert q.amount_received == D("13260.76")  # the need, after the S$500 admin fee
    assert q.amount == D("13760.76") and q.upfront_fees == D("500.00")
    interest = (q.amount * D("0.095") * 30 / 365).quantize(D("0.01"))  # at least 30 days
    assert q.total_interest == interest and q.total_cost == interest + D("500.00")
    assert any("at least 30 days" in f for f in q.flags)


def test_total_cost_is_what_is_paid_minus_what_is_received():
    for product in CATALOGUE.products:
        q = quote(product, need("40000.00", 6))
        paid = -sum(f.amount for f in q.flows if f.kind != "draw")
        assert paid - q.amount == q.total_cost, product.id


def test_over_borrowing_and_term_flags():
    q = quote(CATALOGUE.get("term"), need("13260.76", 1, lower_bound=True))
    assert q.amount == D("50000.00")
    joined = " ".join(q.flags)
    assert "Minimum loan is S$50,000.00" in joined
    assert "Shortest term is 12 months" in joined
    assert "may need it for longer" in joined
    longest = quote(CATALOGUE.get("invoice"), need("50000.00", 6))
    assert any("Longest term is 4 months" in f for f in longest.flags)


def test_early_repayment_fee_is_disclosed_not_priced():
    q = quote(CATALOGUE.get("wc-efs"), need("30000.00", 12))
    assert q.notes == ["Early repayment fee: 1% of the amount repaid early."]
    assert q.upfront_fees == (q.amount * D("0.01")).quantize(D("0.01"))


# --- needs and ranking -------------------------------------------------------------


@pytest.fixture
def crunch_match(crunch):
    s = crunch
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    return match_financing(s.store, s.sandbox, s.business_id, fc).value


def test_need_comes_from_the_forecast_after_the_non_borrowing_plan(crunch_match):
    n = crunch_match.need
    assert n.source == "forecast" and n.need.amount == D("13025.81")
    assert n.need.draw_date == date(2026, 12, 6)
    assert any("INV-1062" in step for step in n.plan_steps)


def test_ineligible_products_are_never_ranked(crunch_match):
    ranked = {r.quote.product_id for r in crunch_match.ranked}
    not_eligible = {e.product_id for e in crunch_match.eligibility if not e.eligible}
    assert not_eligible == {"micro"} and not ranked & not_eligible
    assert ranked | not_eligible == {p.id for p in CATALOGUE.products}


def test_ranking_keeps_cash_above_zero_first_then_cheapest(crunch_match):
    ranked = crunch_match.ranked
    assert ranked[0].quote.product_id == "trade"
    keys = [(not r.keeps_cash_above_target, r.quote.total_cost) for r in ranked]
    assert keys == sorted(keys)
    assert all(r.lowest_with_loan >= 0 for r in ranked if r.keeps_cash_above_target)


def test_message_discloses_cost_rate_and_never_promises_approval(crunch_match):
    m = crunch_match.message
    assert "total cost S$169.52" in m and "effective annual rate 16.44%" in m
    assert "Approval is the lender's decision" in m
    assert "approved" not in m.lower() and "guarantee" not in m.lower()


def test_no_gap_means_borrowing_is_not_needed(load_scenario):
    s = load_scenario("concentrated_b2b")
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    match = match_financing(s.store, s.sandbox, s.business_id, fc).value
    assert match.need.need is None and match.ranked == []
    assert "borrowing is not needed" in match.message


def test_user_stated_need(load_scenario):
    s = load_scenario("concentrated_b2b")
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    match = match_financing(
        s.store, s.sandbox, s.business_id, fc, amount=D("50000.00"), months=6
    ).value
    assert match.need.source == "user" and match.need.need.duration_months == 6
    assert "no cash gap" in match.need.message
    assert all(r.quote.amount_received >= D("50000.00") for r in match.ranked)
    only_amount = match_financing(s.store, s.sandbox, s.business_id, fc, amount=D("50000.00"))
    assert only_amount.value.need.need is None
    assert "how long" in only_amount.value.message


def test_too_large_a_need_is_explained_per_product(crunch):
    s = crunch
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    match = match_financing(s.store, s.sandbox, s.business_id, fc, amount=D("500000.00")).value
    assert [r.quote.product_id for r in match.ranked] == ["trade"]
    revolver = next(e for e in match.eligibility if e.product_id == "revolver")
    assert not revolver.eligible and "can lend at most S$150,000.00" in revolver.reasons[0]
