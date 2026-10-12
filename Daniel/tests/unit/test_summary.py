"""Cash-flow summaries: money in and out by category, per month or week (cash basis)."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pytest

from copilot.cashflow.summary import cash_summary
from copilot.schemas import TransactionCategory as Cat


@pytest.fixture
def crunch(load_scenario):
    return load_scenario("cash_crunch")


def test_monthly_totals_match_hand_sums(crunch):
    s = crunch
    result = cash_summary(s.store, s.business_id, date(2026, 7, 1), date(2026, 9, 30))
    value = result.value
    assert [(p.start, p.end) for p in value.periods] == [
        (date(2026, 7, 1), date(2026, 7, 31)),
        (date(2026, 8, 1), date(2026, 8, 31)),
        (date(2026, 9, 1), date(2026, 9, 30)),
    ]
    txns = [
        t
        for t in s.store.list_transactions(s.business_id, date(2026, 8, 1), date(2026, 8, 31))
        if t.category is not Cat.TRANSFER
    ]
    by_cat: dict[Cat, Decimal] = defaultdict(Decimal)
    for t in txns:
        by_cat[t.category] += t.amount
    august = value.periods[1]
    assert {f.category: f.amount for f in august.by_category} == {
        c: a for c, a in by_cat.items() if a != 0
    }
    assert august.inflows - august.outflows == august.net == sum(t.amount for t in txns)
    assert value.net == sum(p.net for p in value.periods)
    assert value.total_inflows - value.total_outflows == value.net
    assert result.data_coverage.record_count == sum(
        1
        for t in s.store.list_transactions(s.business_id, date(2026, 7, 1), date(2026, 9, 30))
        if t.category is not Cat.TRANSFER
    )


def test_money_in_listed_first_then_biggest_outflows(crunch):
    s = crunch
    september = cash_summary(s.store, s.business_id, date(2026, 9, 1), date(2026, 9, 30))
    flows = [f.amount for f in september.value.periods[0].by_category]
    ins = [a for a in flows if a > 0]
    outs = [a for a in flows if a < 0]
    assert flows == ins + outs
    assert outs == sorted(outs)  # most negative (biggest) first
    assert september.value.by_category[0].category is Cat.SALES


def test_transfers_between_own_accounts_are_left_out(crunch):
    s = crunch
    value = cash_summary(s.store, s.business_id, date(2025, 10, 1), date(2026, 9, 30)).value
    assert all(f.category is not Cat.TRANSFER for p in value.periods for f in p.by_category)


def test_weeks_run_monday_to_sunday_clipped_to_the_range(crunch):
    s = crunch
    value = cash_summary(s.store, s.business_id, date(2026, 9, 2), date(2026, 9, 30), "week").value
    first, *middle, last = value.periods
    assert (first.start, first.end) == (date(2026, 9, 2), date(2026, 9, 6))  # Wed to Sun
    assert all(p.start.weekday() == 0 and p.end - p.start == timedelta(days=6) for p in middle)
    assert (last.start, last.end) == (date(2026, 9, 28), date(2026, 9, 30))


def test_uncategorised_flows_are_kept_and_flagged(crunch):
    s = crunch
    result = cash_summary(s.store, s.business_id, date(2026, 6, 1), date(2026, 8, 31))
    uncategorised = [
        t
        for t in s.store.list_transactions(s.business_id, date(2026, 6, 1), date(2026, 8, 31))
        if t.category is Cat.UNCATEGORISED
    ]
    if uncategorised:
        assert any("not categorised" in w for w in result.warnings)
        assert any(f.category is Cat.UNCATEGORISED for f in result.value.by_category)


def test_empty_range_says_so_and_bad_ranges_are_rejected(crunch):
    s = crunch
    result = cash_summary(s.store, s.business_id, date(2030, 1, 1), date(2030, 1, 31))
    assert result.value.net == 0 and "No transactions" in result.warnings[0]
    with pytest.raises(ValueError):
        cash_summary(s.store, s.business_id, date(2026, 9, 30), date(2026, 9, 1))
    with pytest.raises(ValueError, match="limit"):
        cash_summary(s.store, s.business_id, date(2020, 1, 1), date(2026, 9, 30), "week")
