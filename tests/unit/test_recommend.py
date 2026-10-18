"""Recommendations and the funding need, on both scenarios and a hand-made forecast."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from copilot.cashflow.forecast import Forecast, ForecastItem, forecast_13_weeks, walk
from copilot.cashflow.recommend import (
    find_gaps,
    funding_need,
    recommend_actions,
)
from copilot.schemas import DataCoverage, DomainResult

D = Decimal


@pytest.fixture
def crunch(load_scenario):
    s = load_scenario("cash_crunch")
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    return s, fc, recommend_actions(s.store, s.business_id, fc)


def test_base_gaps(crunch):
    _, _, result = crunch
    gaps = result.value.gaps
    assert [(g.start, g.end, g.lowest_balance) for g in gaps] == [
        (date(2026, 11, 5), date(2026, 11, 9), D("-9376.45")),
        (date(2026, 12, 6), date(2026, 12, 10), D("-9891.21")),
        (date(2026, 12, 27), date(2026, 12, 27), D("-13025.81")),
    ]


def test_collecting_inv_1062_comes_first_and_closes_november(crunch):
    _, _, result = crunch
    options = result.value.options
    assert [o.kind for o in options] == sorted(
        (o.kind for o in options), key=["collect", "reschedule", "cut"].index
    )
    first = options[0]
    assert first.kind == "collect" and "INV-1062" in first.title
    assert first.in_plan and first.follow_up_tool == "draft_reminder"
    assert first.effect.closes == [date(2026, 11, 5)]
    # Rescheduling MFI-88120 would also close November, but the plan doesn't need it.
    mfi = next(o for o in options if "MFI-88120" in o.title)
    assert mfi.effect.closes == [date(2026, 11, 5)] and not mfi.in_plan


def test_december_still_needs_borrowing(crunch):
    _, _, result = crunch
    rec = result.value
    assert rec.borrowing_needed
    assert [g.start for g in rec.gaps_after_plan] == [date(2026, 12, 6), date(2026, 12, 27)]
    need = rec.funding_need
    assert need.amount == D("13025.81")
    assert need.draw_date == date(2026, 12, 6)
    assert need.repay_date is None and need.duration_is_lower_bound
    assert need.duration_days == 22 and need.duration_months == 1  # Dec 6 to Dec 27
    assert need.basis == "after non-borrowing plan"
    assert rec.need_without_actions.draw_date == date(2026, 11, 5)
    assert any("minimum" in w for w in result.warnings)
    assert "S$13,025.81" in rec.message


def test_no_gap_means_no_borrowing(load_scenario):
    s = load_scenario("concentrated_b2b")
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)
    rec = recommend_actions(s.store, s.business_id, fc).value
    assert rec.gaps == [] and rec.options == []
    assert not rec.borrowing_needed and rec.funding_need is None
    assert "borrowing is not needed" in rec.message


def test_buffer_raises_the_need_by_exactly_the_buffer(crunch):
    s, fc, base = crunch
    buffered = recommend_actions(s.store, s.business_id, fc, D("10000.00")).value
    assert buffered.target == D("10000.00")
    assert buffered.need_without_actions.amount - base.value.need_without_actions.amount == D(
        "10000.00"
    )


# --- hand-made forecast: cut option, and a gap that recovers within the horizon ------------

AS_OF = date(2026, 9, 30)


def handmade(items):
    weeks, low = walk(AS_OF, D("10000.00"), items)
    fc = Forecast(
        as_of=AS_OF,
        start_balance=D("10000.00"),
        weeks=weeks,
        low_point=low,
        items=items,
        assumptions=[],
    )
    cov = DataCoverage(period_start=AS_OF, period_end=AS_OF, record_count=0)
    return DomainResult[Forecast](value=fc, data_coverage=cov)


def item(day, amount, source="what_if", label="x", ref=None):
    return ForecastItem(date=day, amount=D(amount), source=source, label=label, ref=ref)


def test_pausing_marketing_closes_a_small_gap_without_borrowing(store):
    fc = handmade(
        [
            item(date(2026, 10, 12), "-3000.00", "recurring", "marketing (monthly)", "marketing"),
            item(date(2026, 10, 20), "-8000.00", label="supplier"),
            item(date(2026, 11, 12), "-3000.00", "recurring", "marketing (monthly)", "marketing"),
            item(date(2026, 11, 15), "-1000.00", label="supplier"),
            item(date(2026, 11, 30), "9000.00", label="customer"),
        ]
    )
    rec = recommend_actions(store, "biz-kopi", fc).value
    # 10,000 - 3,000 - 8,000 = -1,000 on Oct 20; -5,000 by Nov 15; back up on Nov 30.
    assert [(g.start, g.end, g.lowest_balance) for g in rec.gaps] == [
        (date(2026, 10, 20), date(2026, 11, 29), D("-5000.00")),
    ]
    cut = rec.options[0]
    assert cut.kind == "cut" and cut.in_plan and cut.amount == D("-6000.00")
    assert cut.effect.closes == [date(2026, 10, 20)]
    assert not rec.borrowing_needed and rec.funding_need is None
    assert rec.need_without_actions.amount == D("5000.00")
    assert rec.need_without_actions.repay_date == date(2026, 11, 30)


def test_funding_need_with_recovery_inside_the_horizon():
    start = AS_OF + timedelta(days=1)
    path = [(start + timedelta(days=i), D("100.00")) for i in range(91)]
    path[10] = (path[10][0], D("-500.00"))
    path[11] = (path[11][0], D("-200.00"))
    path[40] = (path[40][0], D("-50.00"))
    need = funding_need(AS_OF, path, D("0"))
    assert need.amount == D("500.00")
    assert need.draw_date == path[10][0]
    assert need.repay_date == path[41][0]
    assert need.duration_days == 31 and need.duration_months == 2
    assert not need.duration_is_lower_bound
    assert len(find_gaps(path)) == 2
