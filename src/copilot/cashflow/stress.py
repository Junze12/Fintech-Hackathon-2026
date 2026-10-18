"""Cash-shock stress test (chunk 16a, Jun Ze's simulator idea): how likely is cash to stay above
zero over the 13-week forecast, and how big a surprise payment could the business absorb?

Starts from the 13-week forecast's items. Bills, scheduled payments, recurring costs and GST stay
fixed. Only the timing of customer receipts is random: each run gives every open and expected
invoice a delay drawn from that customer's own past delays (decided 2026-10-12). Runs are seeded,
so the same question always gets the same answer.

Every amount inside a run is whole cents (int), so percentiles are exact and every S$ output is
a Decimal. A shock of S on day D lowers every balance from D on by S, so survival for any shock
size, the survival curve, the largest survivable shock and the extra buffer are all read from
the same runs, without re-simulating.

Read-only: never writes to the store. "Runs" or "simulations", never "scenarios".
"""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import computed_field

from copilot.cashflow.forecast import (
    LATE_RECEIPT_DAYS,
    Forecast,
    ForecastItem,
    active_assumptions,
    balance_path,
    forecast_13_weeks,
    horizon_end,
    measured_delays,
)
from copilot.cashflow.recommend import recommend_actions
from copilot.cashflow.scenarios import CollectOnTime, apply_changes
from copilot.reconcile import match_settlements
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    CopilotModel,
    CounterpartyKind,
    DocumentStatus,
    DomainResult,
    Driver,
    Money,
    UntrustedText,
    sgd,
)
from copilot.store import Store

RUNS = 2000
SEED = 20261020
DEFAULT_TARGET_PCT = 95
CURVE_POINTS = 21
RANDOM_SOURCES = ("open_invoice", "expected_invoice")
NO_SHOCK = -(10**18)  # a run that fails before the shock day survives no shock at all

HeadlineCase = Literal["1", "2", "2b", "3", "4"]
Verdict = Literal["survives", "at_risk", "fails"]
AT_RISK_FROM_PCT = Decimal(50)  # Jun Ze's badge: below target but at least half the runs make it


def verdict(survival_pct: Decimal, meets_target: bool) -> Verdict:
    """Badge for the page: survives (meets the target), at risk (>= 50%), fails (< 50%)."""
    if meets_target:
        return "survives"
    return "at_risk" if survival_pct >= AT_RISK_FROM_PCT else "fails"


class DayBand(CopilotModel):
    """End-of-day cash on one day: the forecast and the 10th / 50th / 90th percentile of runs."""

    date: date
    forecast: Money
    p10: Money
    p50: Money
    p90: Money


class WeekBand(CopilotModel):
    """Each run's lowest balance in the week, at the 10th / 50th / 90th percentile."""

    week: int
    start: date
    end: date
    lowest_p10: Money
    lowest_p50: Money
    lowest_p90: Money


class CurvePoint(CopilotModel):
    shock: Money
    survival_pct: Decimal


class FailureWeek(CopilotModel):
    week: int
    start: date
    end: date
    runs: int  # runs whose first day below the floor falls in this week


class Failures(CopilotModel):
    runs_failing: int
    most_likely_day: date | None
    most_likely_day_share_pct: Decimal  # share of all runs that first fail on that day
    by_week: list[FailureWeek]


BridgeKind = Literal["total", "down", "up", "margin"]


class BridgeStep(CopilotModel):
    """One bar of the gap bridge. `amount` is the signed step (a total's level for "total");
    `start` and `end` are the running level before and after, so a chart needs no maths."""

    key: str
    label: str
    kind: BridgeKind
    amount: Money
    start: Money
    end: Money


class GapBridge(CopilotModel):
    day: date
    steps: list[BridgeStep]
    worst_likely: Money  # end-of-day cash on `day` before the shock, (100 - target)th percentile
    gap: Money  # shock + floor - worst_likely, if positive
    spare: Money  # worst_likely - floor - shock, if positive


class PlanCheck(CopilotModel):
    """recommend_actions' non-borrowing plan, re-run on the same draws (16b ranks options)."""

    actions: list[UntrustedText]  # option titles name customers and documents
    survival_pct: Decimal
    extra_buffer: Money
    gap_on_shock_day: Money
    most_likely_failure_day: date | None


class Headline(CopilotModel):
    case: HeadlineCase
    line1: str
    line2: str


class CustomerTiming(CopilotModel):
    customer_id: str
    name: UntrustedText
    observed_payments: int
    mean_delay_days: Decimal | None
    shortest_delay_days: int | None
    longest_delay_days: int | None
    forecast_delay_days: int  # the delay the 13-week forecast uses
    source: Literal["measured", "saved assumption", "no history (fixed date)"]


class Shock(CopilotModel):
    amount: Money
    date: date | None  # None: no shock given


class StressTest(CopilotModel):
    as_of: date
    horizon_end: date
    runs: int
    seed: int
    target_pct: int
    floor: Money  # a run fails when end-of-day cash goes below this (0 + optional buffer)
    shock: Shock
    shock_day_used: date  # the shock's date, else the most likely failure day / lowest P50 day
    survival_pct: Decimal  # with the shock, no action
    survival_without_shock_pct: Decimal
    meets_target: bool
    failures: Failures
    largest_survivable_shock: Money | None  # on shock_day_used; None: not even S$0 reaches it
    curve: list[CurvePoint]
    extra_buffer: Money  # extra cash today that lifts survival (with the shock) to the target
    bridge: GapBridge
    plan: PlanCheck | None
    headline: Headline
    weekly: list[WeekBand]
    daily: list[DayBand]
    customers: list[CustomerTiming]
    assumptions: list[str]

    @computed_field
    @property
    def verdict(self) -> Verdict:
        return verdict(self.survival_pct, self.meets_target)


def _money(cents: int) -> Decimal:
    return Decimal(cents).scaleb(-2)


def _cents(amount: Decimal) -> int:
    return int(amount * 100)


def _pct(count: int, runs: int) -> Decimal:
    """Exact share in percent; with 2,000 runs every value has at most 2 decimals."""
    return (Decimal(count) * 100 / runs).quantize(Decimal("0.01"))


def _rank(pct: int, n: int) -> int:
    """Index of the nearest-rank pct-th percentile in a sorted list of n values."""
    return max(math.ceil(pct * n / 100), 1) - 1


def _needed(target_pct: int, runs: int) -> int:
    """Runs that must survive to reach the target."""
    return math.ceil(target_pct * runs / 100)


class _Draws:
    """For each random receipt: the day indexes it can land on (None = after the horizon)."""

    def __init__(self, keys: list[tuple], options: list[list[int | None]], amounts: list[int]):
        self.keys = keys
        self.options = options
        self.amounts = amounts


def _item_keys(items: list[ForecastItem]) -> list[tuple]:
    """A stable key per item, so the plan's run can reuse the base draw of the same receipt."""
    seen: Counter = Counter()
    keys = []
    for it in items:
        k = (it.source, it.ref, it.counterparty_id, it.date, it.amount)
        keys.append((*k, seen[k]))
        seen[k] += 1
    return keys


class _Engine:
    """Everything one business needs to simulate: built once per call."""

    def __init__(self, store: Store, business_id: str, fc: Forecast, randomness: bool):
        self.as_of = fc.as_of
        self.days = [d for d, _ in balance_path(fc.as_of, fc.start_balance, [])]
        self.start = _cents(fc.start_balance)
        self.randomness = randomness
        used, _ = measured_delays(store, business_id)
        measured = dict(used)
        self.saved: set[str] = set()
        for a in active_assumptions(store, business_id):
            if a.kind == "payment_delay" and a.counterparty_id and a.days is not None:
                used[a.counterparty_id] = a.days
                self.saved.add(a.counterparty_id)
        self.used = used
        self.measured = measured
        settled = match_settlements(store, business_id, "invoice")
        self.observed: dict[str, list[int]] = defaultdict(list)
        for inv in settled.paid:
            paid_on = settled.paid_on.get(inv.id)
            if paid_on is not None:
                self.observed[inv.counterparty_id].append((paid_on - inv.due_date).days)
        self.due = {
            i.id: i.due_date
            for i in store.list_invoices(business_id)
            if i.status is DocumentStatus.OPEN
        }

    def _index(self, day: date) -> int | None:
        i = (day - self.as_of).days - 1
        return i if 0 <= i < len(self.days) else None

    def _pool(self, it: ForecastItem) -> list[int | None] | None:
        """Possible landing days for a random receipt, or None if its timing stays fixed."""
        cid = it.counterparty_id
        observed = self.observed.get(cid or "")
        if not self.randomness or cid is None or not observed:
            return None
        shift = self.used.get(cid, 0) - self.measured.get(cid, 0)  # a saved delay moves the centre
        delays = sorted(d + shift for d in observed)
        if it.source == "open_invoice":
            due = self.due[it.ref]  # type: ignore[index]
            # Still unpaid today, so only delays longer than it is already late are possible.
            dates = [
                due + timedelta(days=d) for d in delays if due + timedelta(days=d) > self.as_of
            ]
            if not dates:
                dates = [self.as_of + timedelta(days=LATE_RECEIPT_DAYS)]
        else:  # expected_invoice: forecast date = issue + terms + the delay it used
            base = it.date - timedelta(days=self.used.get(cid, 0))
            dates = [max(base + timedelta(days=d), self.as_of + timedelta(days=1)) for d in delays]
        return [self._index(d) for d in dates]

    def split(
        self,
        items: list[ForecastItem],
        fixed_refs: set[str] = frozenset(),  # type: ignore[assignment]
    ) -> tuple[list[int], _Draws]:
        """Fixed daily flows (cents) and the random receipts."""
        flows = [0] * len(self.days)
        keys, options, amounts = [], [], []
        for key, it in zip(_item_keys(items), items, strict=True):
            pool = (
                self._pool(it)
                if it.source in RANDOM_SOURCES and not (it.ref and it.ref in fixed_refs)
                else None
            )
            if pool is None:
                i = self._index(it.date)
                if i is not None:
                    flows[i] += _cents(it.amount)
                continue
            keys.append(key)
            options.append(pool)
            amounts.append(_cents(it.amount))
        return flows, _Draws(keys, options, amounts)


def _simulate(start: int, flows: list[int], draws: _Draws, uniforms: list[dict]) -> list[list[int]]:
    """One end-of-day path (cents) per run."""
    paths = []
    for u in uniforms:
        day_flows = flows[:]
        for key, options, amount in zip(draws.keys, draws.options, draws.amounts, strict=True):
            i = options[int(u[key] * len(options))]
            if i is not None:
                day_flows[i] += amount
        balance, path = start, []
        for f in day_flows:
            balance += f
            path.append(balance)
        paths.append(path)
    return paths


def _first_failures(paths: list[list[int]], floor: int, shock: int, d: int) -> list[int | None]:
    out: list[int | None] = []
    for path in paths:
        out.append(
            next((i for i, b in enumerate(path) if b - (shock if i >= d else 0) < floor), None)
        )
    return out


def _modal(fails: list[int | None]) -> tuple[int | None, int]:
    counts = Counter(f for f in fails if f is not None)
    if not counts:
        return None, 0
    day = min(counts, key=lambda i: (-counts[i], i))  # ties: the earliest day
    return day, counts[day]


def _max_shocks(paths: list[list[int]], floor: int, d: int) -> list[int]:
    """Per run: the largest shock on day index d it survives (NO_SHOCK if it fails before d)."""
    out = []
    for path in paths:
        if d and min(path[:d]) < floor:
            out.append(NO_SHOCK)
        else:
            out.append(min(path[d:]) - floor)
    return out


def _buffers(paths: list[list[int]], floor: int, shock: int, d: int) -> list[int]:
    """Per run: extra cash today needed to stay at or above the floor with the shock."""
    out = []
    for path in paths:
        low = min(path[:d]) if d else None
        after = min(path[d:]) - shock
        lowest = after if low is None else min(low, after)
        out.append(max(0, floor - lowest))
    return out


def _nice_step(top: int) -> int:
    """A round curve step in cents (S$100, 200, 250, 500, 1,000, ...) covering `top`."""
    raw = max(top // (CURVE_POINTS - 1), 10_000)
    scale = 10 ** (len(str(raw)) - 1)
    for m in (1, 2, 2.5, 5, 10):
        step = int(m * scale)
        if step >= raw:
            return step
    return 10 * scale


class Sim:
    """The forecast, the engine and the base runs: shared by the stress test and 16b's plans."""

    def __init__(self, forecast: DomainResult[Forecast], engine: _Engine, floor: int, shock: int):
        self.forecast = forecast
        self.engine = engine
        self.floor = floor
        self.shock = shock
        self.flows, self.draws = engine.split(forecast.value.items)
        self.seed = SEED
        self.uniforms: list[dict] = []
        self.paths: list[list[int]] = []
        self.fails0: list[int | None] = []
        self.d = 0
        self.shock_date: date | None = None


def prepare(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    shock_amount: Decimal,
    shock_date: date | None,
    buffer: Decimal,
    as_of: date | None,
    randomness: bool,
) -> Sim:
    if shock_amount < 0:
        raise ValueError("the shock is a payment: give a positive amount")
    if shock_amount > 0 and shock_date is None:
        raise ValueError("give the date of the shock (YYYY-MM-DD) within the next 13 weeks")
    forecast = forecast_13_weeks(store, sandbox, business_id, as_of)
    fc = forecast.value
    last = horizon_end(fc.as_of)
    if shock_date is not None and not fc.as_of < shock_date <= last:
        raise ValueError(
            f"the shock date must be between {(fc.as_of + timedelta(days=1)).isoformat()} and "
            f"{last.isoformat()} (the 13-week forecast)"
        )
    engine = _Engine(store, business_id, fc, randomness)
    sim = Sim(forecast, engine, _cents(buffer), _cents(shock_amount))
    sim.shock_date = shock_date
    return sim


def sim_runs(sim: Sim, runs: int = RUNS, seed: int = SEED) -> None:
    """Draw the runs (no shock in the paths) and find the shock day: the shock's date, else the
    most likely failure day, else the lowest P50 day."""
    rng = random.Random(seed)
    sim.seed = seed
    sim.uniforms = [{k: rng.random() for k in sim.draws.keys} for _ in range(runs)]
    sim.paths = _simulate(sim.engine.start, sim.flows, sim.draws, sim.uniforms)
    sim.fails0 = _first_failures(sim.paths, sim.floor, 0, 0)
    n = len(sim.paths)
    if sim.shock_date is not None:
        sim.d = (sim.shock_date - sim.engine.as_of).days - 1
    else:
        modal0, _ = _modal(sim.fails0)
        if modal0 is not None:
            sim.d = modal0
        else:
            p50 = [sorted(col)[_rank(50, n)] for col in zip(*sim.paths, strict=True)]
            sim.d = min(range(len(sim.engine.days)), key=lambda i: (p50[i], i))


def stress_test(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    shock_amount: Decimal = Decimal("0"),
    shock_date: date | None = None,
    target_pct: int = DEFAULT_TARGET_PCT,
    buffer: Decimal = Decimal("0"),
    as_of: date | None = None,
    randomness: bool = True,
    runs: int = RUNS,
    seed: int = SEED,
    best_plan: bool = True,
) -> DomainResult[StressTest]:
    """randomness=False puts every customer on the forecast's delay (tests: every run then
    equals the 13-week forecast). runs and seed are fixed for users; tests may change them.
    best_plan=False skips 16b's plan search (~1 s) for the headline: tests that only read
    survival use it; the tool always searches."""
    if not 50 <= target_pct <= 99:
        raise ValueError("target must be between 50 and 99 percent")

    sim = prepare(store, sandbox, business_id, shock_amount, shock_date, buffer, as_of, randomness)
    sim_runs(sim, runs, seed)
    forecast, fc, engine, flows = sim.forecast, sim.forecast.value, sim.engine, sim.flows
    uniforms, paths, d, fails0 = sim.uniforms, sim.paths, sim.d, sim.fails0
    last = horizon_end(fc.as_of)
    days = engine.days
    n = len(paths)
    floor = _cents(buffer)
    shock = _cents(shock_amount)
    need = _needed(target_pct, n)

    fails = _first_failures(paths, floor, shock, d) if shock else fails0
    survivors = sum(f is None for f in fails)
    survival = _pct(survivors, n)
    survival0 = _pct(sum(f is None for f in fails0), n)

    max_shock = sorted(_max_shocks(paths, floor, d), reverse=True)
    largest = max_shock[need - 1] if max_shock[need - 1] >= 0 else None
    buffers = sorted(_buffers(paths, floor, shock, d))
    extra = buffers[need - 1]

    p90_capacity = max(max_shock[_rank(10, n)], 0)  # 90th percentile of each run's capacity
    top = max(2 * (largest or 0), 2 * shock, p90_capacity, 1_000_000)
    step = _nice_step(top)
    curve = [
        CurvePoint(
            shock=_money(i * step),
            survival_pct=_pct(sum(m >= i * step for m in max_shock), n),
        )
        for i in range(CURVE_POINTS)
    ]

    # Daily and weekly bands, with the shock taken off from day d on.
    columns = [sorted(col) for col in zip(*paths, strict=True)]
    forecast_path = balance_path(fc.as_of, fc.start_balance, fc.items)
    daily = []
    for i, (day, col) in enumerate(zip(days, columns, strict=True)):
        off = shock if i >= d else 0
        daily.append(
            DayBand(
                date=day,
                forecast=forecast_path[i][1] - (_money(off)),
                p10=_money(col[_rank(10, n)] - off),
                p50=_money(col[_rank(50, n)] - off),
                p90=_money(col[_rank(90, n)] - off),
            )
        )
    weekly = []
    for w in fc.weeks:
        idx = [i for i, day in enumerate(days) if w.start <= day <= w.end]
        lows = sorted(min(p[i] - (shock if i >= d else 0) for i in idx) for p in paths)
        weekly.append(
            WeekBand(
                week=w.week,
                start=w.start,
                end=w.end,
                lowest_p10=_money(lows[_rank(10, n)]),
                lowest_p50=_money(lows[_rank(50, n)]),
                lowest_p90=_money(lows[_rank(90, n)]),
            )
        )

    modal, modal_count = _modal(fails)
    failures = Failures(
        runs_failing=n - survivors,
        most_likely_day=days[modal] if modal is not None else None,
        most_likely_day_share_pct=_pct(modal_count, n),
        by_week=[
            FailureWeek(
                week=w.week,
                start=w.start,
                end=w.end,
                runs=sum(1 for f in fails if f is not None and w.start <= days[f] <= w.end),
            )
            for w in fc.weeks
        ],
    )

    bridge = _bridge(fc, flows, paths, d, days[d], target_pct, floor, shock)

    plan = None
    if survivors < need:
        plan = _plan_check(
            store, business_id, forecast, engine, uniforms, shock, d, floor, target_pct
        )

    gap0 = _cents(bridge.gap)
    head = _headline(
        survivors >= need,
        _best_plan(store, sandbox, business_id, sim, target_pct)
        if survivors < need and best_plan
        else None,
        gap0,
        shock_amount,
        days[d],
        last,
        survival,
        extra,
        failures.most_likely_day,
        target_pct,
        buffer,
    )

    counterparties = {c.id: c for c in store.list_counterparties(business_id)}
    customers = []
    for cid in sorted(
        c.id
        for c in counterparties.values()
        if c.kind in (CounterpartyKind.CUSTOMER, CounterpartyKind.BOTH)
    ):
        obs = engine.observed.get(cid, [])
        customers.append(
            CustomerTiming(
                customer_id=cid,
                name=counterparties[cid].name,
                observed_payments=len(obs),
                mean_delay_days=(Decimal(sum(obs)) / len(obs)).quantize(Decimal("0.1"))
                if obs
                else None,
                shortest_delay_days=min(obs) if obs else None,
                longest_delay_days=max(obs) if obs else None,
                forecast_delay_days=engine.used.get(cid, 0),
                source="saved assumption"
                if cid in engine.saved
                else ("measured" if obs else "no history (fixed date)"),
            )
        )

    warnings = list(forecast.warnings)
    if not randomness:
        warnings.append("Randomness switched off: every run equals the 13-week forecast.")
    fixed_customers = [c.name for c in customers if c.observed_payments == 0]
    if fixed_customers and randomness:
        warnings.append(
            f"{len(fixed_customers)} customer(s) have no matched past payments, so their "
            "receipts keep the forecast's date in every run."
        )

    risk_day = failures.most_likely_day or days[d]
    drivers = [
        Driver(label=it.label, amount=it.amount, detail=f"{it.date.isoformat()} ({it.source})")
        for it in sorted(
            (it for it in fc.items if it.amount < 0 and it.date <= risk_day),
            key=lambda it: it.amount,
        )[:5]
    ]

    value = StressTest(
        as_of=fc.as_of,
        horizon_end=last,
        runs=n,
        seed=seed,
        target_pct=target_pct,
        floor=buffer,
        shock=Shock(amount=shock_amount, date=shock_date),
        shock_day_used=days[d],
        survival_pct=survival,
        survival_without_shock_pct=survival0,
        meets_target=survivors >= need,
        failures=failures,
        largest_survivable_shock=_money(largest) if largest is not None else None,
        curve=curve,
        extra_buffer=_money(extra),
        bridge=bridge,
        plan=plan,
        headline=head,
        weekly=weekly,
        daily=daily,
        customers=customers,
        assumptions=_assumptions(n, target_pct, buffer, last),
    )
    return DomainResult[StressTest](
        value=value, drivers=drivers, data_coverage=forecast.data_coverage, warnings=warnings
    )


def _bridge(
    fc: Forecast,
    flows: list[int],
    paths: list[list[int]],
    d: int,
    day: date,
    target_pct: int,
    floor: int,
    shock: int,
) -> GapBridge:
    """Cash today -> fixed payments -> fixed receipts -> customers (average run) -> bad-luck
    margin -> worst likely position -> shock -> after the shock. Adds up to the cent."""
    n = len(paths)
    start = _cents(fc.start_balance)
    fixed_out = sum(f for f in flows[: d + 1] if f < 0)
    fixed_in = sum(f for f in flows[: d + 1] if f > 0)
    on_day = sorted(p[d] for p in paths)
    worst = on_day[_rank(100 - target_pct, n)]
    average = _money(sum(on_day)) / n  # exact Decimal mean, rounded to cents below
    average = average.quantize(Decimal("0.01"))
    customers = average - _money(start + fixed_out + fixed_in)
    margin = _money(worst) - average

    steps: list[BridgeStep] = []
    level = Decimal("0")

    def add(key: str, label: str, kind: BridgeKind, amount: Decimal) -> None:
        nonlocal level
        begin = Decimal("0") if kind == "total" else level
        end = amount if kind == "total" else level + amount
        steps.append(
            BridgeStep(key=key, label=label, kind=kind, amount=amount, start=begin, end=end)
        )
        level = end

    when = day.strftime("%d %b").lstrip("0")
    add("cash", "Cash today", "total", fc.start_balance)
    add("bills", f"Bills and fixed payments to {when}", "down", _money(fixed_out))
    if fixed_in:
        add("fixed_in", f"Other fixed money in to {when}", "up", _money(fixed_in))
    add("customers", "Customers paying (average run)", "up", customers)
    add("margin", "Bad-luck margin", "margin", margin)
    if level != _money(worst):
        raise AssertionError("gap bridge does not add up")  # pragma: no cover
    add("worst", f"Worst likely position on {when}", "total", _money(worst))
    if shock:
        add("shock", "The shock", "down", -_money(shock))
        add("after", "After the shock", "total", _money(worst - shock))
    return GapBridge(
        day=day,
        steps=steps,
        worst_likely=_money(worst),
        gap=_money(max(0, shock + floor - worst)),
        spare=_money(max(0, worst - floor - shock)),
    )


def _plan_check(
    store: Store,
    business_id: str,
    forecast: DomainResult[Forecast],
    engine: _Engine,
    uniforms: list[dict],
    shock: int,
    d: int,
    floor: int,
    target_pct: int,
) -> PlanCheck | None:
    """recommend_actions' plan for the forecast with the shock in it, on the same draws."""
    fc = forecast.value
    items = list(fc.items)
    if shock:
        items.append(
            ForecastItem(
                date=engine.days[d], amount=-_money(shock), source="what_if", label="The shock"
            )
        )
    shocked = forecast.model_copy(update={"value": fc.model_copy(update={"items": items})})
    rec = recommend_actions(store, business_id, shocked, _money(floor)).value
    chosen = [o for o in rec.options if o.in_plan]
    if not chosen:
        return None
    changes = [c for o in chosen for c in o.changes]
    plan_items, _, _ = apply_changes(store, business_id, shocked.value, changes)
    collected = {c.invoice_id for c in changes if isinstance(c, CollectOnTime)}
    flows, draws = engine.split(plan_items, collected)
    # Same draw for the same receipt; a receipt only the plan has gets a fresh, seeded one.
    extra_rng = random.Random(SEED + 1)
    runs = [{k: u[k] if k in u else extra_rng.random() for k in draws.keys} for u in uniforms]
    paths = _simulate(engine.start, flows, draws, runs)
    n = len(paths)
    need = _needed(target_pct, n)
    fails = _first_failures(paths, floor, 0, 0)
    modal, _ = _modal(fails)
    on_day = sorted(p[d] for p in paths)
    worst = on_day[_rank(100 - target_pct, n)]
    return PlanCheck(
        actions=[o.title for o in chosen],
        survival_pct=_pct(sum(f is None for f in fails), n),
        extra_buffer=_money(sorted(_buffers(paths, floor, 0, d))[need - 1]),
        gap_on_shock_day=_money(max(0, floor - worst)),
        most_likely_failure_day=engine.days[modal] if modal is not None else None,
    )


def _best_plan(
    store: Store, sandbox: Sandbox, business_id: str, sim: Sim, target_pct: int
) -> PlanCheck | None:
    """16b's best plan (compare_options, default assumptions) for the headline."""
    from copilot.cashflow.options import NOTHING, search  # options.py builds on this module

    _, ranked = search(store, sandbox, business_id, sim, target_pct)
    best = ranked[0][0]
    if best.key == NOTHING:
        return None
    return PlanCheck(
        actions=best.actions,
        survival_pct=best.survival_pct,
        extra_buffer=best.extra_buffer,
        gap_on_shock_day=best.gap_on_risk_day,
        most_likely_failure_day=best.most_likely_failure_day,
    )


def _headline(
    covered: bool,
    plan: PlanCheck | None,
    gap0: int,
    shock: Decimal,
    day: date,
    last: date,
    survival: Decimal,
    extra: int,
    fail_day: date | None,
    target_pct: int,
    buffer: Decimal,
) -> Headline:
    """Jun Ze's four cases, in our words. Built from code only (no imported text)."""
    when = day.strftime("%d %b %Y").lstrip("0")
    line = "zero" if buffer == 0 else sgd(buffer)
    what = f"the {sgd(shock)} payment on {when}" if shock else None
    target = Decimal(target_pct)
    if covered:
        return Headline(
            case="1",
            line1=f"You can cover {what} without doing anything."
            if what
            else f"Cash stays above {line} to {last.strftime('%d %b %Y').lstrip('0')} without "
            "doing anything.",
            line2=f"{survival}% of simulated runs never go below {line}.",
        )
    if plan is not None and plan.survival_pct >= target:
        first = (
            f"Without action you'll be {sgd(_money(gap0))} short on {when} in a bad run."
            if gap0 > 0
            else f"Without action cash runs short after {when}."
        )
        return Headline(
            case="2" if gap0 > 0 else "2b",
            line1=first,
            line2=f"Best move: the best plan in the options comparison ({len(plan.actions)} "
            f"action(s)); with it "
            f"{plan.survival_pct}% of runs stay above {line}.",
        )
    plan_gap = _cents(plan.gap_on_shock_day) if plan is not None else gap0
    if plan_gap > 0:
        more = _money(_cents(plan.extra_buffer)) if plan is not None else _money(extra)
        return Headline(
            case="3",
            line1=(
                f"Even the best plan leaves you {sgd(_money(plan_gap))} short on {when}."
                if plan is not None
                else f"You'll be {sgd(_money(plan_gap))} short on {when} in a bad run, and "
                "no collection, rescheduling or cut closes it."
            ),
            line2=f"You need about {sgd(more)} more cash or credit before {when} to reach "
            f"{target_pct}% survival.",
        )

    # Case 4: the shock day is covered (by the plan, or without action), yet runs fail later.
    def day_text(d: date) -> str:
        return d.strftime("%d %b %Y").lstrip("0")

    if plan is not None and gap0 > 0:
        first = (
            f"Without action you'll be {sgd(_money(gap0))} short on {when} in a bad run. The "
            f"best plan covers {when}, but cash still runs short later."
        )
    else:
        first = f"You can cover {what or when}, but the business still runs short later."
    where = [f"most runs first fail on {day_text(fail_day)}"] if fail_day else []
    if plan is not None and plan.most_likely_failure_day:
        where.append(f"with the best plan, on {day_text(plan.most_likely_failure_day)}")
    more = plan.extra_buffer if plan is not None else _money(extra)
    joined = "; ".join(where)
    second = (f"{joined[:1].upper()}{joined[1:]}. " if where else "") + (
        f"About {sgd(more)} more cash or credit from now on would lift survival to {target_pct}%."
    )
    return Headline(case="4", line1=first, line2=second)


def _assumptions(runs: int, target_pct: int, buffer: Decimal, last: date) -> list[str]:
    line = "zero" if buffer == 0 else sgd(buffer)
    return [
        f"{runs:,} simulated runs of the 13-week forecast to {last.isoformat()}, with a fixed "
        "seed (the same question always gives the same answer).",
        "Only the timing of customer payments is random: each invoice's delay is drawn from "
        "that customer's own past payments (an unpaid invoice only from delays longer than it "
        "is already late). Amounts, bills, payroll, rent, tax and scheduled payments are fixed.",
        "A saved payment-delay assumption moves that customer's delays so they centre on the "
        "saved number of days.",
        f"A run fails if end-of-day cash goes below {line} on any day. Survival = share of "
        f"runs that never do. Target {target_pct}%.",
        f"'Worst likely' and 'a bad run' = the {100 - target_pct}th percentile of runs; "
        "P10 / P50 / P90 = the 10th, 50th and 90th percentile on each day.",
        "Not modelled: customers paying less than invoiced or stopping, more than one shock, "
        "and invoices first issued after the forecast's pattern. Plans with a credit line or "
        "loan are compared by compare_options; the headline uses its best plan.",
    ]
