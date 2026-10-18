"""Chunk 16a: cash-shock stress test.

There is no answer key for random runs, so the simulation is checked against itself and the
13-week forecast: same seed = same answer; with randomness off every run equals the forecast to
the cent; survival never rises with the shock; P10 <= P50 <= P90; the gap bridge adds up; the
largest survivable shock and extra buffer sit exactly on the target; known facts of the fixtures
(b2b survives, cash_crunch fails first on 5 Nov).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from copilot.cashflow.forecast import daily_balances, forecast_13_weeks
from copilot.cashflow.stress import RUNS, _Engine, stress_test
from copilot.runtime import open_scenario
from copilot.schemas import Role

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"
INJECTION = SYNTHETIC_DIR / "prompt_injection"
FIXTURES = [CRUNCH, B2B, INJECTION]


def session(folder=CRUNCH, role=Role.OWNER):
    return open_scenario(folder, role)


def run(s, **kwargs):
    return stress_test(s.gateway.store, s.gateway.sandbox, s.actor.business_id, **kwargs)


@pytest.fixture(scope="module")
def crunch():
    return run(session()).value


@pytest.fixture(scope="module")
def b2b():
    return run(session(B2B)).value


def test_same_seed_same_answer():
    s = session()
    assert run(s, shock_amount=D("20000"), shock_date=date(2026, 10, 15)) == run(
        s, shock_amount=D("20000"), shock_date=date(2026, 10, 15)
    )
    assert run(s, seed=7).value != run(s).value  # the seed matters


@pytest.mark.parametrize("folder", FIXTURES, ids=lambda f: f.name)
def test_without_randomness_every_run_is_the_forecast(folder):
    s = session(folder)
    fc = forecast_13_weeks(s.gateway.store, s.gateway.sandbox, s.actor.business_id)
    expected = daily_balances(fc.value)
    v = run(s, randomness=False, runs=50).value
    assert [(r.date, r.p10) for r in v.daily] == expected
    assert all(r.p10 == r.p50 == r.p90 == r.forecast for r in v.daily)


@pytest.mark.parametrize("folder", FIXTURES, ids=lambda f: f.name)
def test_percentiles_are_ordered_every_day_and_week(folder):
    v = run(session(folder), shock_amount=D("15000"), shock_date=date(2026, 11, 2)).value
    assert len(v.daily) == (v.horizon_end - v.as_of).days and v.runs == RUNS
    assert all(r.p10 <= r.p50 <= r.p90 for r in v.daily)
    assert all(w.lowest_p10 <= w.lowest_p50 <= w.lowest_p90 for w in v.weekly)


@pytest.mark.parametrize("folder", [CRUNCH, B2B], ids=lambda f: f.name)
def test_survival_never_rises_as_the_shock_grows(folder):
    s = session(folder)
    v = run(s).value
    curve = [p.survival_pct for p in v.curve]
    assert curve == sorted(curve, reverse=True) and v.curve[0].shock == 0
    day = v.shock_day_used
    previous = D("100")
    for amount in range(0, 300_001, 25_000):
        # survival only: skip 16b's plan search for the headline (speed)
        pct = run(s, shock_amount=D(amount), shock_date=day, best_plan=False)
        pct = pct.value.survival_pct
        assert pct <= previous
        previous = pct


@pytest.mark.parametrize("folder", FIXTURES, ids=lambda f: f.name)
def test_gap_bridge_adds_up_to_the_cent(folder):
    v = run(session(folder), shock_amount=D("30000"), shock_date=date(2026, 10, 20)).value
    steps = v.bridge.steps
    level = D("0")
    for step in steps:
        if step.kind == "total":
            assert step.start == 0 and step.end == step.amount
            if step.key != "cash":
                assert step.amount == level  # a total equals the steps before it
        else:
            assert step.start == level and step.end == level + step.amount
        level = step.end
    keys = [st.key for st in steps]
    assert keys[0] == "cash" and "worst" in keys and keys[-1] == "after"
    worst = next(st for st in steps if st.key == "worst")
    assert worst.amount == v.bridge.worst_likely
    assert v.bridge.gap == max(D("0"), D("30000") - v.bridge.worst_likely)
    assert v.bridge.spare == max(D("0"), v.bridge.worst_likely - D("30000"))


def test_b2b_survives_with_no_shock(b2b):
    assert b2b.survival_pct == D("100.00") and b2b.survival_without_shock_pct == D("100.00")
    assert b2b.meets_target and b2b.headline.case == "1" and b2b.plan is None
    assert b2b.failures.most_likely_day is None and b2b.extra_buffer == 0


def test_cash_crunch_fails_first_on_5_november(crunch):
    assert crunch.failures.most_likely_day == date(2026, 11, 5)  # MFI-88120's S$85k bill
    assert crunch.failures.most_likely_day_share_pct > 50
    week6 = crunch.failures.by_week[5]
    assert week6.start <= date(2026, 11, 5) <= week6.end
    assert week6.runs == max(w.runs for w in crunch.failures.by_week)
    assert crunch.shock_day_used == date(2026, 11, 5)
    assert crunch.survival_pct < 5 and not crunch.meets_target


def test_cash_crunch_headline_and_plan(crunch):
    # Without action ~S$48.5k short on 5 Nov in a bad case; chasing INV-1062 covers that day,
    # but December still fails (structural, as recommend_actions found).
    assert crunch.plan is not None and len(crunch.plan.actions) == 1
    assert "INV-1062" in crunch.plan.actions[0]
    assert crunch.plan.gap_on_shock_day == 0 and crunch.bridge.gap > 0
    assert crunch.plan.extra_buffer == D("24645.36")  # 16a's number is unchanged
    # Chunk 16b (by design): the headline uses compare_options' best plan, which adds a credit
    # line and reaches the target, so case 4 became case 2.
    assert crunch.headline.case == "2"
    assert "Without action" in crunch.headline.line1 and "S$48,533.79" in crunch.headline.line1
    assert "3 action(s)" in crunch.headline.line2 and "96.10%" in crunch.headline.line2


def _survival(s, day, amount):
    return run(s, shock_amount=amount, shock_date=day, best_plan=False).value.survival_pct


def test_largest_survivable_shock_sits_exactly_on_the_target():
    s = session(B2B)
    v = run(s, shock_amount=D("1000"), shock_date=date(2026, 11, 1)).value
    largest = v.largest_survivable_shock
    assert largest is not None and largest > 0
    day = date(2026, 11, 1)
    assert _survival(s, day, largest) >= 95
    assert _survival(s, day, largest + D("0.01")) < 95


def test_extra_buffer_sits_exactly_on_the_target():
    s = session(B2B)
    day, shock = date(2026, 11, 5), D("170000")
    v = run(s, shock_amount=shock, shock_date=day).value
    assert not v.meets_target and v.extra_buffer > 0
    # More cash today = a smaller shock as far as survival is concerned (every day shifts up).
    assert _survival(s, day, shock - v.extra_buffer) >= 95
    assert _survival(s, day, shock - v.extra_buffer + D("0.01")) < 95


def test_cash_crunch_cannot_absorb_any_shock(crunch):
    assert crunch.largest_survivable_shock is None  # it fails before any shock
    assert all(p.survival_pct == crunch.survival_pct for p in crunch.curve[:1])


def test_open_invoice_only_draws_delays_it_has_not_passed():
    s = session()
    store, bid = s.gateway.store, s.actor.business_id
    fc = forecast_13_weeks(store, s.gateway.sandbox, bid).value
    engine = _Engine(store, bid, fc, randomness=True)
    for it in fc.items:
        if it.source == "open_invoice":
            pool = engine._pool(it)
            assert pool and all(i is None or i >= 0 for i in pool)


def test_plan_reuses_the_draws_and_keeps_collected_invoices_fixed(crunch):
    # INV-1062 is collected by its due date (19 Oct) in the plan: no run should move it, so the
    # plan never fails on 5 Nov (the base fails there in most runs).
    assert crunch.plan.most_likely_failure_day != date(2026, 11, 5)


def test_bad_inputs_are_errors():
    s = session()
    with pytest.raises(ValueError, match="date"):
        run(s, shock_amount=D("1000"))
    with pytest.raises(ValueError, match="between"):
        run(s, shock_amount=D("1000"), shock_date=date(2027, 6, 1))
    with pytest.raises(ValueError, match="positive"):
        run(s, shock_amount=D("-1"), shock_date=date(2026, 10, 10))


def test_tool_through_the_gateway_for_a_viewer_writes_nothing():
    s = session(role=Role.VIEWER)
    store = s.gateway.store
    before = store.list_transactions(s.actor.business_id)
    r = s.gateway.call(
        s.actor, "stress_test_cash", {"shock_amount": "20000.00", "shock_date": "2026-10-15"}
    )
    assert r.ok, r.message
    assert r.data.value.daily == [] and len(r.data.value.weekly) == 13
    daily = s.gateway.call(s.actor, "stress_test_cash", {"include_daily": True})
    assert len(daily.data.value.daily) == 88  # 1 Oct (a Thursday) to 27 Dec
    assert store.list_transactions(s.actor.business_id) == before
    bad = s.gateway.call(s.actor, "stress_test_cash", {"shock_amount": "5000.00"})
    assert not bad.ok
    smuggled = s.gateway.call(s.actor, "stress_test_cash", {"runs": 5})
    assert not smuggled.ok  # runs and seed are not tool arguments


def test_fast_enough_for_the_agent():
    import time

    s = session()
    start = time.perf_counter()
    run(s, shock_amount=D("20000"), shock_date=date(2026, 10, 15))
    assert time.perf_counter() - start < 2
