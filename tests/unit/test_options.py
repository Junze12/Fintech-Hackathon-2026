"""Chunk 16b: options under uncertainty.

No answer key exists for plans scored on random runs, so they are checked against 16a and
against themselves: "do nothing" is 16a exactly; plans share each receipt's draw; adding a free
option never makes a surviving run fail; a credit line never makes one fail; cost parts add up;
the credit line never goes past its limit and charges costs.py's interest; the frontier holds the
best plan; known facts of the fixtures (b2b needs nothing; cash_crunch needs a credit line).
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from copilot.cashflow.options import (
    NOTHING,
    Levers,
    _bands,
    _cents,
    _line,
    compare_options,
    search,
)
from copilot.cashflow.recommend import FundingNeed
from copilot.cashflow.stress import prepare, sim_runs, stress_test, verdict
from copilot.financing.catalogue import load_catalogue
from copilot.financing.costs import quote
from copilot.runtime import open_scenario
from copilot.schemas import Role

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"
INJECTION = SYNTHETIC_DIR / "prompt_injection"
FIXTURES = [CRUNCH, B2B, INJECTION]


def session(folder=CRUNCH, role=Role.OWNER):
    return open_scenario(folder, role)


def compare(s, **kwargs):
    return compare_options(s.gateway.store, s.gateway.sandbox, s.actor.business_id, **kwargs)


def searched(s, levers=None, shock=D("0"), shock_date=None, target=95):
    store, sandbox, biz = s.gateway.store, s.gateway.sandbox, s.actor.business_id
    sim = prepare(store, sandbox, biz, shock, shock_date, D("0"), None, True)
    sim_runs(sim)
    return search(store, sandbox, biz, sim, target, levers)


def subset(srch, *keys):
    by_key = {lv.key: lv for lv in srch.levers_list}
    return tuple(by_key[k] for k in keys)


def finance(srch, key):
    return next(f for f in srch.finance if f.key == key)


@pytest.fixture(scope="module")
def crunch():
    return compare(session()).value


@pytest.fixture(scope="module")
def crunch_search():
    return searched(session())


# --- Do nothing is 16a ---------------------------------------------------------------------


@pytest.mark.parametrize("folder", FIXTURES, ids=lambda f: f.name)
def test_doing_nothing_equals_the_stress_test(folder):
    s = session(folder)
    stress = stress_test(s.gateway.store, s.gateway.sandbox, s.actor.business_id).value
    srch, ranked = searched(s)
    nothing = next(p[0] for p in ranked if p[0].key == NOTHING)
    assert nothing.survival_pct == stress.survival_pct
    assert nothing.cost_vs_nothing == 0
    _, _, paths, _ = srch._score((), None, keep=True)
    bands = _bands(srch.days, [b.forecast for b in stress.daily], paths)
    assert [(b.p10, b.p50, b.p90) for b in bands] == [(b.p10, b.p50, b.p90) for b in stress.daily]


def test_doing_nothing_equals_the_stress_test_with_a_shock():
    s = session(B2B)
    day = date(2026, 11, 5)
    stress = stress_test(
        s.gateway.store, s.gateway.sandbox, s.actor.business_id, D("170000"), day
    ).value
    _, ranked = searched(s, shock=D("170000"), shock_date=day)
    nothing = next(p[0] for p in ranked if p[0].key == NOTHING)
    assert nothing.survival_pct == stress.survival_pct < 95


# --- Same draws, same answer ---------------------------------------------------------------


def test_same_seed_same_answer():
    s = session()
    assert compare(s) == compare(s)
    assert compare(s, seed=7).value != compare(s).value


def test_every_plan_uses_the_same_draw_for_the_same_receipt(crunch_search):
    srch, _ = crunch_search
    nothing = srch._subset(())[0]
    # Moving a fixed bill shifts every run by the same amounts: the receipts' draws are shared.
    moved = srch._subset(subset(srch, "reschedule:b-bulk-stock"))[0]
    shifts = {
        tuple(b - a for a, b in zip(p0, p1, strict=True))
        for p0, p1 in zip(nothing, moved, strict=True)
    }
    assert len(shifts) == 1 and any(shifts.pop())
    # Chasing that never works (0%) leaves every run exactly as it was.
    never = searched(session(), Levers(chase_on_time_pct=0))[0]
    assert never._subset(subset(never, "collect:i-0062"))[0] == nothing


def test_chasing_for_certain_reproduces_the_stress_tests_plan_check():
    s = session()
    stress = stress_test(s.gateway.store, s.gateway.sandbox, s.actor.business_id).value
    srch, _ = searched(s, Levers(chase_on_time_pct=100))
    score = srch._score(subset(srch, "collect:i-0062"), None)[0]
    assert stress.plan is not None
    assert score.survival_pct == stress.plan.survival_pct
    assert score.extra_buffer == stress.plan.extra_buffer == D("24645.36")


# --- Adding options ------------------------------------------------------------------------


def test_free_options_never_make_a_surviving_run_fail(crunch_search):
    srch, _ = crunch_search
    free = [lv for lv in srch.levers_list if lv.info.kind != "discount"]
    checked = 0
    for base in [(), *[(lv,) for lv in free]]:
        before = srch._score(base, None)[1].fails
        for lv in free:
            if lv in base:
                continue
            after = srch._score(tuple(x for x in free if x in (*base, lv)), None)[1].fails
            assert all(a is None for b, a in zip(before, after, strict=True) if b is None)
            checked += 1
    assert checked >= 2


def test_a_discount_only_hurts_runs_where_it_was_given(crunch_search):
    """The one exception: a customer who would have paid early anyway takes 2% off, so a run
    can end slightly lower. Every run that fails only because of the offer gave a discount."""
    srch, _ = crunch_search
    base = subset(srch, "reschedule:b-bulk-stock")
    line = finance(srch, "line")
    with_line = srch._score(base, line)
    discount = srch._score((*base, *subset(srch, "discount")), line)
    hurt = [
        r
        for r, (b, a) in enumerate(zip(with_line[1].fails, discount[1].fails, strict=True))
        if b is None and a is not None
    ]
    assert all(discount[1].costs["discounts"][r] > 0 for r in hurt)


def test_a_credit_line_never_makes_a_run_fail(crunch_search):
    srch, _ = crunch_search
    line = finance(srch, "line")
    for size in range(len(srch.levers_list) + 1):
        for keys in [srch.levers_list[:size]]:
            without = srch._score(tuple(keys), None)[1].fails
            with_line = srch._score(tuple(keys), line)[1].fails
            assert all(w is None for o, w in zip(without, with_line, strict=True) if o is None)


# --- Costs and the credit line -------------------------------------------------------------


def test_cost_parts_add_up_exactly(crunch):
    for plan in crunch.ranked:
        assert sum((p.amount for p in plan.cost_parts), D("0")) == plan.cost_vs_nothing
    bridge = crunch.cost_bridge
    assert bridge[-1].kind == "total" and bridge[-1].amount == crunch.best.cost_vs_nothing
    level = D("0")
    for step in bridge[:-1]:
        assert step.start == level and step.end == level + step.amount
        level = step.end
    assert level == crunch.best.cost_vs_nothing


def test_credit_line_never_goes_past_its_limit(crunch_search):
    srch, _ = crunch_search
    score, _, _, drawn = srch._score(subset(srch, "collect:i-0062"), finance(srch, "line"), True)
    limit = _cents(score.credit_line.limit)
    assert max(max(d) for d in drawn) <= limit
    assert score.credit_line.limit >= score.credit_line.needed_for_target


def test_credit_line_interest_matches_costs_py_for_a_hand_case():
    """costs.py's revolving quote (amount grossed up for the fee, drawn 30 days) charges the same
    interest as the line drawing that amount for exactly 30 days."""
    product = load_catalogue().get("revolver")
    draw = date(2026, 11, 1)
    need = FundingNeed(
        amount=D("13025.81"),
        target=D("0"),
        draw_date=draw,
        repay_date=draw + timedelta(days=30),
        duration_days=30,
        duration_months=1,
        duration_is_lower_bound=False,
        purpose="test",
        basis="stated by the user",
    )
    q = quote(product, need)
    cents = _cents(q.amount)  # S$13,525.81
    path = [-cents] * 30 + [5_000_000] * 10  # short 30 days, then cash comes in
    _, fail, peak, interest, drawn_end, _, _, _ = _line(
        path, 0, 0, None, product.annual_rate_pct / 100, 0, 0
    )
    assert fail is None and drawn_end == 0
    assert peak == cents + interest  # the interest charged on day 30 was drawn too
    assert D(interest) / 100 == q.total_interest == D("105.61")


def test_customer_loss_costs_twelve_months_of_margin():
    srch, _ = searched(session(), Levers(customer_loss_pct=100))
    score = srch._score(subset(srch, "collect:i-0062"), None)[0]
    [loss] = score.customer_loss
    assert loss.customer_id == "c-bayfront" and loss.runs_pct == 100
    assert loss.cost_if_lost > 0
    lost = next(p for p in score.cost_parts if p.key == "lost_customers")
    assert lost.amount == loss.cost_if_lost == score.cost_vs_nothing
    # Losing Bayfront drops its expected invoices, so fewer runs keep their late receipts.
    off = searched(session())[0]._score(subset(srch, "collect:i-0062"), None)[0]
    assert score.low_point == off.low_point  # "if everything works" = nobody lost


# --- Ranking, frontier, table --------------------------------------------------------------


def test_frontier_holds_the_best_plan_and_nothing_beats_a_frontier_point(crunch):
    keys = {p.key for p in crunch.frontier}
    assert crunch.best.meets_target and crunch.best.key in keys
    for p in crunch.frontier:
        assert not any(
            o.survival_pct >= p.survival_pct
            and o.cost_vs_nothing <= p.cost
            and (o.survival_pct > p.survival_pct or o.cost_vs_nothing < p.cost)
            for o in crunch.ranked
        )


def test_cash_crunch_best_plan_needs_a_credit_line(crunch):
    best = crunch.best
    assert best.key == "collect:i-0062+reschedule:b-bulk-stock+line"
    assert best.survival_pct == D("96.10") and best.cost_vs_nothing == D("521.98")
    assert best.credit_line.limit == D("29000.00") and not best.credit_line.capped
    assert [p.amount for p in best.cost_parts if p.amount] == [D("500.00"), D("21.98")]
    # Without borrowing no plan survives: the 27 Dec payroll is short in every run.
    assert all(p.survival_pct == 0 for p in crunch.ranked if p.financing_key is None)
    alone = next(r for r in crunch.table if r.key == "line")
    assert alone.survival_pct == D("96.30") and alone.cost_vs_nothing == D("544.75")
    assert [r.key for r in crunch.table if r.recommended] == [best.key]
    assert crunch.table[0].key == NOTHING and crunch.plans_compared == 56


def test_fixed_loans_cost_what_find_financing_says(crunch):
    """The non-borrowing plan + trade financing is priced like find_financing (S$169.52)."""
    trade = next(
        p
        for p in compare(session()).value.frontier
        if p.key == "collect:i-0062+reschedule:b-bulk-stock+loan:trade"
    )
    assert trade.cost == D("169.52") and trade.survival_pct < 95


def test_b2b_needs_nothing():
    v = compare(session(B2B)).value
    assert v.best.key == NOTHING and v.best.cost_vs_nothing == 0 and v.best.meets_target
    assert v.cost_bridge[-1].amount == 0
    assert "No action or borrowing is needed" in v.message


@pytest.mark.parametrize("folder", FIXTURES, ids=lambda f: f.name)
def test_fast_enough(folder):
    s = session(folder)
    start = time.perf_counter()
    compare(s)
    assert time.perf_counter() - start < 2


# --- Through the gateway -------------------------------------------------------------------


def test_tool_through_the_gateway_for_a_viewer_writes_nothing():
    s = session(role=Role.VIEWER)
    before = s.gateway.store.list_transactions(s.actor.business_id)
    r = s.gateway.call(s.actor, "compare_options", {"chase_on_time_pct": 80})
    assert r.ok, r.message
    assert r.data.value.levers.chase_on_time_pct == 80
    assert r.data.value.best_daily == [] and r.data.value.line_daily == []  # unless asked
    daily = s.gateway.call(s.actor, "compare_options", {"include_daily": True})
    assert len(daily.data.value.line_daily) == 88
    assert not s.gateway.call(s.actor, "compare_options", {"seed": 5}).ok  # not an argument
    assert not s.gateway.call(s.actor, "compare_options", {"chase_on_time_pct": 120}).ok
    assert s.gateway.store.list_applications(s.actor.business_id) == []
    assert s.gateway.store.list_transactions(s.actor.business_id) == before


# --- Verdict badge (Jun Ze's survives / at risk / fails) -----------------------------------


def test_verdict_states_and_the_fifty_percent_boundary():
    assert verdict(D("96.10"), True) == "survives"
    assert verdict(D("50.00"), False) == "at_risk"
    assert verdict(D("49.99"), False) == "fails"
    # The target decides "survives", not the number: a 60% target met at 60% survives.
    assert verdict(D("60.00"), True) == "survives"


def test_cash_crunch_verdicts_reach_the_json(crunch):
    assert crunch.best.model_dump()["verdict"] == "survives"
    table = {r.key: r.verdict for r in crunch.table}
    assert table[NOTHING] == "fails" and table["line"] == "survives"
