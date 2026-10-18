import re
from datetime import date
from decimal import Decimal

import pytest

from copilot.analysis.metrics import period_metrics, runway
from copilot.cashflow.position import cash_position
from copilot.dates import add_months, clamp_day
from copilot.sandbox.bank import Sandbox
from copilot.schemas import Account, Business, Transaction
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store


def month_bounds(key: str) -> tuple[date, date]:
    year, month = (int(p) for p in key.split("-"))
    return date(year, month, 1), clamp_day(year, month, 31)


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_monthly_revenue_and_cogs_match_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    for month, totals in s.truth["monthly_totals"].items():
        start, end = month_bounds(month)
        m = period_metrics(s.store, s.business_id, start, end).value
        truth_rev = Decimal(totals["by_group"].get("revenue", "0"))
        truth_cogs = -Decimal(totals["by_group"].get("cogs", "0"))
        assert m.revenue == truth_rev, month
        assert m.cogs == truth_cogs, month
        if truth_rev:
            expected = ((truth_rev - truth_cogs) / truth_rev).quantize(Decimal("0.0001"))
            assert m.gross_margin == expected, month


def test_metrics_report_basis_and_uncategorised(load_scenario):
    s = load_scenario("cash_crunch")
    result = period_metrics(s.store, s.business_id, date(2025, 10, 1), date(2026, 9, 30))
    assert result.value.basis == "cash"
    assert result.value.uncategorised_count > 0
    assert any("uncategorised" in w for w in result.warnings)
    assert any(re.search(r"\(net -?S\$[\d,]+\.\d{2}\)", w) for w in result.warnings)
    assert any("Cash basis" in w for w in result.warnings)
    assert result.data_coverage.record_count == len(s.truth["true_category"])


def test_no_revenue_means_no_margins(load_scenario):
    s = load_scenario("cash_crunch")
    result = period_metrics(s.store, s.business_id, date(2020, 1, 1), date(2020, 1, 31))
    assert result.value.gross_margin is None and result.value.operating_margin is None
    assert any("No revenue" in w for w in result.warnings)


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_runway_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = runway(s.store, s.sandbox, s.business_id)
    cash = sum(Decimal(v) for v in s.truth["closing_balances"].values())
    net = sum(
        Decimal(v)
        for month in ("2026-07", "2026-08", "2026-09")
        for category, v in s.truth["monthly_totals"][month]["by_category"].items()
        if category != "transfer"
    )
    avg = (net / 3).quantize(Decimal("0.01"))
    assert result.value.cash == cash
    assert result.value.avg_monthly_net_flow == avg
    if avg >= 0:
        assert result.value.status == "cash-flow positive" and result.value.months is None
    else:
        assert result.value.status == "burning cash"
        assert result.value.months == (cash / -avg).quantize(Decimal("0.1"))


def test_runway_hides_the_crunch(load_scenario):
    """Documented insight: average burn says 'years of runway' while the forecast says
    the account goes negative in 5 weeks. Timing matters; the forecast is the tool for it."""
    s = load_scenario("cash_crunch")
    assert runway(s.store, s.sandbox, s.business_id).value.months > 24
    assert s.truth["forward"]["first_below_zero"] == "2026-11-05"


def test_runway_for_a_loss_making_business():
    store = Store(":memory:")
    store.add_business(
        Business(
            id="b1",
            name="Burn Co",
            uen="1",
            industry="x",
            incorporated_on=date(2020, 1, 1),
            employee_count=1,
            local_shareholding_pct=Decimal("100"),
        )
    )
    store.add_account(
        Account(
            id="a1",
            business_id="b1",
            name="Main",
            bank_name="Bank",
            account_number="1234",
            opening_balance=Decimal("30000"),
            opening_date=date(2026, 6, 1),
        )
    )
    for i in range(3):
        store.add_transaction(
            Transaction(
                id=f"t{i}",
                business_id="b1",
                account_id="a1",
                date=add_months(date(2026, 7, 15), i),
                amount=Decimal("-5000"),
                description="Payroll",
                category=Cat.PAYROLL,
            )
        )
    sandbox = Sandbox(store)
    result = runway(store, sandbox, "b1", as_of=date(2026, 9, 30))
    # 15,000 cash left, burning 5,000 a month -> 3 months.
    assert result.value.status == "burning cash"
    assert result.value.cash == Decimal("15000.00")
    assert result.value.avg_monthly_net_flow == Decimal("-5000.00")
    assert result.value.months == Decimal("3.0")


def test_cash_position_hides_account_numbers(load_scenario):
    s = load_scenario("cash_crunch")
    result = cash_position(s.store, s.sandbox, s.business_id)
    assert result.value.total == sum(Decimal(v) for v in s.truth["closing_balances"].values())
    dumped = result.model_dump_json()
    for account in s.store.list_accounts(s.business_id):
        assert account.account_number.get_secret_value() not in dumped
