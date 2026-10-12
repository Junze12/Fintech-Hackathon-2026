from datetime import timedelta
from decimal import Decimal

import pytest

from copilot.cashflow.alerts import (
    default_floor,
    evaluate_alerts,
    new_alerts,
    overdue_alerts,
    threshold_alert,
    urgency,
)
from copilot.cashflow.forecast import forecast_13_weeks


def truth_monthly_fixed_costs(truth) -> Decimal:
    return sum(
        -Decimal(r["amount"]) / (1 if r["cadence"] == "monthly" else 3) for r in truth["recurring"]
    )


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_default_floor_is_one_month_of_fixed_costs(load_scenario, scenario):
    s = load_scenario(scenario)
    floor = default_floor(s.store, s.business_id, s.as_of).value
    expected = truth_monthly_fixed_costs(s.truth)
    assert abs(floor - expected) / expected <= Decimal("0.05")


def test_cash_crunch_raises_critical_alert(load_scenario):
    s = load_scenario("cash_crunch")
    forecast = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    floor = default_floor(s.store, s.business_id, s.as_of).value
    result = threshold_alert(forecast, floor)
    alert = result.value
    assert alert is not None
    assert alert.severity == "critical"
    assert alert.lowest_balance < 0
    assert alert.gap_below_floor == floor - alert.lowest_balance
    assert "overdrawn" in alert.message
    # The explanation is about what first pushes cash under the floor: the S$85k bill.
    assert "MFI-88120" in result.drivers[0].label
    assert result.drivers[0].amount == Decimal("-85000.00")


def test_warning_when_above_zero_but_below_floor(load_scenario):
    s = load_scenario("concentrated_b2b")
    forecast = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    high_floor = forecast.value.low_point.balance + Decimal("1000")
    alert = threshold_alert(forecast, high_floor).value
    assert alert is not None and alert.severity == "warning"
    assert alert.lowest_balance > 0


def test_healthy_business_has_no_alert(load_scenario):
    s = load_scenario("concentrated_b2b")
    forecast = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    floor = default_floor(s.store, s.business_id, s.as_of).value
    result = threshold_alert(forecast, floor)
    assert result.value is None
    assert result.drivers == []


def test_alert_message_shows_sgd_amounts(load_scenario):
    """Regression: the message used to read 'floor of 68,771.18 ... reaching -13,260.76'."""
    s = load_scenario("cash_crunch")
    forecast = forecast_13_weeks(s.store, s.sandbox, s.business_id)
    floor = default_floor(s.store, s.business_id, s.as_of).value
    alert = threshold_alert(forecast, floor).value
    assert f"your floor of S${floor:,.2f} from" in alert.message
    assert f"reaching -S${-alert.lowest_balance:,.2f} on" in alert.message


# --- v1 alerts, ranked (4b-1) ----------------------------------------------------------


def ranked(s, floor=None):
    forecast = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    floor = floor if floor is not None else default_floor(s.store, s.business_id, s.as_of).value
    return evaluate_alerts(s.store, s.business_id, forecast, floor).value


def test_cash_crunch_shortfall_names_the_big_bill(load_scenario):
    s = load_scenario("cash_crunch")
    shortfalls = [a for a in ranked(s) if a.kind == "shortfall"]
    first = min(shortfalls, key=lambda a: a.event_date)
    assert first.event_date.isoformat() == s.truth["forward"]["first_below_zero"] == "2026-11-05"
    assert "Bill MFI-88120" in first.message and "S$85,000.00" in first.message
    assert first.severity == "critical"
    tolerance = Decimal(s.truth["forward"]["tolerance"])
    truth_low = -Decimal(s.truth["forward"]["low_point"]["balance"])
    assert abs(first.impact - truth_low) <= tolerance  # S$9.6k short vs S$18.1k in the truth


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_overdue_alerts_match_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    overdue = [a for a in ranked(s) if a.kind == "overdue_receivable"]
    assert sorted(a.key.removeprefix("overdue:") for a in overdue) == s.truth["overdue_invoices"]


def test_overdue_within_usual_delay_is_info_later_is_warning(load_scenario):
    s = load_scenario("cash_crunch")
    [inv] = [a for a in overdue_alerts(s.store, s.business_id, s.as_of)]
    assert inv.severity == "info" and "normal for them" in inv.message  # 11 days, usual 22
    later = s.as_of + timedelta(days=30)  # 41 days overdue > 22 + 7
    [inv] = [a for a in overdue_alerts(s.store, s.business_id, later) if a.key == inv.key]
    assert inv.severity == "warning" and "later than usual" in inv.message


def test_ranking_is_severity_first_then_score(load_scenario):
    alerts = ranked(load_scenario("cash_crunch"))
    order = {"critical": 0, "warning": 1, "info": 2}
    assert [order[a.severity] for a in alerts] == sorted(order[a.severity] for a in alerts)
    assert alerts[0].kind == "threshold"
    assert "MFI-88120" in alerts[1].message  # the S$85k bill before later, smaller dips
    criticals = [a.score for a in alerts if a.severity == "critical"]
    assert criticals == sorted(criticals, reverse=True)
    # An info note never outranks a critical alert, even with a bigger score.
    info = next(a for a in alerts if a.severity == "info")
    assert info.score > alerts[1].score and alerts.index(info) > 1


def test_urgency_falls_off_after_a_week():
    assert urgency(0) == urgency(7) == Decimal("1")
    assert urgency(14) == Decimal("0.5") and urgency(28) == Decimal("0.25")


def test_new_alerts_reports_new_keys_and_escalations(load_scenario):
    s = load_scenario("cash_crunch")
    before = ranked(s)
    assert new_alerts(before, before) == []
    downgraded = [a.model_copy(update={"severity": "info"}) for a in before]
    assert {a.key for a in new_alerts(downgraded, before)} == {
        a.key for a in before if a.severity != "info"
    }
    assert new_alerts(before[1:], before) == [before[0]]


def test_healthy_business_only_gets_overdue_notes(load_scenario):
    alerts = ranked(load_scenario("concentrated_b2b"))
    assert {a.kind for a in alerts} == {"overdue_receivable"}
