"""Forecast tests, scored against the synthetic answer keys.

Scoring is outcome-based (agreed 2026-10-03): the forecast estimates customer habits from noisy
history, so a payment can land a day or two away from the true date and cross a week boundary.
We therefore score what the user relies on, not every single week:
  1. the first day cash goes below zero (within 7 days of the true date),
  2. the lowest balance in the 13 weeks (within the answer key's tolerance),
  3. the average weekly error (within the tolerance).
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from copilot.cashflow.forecast import daily_balances, forecast_13_weeks
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    Account,
    Bill,
    Business,
    Counterparty,
    CounterpartyKind,
    Transaction,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

SCENARIOS = ["cash_crunch", "concentrated_b2b"]


def first_below_zero(forecast):
    return next((d for d, b in daily_balances(forecast) if b < 0), None)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_week_structure(load_scenario, scenario):
    s = load_scenario(scenario)
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id).value
    assert len(fc.weeks) == 13
    assert fc.weeks[0].start == date(2026, 9, 28)
    assert all(w.start.weekday() == 0 and w.end - w.start == timedelta(days=6) for w in fc.weeks)
    assert fc.start_balance == Decimal(s.truth["forward"]["start_balance"])


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_first_day_below_zero(load_scenario, scenario):
    s = load_scenario(scenario)
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id).value
    truth = s.truth["forward"]["first_below_zero"]
    ours = first_below_zero(fc)
    if truth is None:
        assert ours is None
    else:
        assert ours is not None
        assert abs((ours - date.fromisoformat(truth)).days) <= 7


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_lowest_balance_within_tolerance(load_scenario, scenario):
    s = load_scenario(scenario)
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id).value
    truth_low = Decimal(s.truth["forward"]["low_point"]["balance"])
    tolerance = Decimal(s.truth["forward"]["tolerance"])
    assert abs(fc.low_point.balance - truth_low) <= tolerance


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_average_weekly_error_within_tolerance(load_scenario, scenario):
    s = load_scenario(scenario)
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id).value
    truth_weeks = s.truth["forward"]["weeks"]
    errors = [
        abs(ours.end_balance - Decimal(t["end_balance"]))
        for ours, t in zip(fc.weeks, truth_weeks, strict=True)
    ]
    assert sum(errors) / len(errors) <= Decimal(s.truth["forward"]["tolerance"])


def test_cash_crunch_names_the_big_bill(load_scenario):
    s = load_scenario("cash_crunch")
    result = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    breach_day = first_below_zero(result.value)
    on_that_day = sorted(
        (it for it in result.value.items if it.date == breach_day), key=lambda it: it.amount
    )
    assert "MFI-88120" in on_that_day[0].label
    assert on_that_day[0].amount == Decimal("-85000.00")


def test_assumptions_and_drivers_are_explained(load_scenario):
    s = load_scenario("cash_crunch")
    result = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    text = " ".join(result.value.assumptions)
    assert "average delay" in text and "Recurring costs" in text
    assert result.drivers and all(d.amount is not None for d in result.drivers)


def test_forecast_does_not_change_the_store(load_scenario):
    s = load_scenario("concentrated_b2b")
    before = s.store.list_transactions(s.business_id), s.store.list_bills(s.business_id)
    forecast_13_weeks(s.store, s.sandbox, s.business_id)
    after = s.store.list_transactions(s.business_id), s.store.list_bills(s.business_id)
    assert before == after


def test_thin_data_uses_only_scheduled_items():
    store = Store(":memory:")
    store.add_business(
        Business(
            id="b1",
            name="New Co",
            uen="1",
            industry="x",
            incorporated_on=date(2026, 9, 1),
            employee_count=2,
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
            opening_balance=Decimal("10000"),
            opening_date=date(2026, 9, 1),
        )
    )
    store.add_counterparty(
        Counterparty(id="s1", business_id="b1", name="Supplier", kind=CounterpartyKind.SUPPLIER)
    )
    for i, day in enumerate((5, 12, 19)):  # three weeks of history
        store.add_transaction(
            Transaction(
                id=f"t{i}",
                business_id="b1",
                account_id="a1",
                date=date(2026, 9, day),
                amount=Decimal("-500"),
                description="Rent",
                category=Cat.RENT,
            )
        )
    store.add_document(
        "bill",
        Bill(
            id="b-1",
            business_id="b1",
            counterparty_id="s1",
            number="B1",
            issue_date=date(2026, 9, 20),
            due_date=date(2026, 10, 20),
            amount=Decimal("2000"),
        ),
    )
    result = forecast_13_weeks(store, Sandbox(store), "b1", as_of=date(2026, 9, 30))
    assert {it.source for it in result.value.items} == {"open_bill"}
    assert any("Less than 8 weeks" in w for w in result.warnings)
