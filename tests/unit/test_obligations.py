"""Obligations calendar: known money in and out over the next weeks, from the forecast."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from copilot.cashflow.forecast import daily_balances, forecast_13_weeks
from copilot.cashflow.obligations import obligations_calendar


@pytest.fixture
def crunch(load_scenario):
    s = load_scenario("cash_crunch")
    return s, forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)


def test_default_is_four_weeks_of_known_items(crunch):
    s, forecast = crunch
    cal = obligations_calendar(forecast).value
    assert (cal.start, cal.end) == (date(2026, 10, 1), date(2026, 10, 28))
    assert all(cal.start <= r.date <= cal.end for r in cal.items)
    assert {r.source for r in cal.items} <= {"open_bill", "recurring", "open_invoice"}
    labels = [r.label for r in cal.items]
    assert any("BL-5048" in label for label in labels)  # open bill, due 10-03
    assert any(label.startswith("rent") for label in labels)
    assert not any(label.startswith("Expected") for label in labels)  # projections left out


def test_certainty_and_amounts_come_from_the_forecast(crunch):
    _, forecast = crunch
    cal = obligations_calendar(forecast, weeks=2).value
    bill = next(r for r in cal.items if "BL-5048" in r.label)
    assert (bill.amount, bill.certainty, bill.kind) == (Decimal("-61898.43"), "due", "payment")
    receipt = next(r for r in cal.items if "INV-1057" in r.label)
    assert receipt.certainty == "estimated" and receipt.kind == "receipt"
    assert receipt.date == date(2026, 10, 11)  # 7 days after as-of: already later than usual
    assert cal.total_out == sum(-r.amount for r in cal.items if r.amount < 0)
    assert cal.total_in == sum(r.amount for r in cal.items if r.amount > 0)


def test_balance_after_is_the_forecast_end_of_day_balance(crunch):
    _, forecast = crunch
    end_of_day = dict(daily_balances(forecast.value))
    for row in obligations_calendar(forecast, weeks=13).value.items:
        assert row.balance_after == end_of_day[row.date]


@pytest.mark.parametrize("weeks", [0, 14])
def test_weeks_out_of_range(crunch, weeks):
    with pytest.raises(ValueError):
        obligations_calendar(crunch[1], weeks=weeks)


def test_one_week(crunch):
    s, forecast = crunch
    cal = obligations_calendar(forecast, weeks=1).value
    assert cal.end == s.as_of + timedelta(days=7)
    assert max(r.date for r in cal.items) <= cal.end
