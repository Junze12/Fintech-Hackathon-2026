"""Options under uncertainty (chunk 16b, Jun Ze's plans merged with ours): which combination of
actions and financing keeps cash above zero in enough of 16a's runs, and at what cost?

One options list:
  collect, reschedule, cut   recommend_actions' options (cashflow/recommend.py)
  discount                   offer a discount on every open invoice paid within N days
  credit line                the catalogue's revolving line, drawn when short, repaid when not
  loans                      find_financing's other eligible products, priced by costs.py
A **plan** is a set of non-borrowing options plus at most one financing choice. Every plan is
run on 16a's runs with the same random number for the same receipt, and scored two ways:
  - low point if everything works (chase pays on time, discount accepted, nobody lost),
  - survival % and cost vs doing nothing (discounts given, fees, interest, lost-customer margin).
Ranking: meets the target first, then lowest cost, then fewer actions. If none meets it: most
runs surviving, then most days survived, then cost.

Levers with no data behind them (the chance a chased customer pays on time, discount take-up,
losing a customer) are labelled assumptions with tool arguments; customer loss is off unless
the owner sets it (decided 2026-10-12).

Amounts are whole cents inside runs; every S$ output is a Decimal. Read-only: never writes.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from itertools import accumulate, combinations
from operator import add
from typing import Annotated, Literal

from pydantic import Field, computed_field

from copilot.analysis.statements import monthly_statements
from copilot.cashflow.forecast import (
    LATE_RECEIPT_DAYS,
    Forecast,
    ForecastItem,
    balance_path,
    horizon_end,
)
from copilot.cashflow.recommend import funding_need, recommend_actions
from copilot.cashflow.scenarios import CollectOnTime, apply_changes
from copilot.cashflow.stress import (
    RANDOM_SOURCES,
    BridgeStep,
    DayBand,
    Shock,
    Sim,
    Verdict,
    _cents,
    _item_keys,
    _modal,
    _money,
    _needed,
    _pct,
    _rank,
    prepare,
    sim_runs,
    verdict,
)
from copilot.financing.catalogue import load_catalogue
from copilot.financing.costs import CENT, Quote, quote, upfront_fees
from copilot.financing.eligibility import business_facts, check
from copilot.financing.ranking import DISCLAIMER, loan_items
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    UNTRUSTED,
    CopilotModel,
    DocumentStatus,
    DomainResult,
    Driver,
    FinancingProduct,
    Money,
    RepaymentStructure,
    UntrustedText,
    sgd,
)
from copilot.store import Store

MAX_OPTIONS = 5  # non-borrowing options combined in every way: 2**5 = 32 subsets at most
TOP_PLANS = 10
LOSS_MONTHS = 12  # a lost customer costs 12 months of its gross profit (Daniel, 2026-10-12)
LINE_STEP = 100_000  # credit-line limits are rounded up to S$1,000 (cents)
INTEREST_EVERY = 30  # days between interest charges on the credit line
NOTHING = "nothing"

Message = Annotated[str, UNTRUSTED]  # quotes option titles (customer and supplier names)
LeverKind = Literal["collect", "reschedule", "cut", "discount"]
CostKey = Literal["discounts", "fees", "interest", "lost_customers"]


class Levers(CopilotModel):
    """The owner's assumptions for levers we have no data on. Defaults are ours, not data."""

    chase_on_time_pct: int = Field(50, ge=0, le=100)
    customer_loss_pct: int = Field(0, ge=0, le=100)
    discount_pct: Decimal = Field(Decimal("2"), gt=0, le=10)
    discount_days: int = Field(10, ge=1, le=30)
    discount_accept_pct: int = Field(50, ge=0, le=100)


class OptionInfo(CopilotModel):
    key: str
    kind: LeverKind
    title: UntrustedText
    assumption: str
    follow_up_tool: str | None


class FinancingInfo(CopilotModel):
    key: str
    kind: Literal["credit_line", "loan"]
    product_id: str
    name: str
    lender: str
    offered: bool
    reason: str | None  # why it is not in any plan


class CostPart(CopilotModel):
    key: CostKey
    label: str
    amount: Money  # average over runs, rounded to cents


class LossRisk(CopilotModel):
    customer_id: str
    name: UntrustedText
    runs_pct: Decimal  # share of runs in which this plan loses the customer
    cost_if_lost: Money


class LoanTerms(CopilotModel):
    product_id: str
    amount: Money
    draw_date: date
    term_months: int
    total_cost: Money
    eir_pct: Decimal


class CreditLine(CopilotModel):
    product_id: str
    limit: Money
    needed_for_target: Money  # the exact peak draw at the target, before rounding
    capped: bool  # the eligible maximum is below what the target needs
    runs_drawing_pct: Decimal  # share of runs that draw at all
    drawn_at_end_p50: Money
    drawn_at_end_p90: Money


class PlanScore(CopilotModel):
    key: str
    rank: int
    actions: list[UntrustedText]
    option_keys: list[str]
    financing_key: str | None
    survival_pct: Decimal
    meets_target: bool
    mean_days_survived: Decimal
    cost_vs_nothing: Money
    cost_parts: list[CostPart]
    low_point: Money  # if everything works
    low_point_date: date
    gap_on_risk_day: Money  # shortfall on the risk day in a bad run ((100 - target)th pct)
    most_likely_failure_day: date | None
    extra_buffer: Money  # extra cash from today that would bring this plan to the target
    credit_line: CreditLine | None
    loan: LoanTerms | None
    customer_loss: list[LossRisk]
    follow_up_tools: list[str]

    @computed_field
    @property
    def verdict(self) -> Verdict:
        return verdict(self.survival_pct, self.meets_target)


class TableRow(CopilotModel):
    """One row of the options table (Jun Ze's layout): option, chance of surviving, cost vs
    doing nothing, still short on the risk day, risk, recommended."""

    key: str
    name: UntrustedText
    survival_pct: Decimal
    meets_target: bool
    cost_vs_nothing: Money
    gap_on_risk_day: Money
    customer_loss: list[LossRisk]
    recommended: bool

    @computed_field
    @property
    def verdict(self) -> Verdict:
        return verdict(self.survival_pct, self.meets_target)


class FrontierPoint(CopilotModel):
    key: str
    cost: Money
    survival_pct: Decimal


class LineDay(CopilotModel):
    date: date
    drawn_p10: Money
    drawn_p50: Money
    drawn_p90: Money


class OptionsComparison(CopilotModel):
    as_of: date
    horizon_end: date
    runs: int
    seed: int
    target_pct: int
    floor: Money
    shock: Shock
    risk_day: date  # the shock's day, else where cash is most at risk with no action
    levers: Levers
    options: list[OptionInfo]
    financing: list[FinancingInfo]
    plans_compared: int
    best: PlanScore
    table: list[TableRow]
    ranked: list[PlanScore]  # the best TOP_PLANS
    frontier: list[FrontierPoint]  # cheapest first; no plan is both cheaper and safer
    cost_bridge: list[BridgeStep]  # the best plan's cost, part by part
    line_plan: str | None  # the plan whose credit-line use line_daily shows
    line_daily: list[LineDay]
    best_daily: list[DayBand]  # cash with the best plan, P10/P50/P90 per day
    message: Message
    disclaimer: str
    assumptions: list[str]


# --------------------------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------------------------


class _Lever:
    def __init__(self, info: OptionInfo, changes: list, invoice_id: str | None = None):
        self.info = info
        self.key = info.key
        self.changes = changes  # what-if changes (reschedule, cut); chasing is handled per run
        self.invoice_id = invoice_id  # for collect


class _Finance:
    def __init__(self, key: str, product: FinancingProduct, max_amount: Decimal):
        self.key = key
        self.product = product
        self.max_amount = max_amount
        self.line = product.repayment is RepaymentStructure.REVOLVING


class _Coins:
    """Seeded random numbers per receipt or customer, one per run, the same in every plan and
    independent of 16a's draws."""

    def __init__(self, seed: int, runs: int):
        self.seed, self.runs = seed, runs
        self._cache: dict[tuple, list[float]] = {}

    def get(self, kind: str, key: object) -> list[float]:
        k = (kind, str(key))
        if k not in self._cache:
            rng = random.Random(f"{self.seed}:{kind}:{key}")
            self._cache[k] = [rng.random() for _ in range(self.runs)]
        return self._cache[k]


class _Outcome:
    """Per-run results of one plan."""

    def __init__(self, n: int):
        self.fails: list[int | None] = [None] * n
        self.lowest: list[int] = [0] * n
        self.on_day: list[int] = [0] * n
        self.costs: dict[str, list[int]] = {}
        self.lost: Counter = Counter()


def _first_fail(path: list[int], floor: int) -> int | None:
    if min(path) >= floor:
        return None
    return next(i for i, b in enumerate(path) if b < floor)


def _interest(cent_days: int, rate: Decimal) -> int:
    """Interest in cents on a sum of daily drawn balances: drawn x rate x days / 365, rounded
    as costs.py rounds (a constant draw for N days gives the same cents as costs.quote)."""
    if not cent_days:
        return 0
    return _cents((_money(cent_days) * rate / 365).quantize(CENT))


def _line(
    path: list[int],
    start: int,
    floor: int,
    limit: int | None,
    rate: Decimal,
    fee: int,
    d: int,
    keep: bool = False,
) -> tuple[list[int], int | None, int, int, int, list[int], int, int]:
    """A credit line over one run: (cash path if keep, first fail, peak draw, interest cents,
    drawn at the end, drawn per day if keep, lowest cash, cash on day index d). End of each
    day: below the floor -> draw up to the limit (None = unlimited); above it -> repay.
    Interest accrues daily, charged every 30 days; the part not yet charged at the end is a
    cost but not cash. The fee is paid on day 1."""
    if min(path) - fee >= floor:  # never drawn: only the fee
        cash_path = [b - fee for b in path]
        drawn0 = [0] * len(path) if keep else []
        return cash_path, None, 0, 0, 0, drawn0, min(path) - fee, path[d] - fee
    room = math.inf if limit is None else limit
    cash, prev, drawn, cent_days, peak, interest = start - fee, start, 0, 0, 0, 0
    fail: int | None = None
    out: list[int] = []
    drawn_days: list[int] = []
    lowest = at_d = cash
    for i, b in enumerate(path, 1):
        cash += b - prev
        prev = b
        for _ in (0, 1):  # settle; again after an interest charge
            if cash < floor:
                take = min(room - drawn, floor - cash)
                if take > 0:
                    drawn += take
                    cash += take
                    if drawn > peak:
                        peak = drawn
            elif drawn and cash > floor:
                back = min(drawn, cash - floor)
                drawn -= back
                cash -= back
            if _ or i % INTEREST_EVERY:
                break
            charge = _interest(cent_days + drawn, rate)  # today's balance included
            cash -= charge
            interest += charge
            cent_days = 0  # a re-draw to pay the interest accrues from tomorrow
        if i % INTEREST_EVERY:
            cent_days += drawn
        if cash < lowest or i == 1:
            lowest = cash
            if fail is None and cash < floor:
                fail = i - 1
        if i == d + 1:
            at_d = cash
        if keep:
            out.append(cash)
            drawn_days.append(drawn)
    interest += _interest(cent_days, rate)
    return out, fail, peak, int(interest), drawn, drawn_days, lowest, at_d


def _customer_margins(store: Store, business_id: str, today: date) -> tuple[dict[str, int], str]:
    """12 months of each customer's gross profit (cents): its share of the last 12 complete
    months' accrual sales x the accrual gross margin, scaled to 12 months."""
    months, _, reason = monthly_statements(store, business_id, today)
    if reason is not None or not months:
        return {}, reason or "no accrual books"
    last = months[-12:]
    keys = {m.month for m in last}
    revenue = sum((m.pnl.revenue for m in last), Decimal("0"))
    gross = sum((m.pnl.gross_profit for m in last), Decimal("0"))
    if revenue <= 0:
        return {}, "no sales in the last 12 months"
    sales: dict[str, Decimal] = {}
    for inv in store.list_invoices(business_id):
        if f"{inv.issue_date.year}-{inv.issue_date.month:02d}" in keys:
            sales[inv.counterparty_id] = sales.get(inv.counterparty_id, Decimal("0")) + (
                inv.amount - (inv.gst or 0)
            )
    scale = Decimal(LOSS_MONTHS) / len(last)
    margins = {
        cid: _cents((s * gross / revenue * scale).quantize(CENT)) for cid, s in sales.items()
    }
    source = (
        f"gross margin {(gross / revenue * 100).quantize(Decimal('0.1'))}% on each customer's "
        f"sales, {last[0].month} to {last[-1].month}, scaled to {LOSS_MONTHS} months"
    )
    return margins, source


# --------------------------------------------------------------------------------------------
# The search
# --------------------------------------------------------------------------------------------


class _Search:
    def __init__(
        self,
        store: Store,
        sandbox: Sandbox,
        business_id: str,
        sim: Sim,
        target_pct: int,
        levers: Levers,
    ):
        self.store, self.business_id, self.sim = store, business_id, sim
        self.levers = levers
        self.target_pct = target_pct
        fc = sim.forecast.value
        self.as_of = fc.as_of
        self.days = sim.engine.days
        self.n = len(sim.uniforms)
        self.need = _needed(target_pct, self.n)
        self.floor = sim.floor
        self.start = sim.engine.start
        self.coins = _Coins(sim.seed, self.n)
        self.warnings: list[str] = []
        self.names = {c.id: c.name for c in store.list_counterparties(business_id)}

        # The forecast as this search sees it: with the shock as a fixed payment on its day.
        items = list(fc.items)
        if sim.shock:
            items.append(
                ForecastItem(
                    date=self.days[sim.d],
                    amount=-_money(sim.shock),
                    source="what_if",
                    label="The shock",
                )
            )
        self.fc: Forecast = fc.model_copy(update={"items": items})
        shocked = sim.forecast.model_copy(update={"value": self.fc})
        self.rec = recommend_actions(store, business_id, shocked, _money(self.floor)).value
        self.open = {i.id: i for i in store.list_invoices(business_id, DocumentStatus.OPEN)}

        self.levers_list = self._levers()
        self.finance = self._financing(store, sandbox, business_id)
        self.margins: dict[str, int] = {}
        if levers.customer_loss_pct and any(lv.invoice_id for lv in self.levers_list):
            self.margins, self.margin_source = _customer_margins(store, business_id, fc.as_of)
            if not self.margins:
                self.warnings.append(
                    f"Can't price a lost customer ({self.margin_source}): its cost is left out."
                )
        self._subset_cache: dict[tuple[str, ...], tuple] = {}
        self._quotes: dict[tuple[str, str], Quote] = {}

    # ---- options ----------------------------------------------------------------------------

    def _levers(self) -> list[_Lever]:
        out: list[_Lever] = []
        lv = self.levers
        for o in self.rec.options:
            inv_id = next((c.invoice_id for c in o.changes if isinstance(c, CollectOnTime)), None)
            change = o.changes[0]
            target = getattr(change, "invoice_id", None) or getattr(change, "bill_id", None)
            key = f"{o.kind}:{target or change.category.value}"  # type: ignore[union-attr]
            assumption = o.assumption
            if o.kind == "collect":
                assumption = (
                    f"Assumes a {lv.chase_on_time_pct}% chance the customer pays by the due "
                    "date once chased (our assumption, not data); otherwise it pays as it "
                    "usually does."
                    + (
                        f" {lv.customer_loss_pct}% chance chasing loses the customer (your "
                        "setting)."
                        if lv.customer_loss_pct
                        else ""
                    )
                )
            out.append(
                _Lever(
                    OptionInfo(
                        key=key,
                        kind=o.kind,
                        title=o.title,
                        assumption=assumption,
                        follow_up_tool=o.follow_up_tool,
                    ),
                    [] if inv_id else list(o.changes),
                    inv_id,
                )
            )
        has_discount = bool(self.open)
        room = MAX_OPTIONS - has_discount
        if len(out) > room:
            self.warnings.append(
                f"{len(out)} options without borrowing: only the first {room} (in order of "
                "preference) are combined into plans."
            )
            out = out[:room]
        if has_discount:
            out.append(
                _Lever(
                    OptionInfo(
                        key="discount",
                        kind="discount",
                        title=f"Offer {lv.discount_pct.normalize():f}% off every open invoice "
                        f"paid within {lv.discount_days} days",
                        assumption=f"Assumes each customer takes it with a "
                        f"{lv.discount_accept_pct}% chance (our assumption, not data). Invoices "
                        "the same plan chases are left out.",
                        follow_up_tool=None,
                    ),
                    [],
                )
            )
        return out

    def _financing(self, store: Store, sandbox: Sandbox, business_id: str) -> list[_Finance]:
        facts = business_facts(store, sandbox, business_id, self.as_of).value
        self.financing_info: list[FinancingInfo] = []
        out: list[_Finance] = []
        for p in load_catalogue().products:
            e = check(p, facts)
            line = p.repayment is RepaymentStructure.REVOLVING
            key = "line" if line else f"loan:{p.id}"
            reason = None if e.eligible else "; ".join(e.reasons) or "not eligible"
            self.financing_info.append(
                FinancingInfo(
                    key=key,
                    kind="credit_line" if line else "loan",
                    product_id=p.id,
                    name=p.name,
                    lender=p.lender,
                    offered=e.eligible,
                    reason=reason,
                )
            )
            if e.eligible:
                out.append(_Finance(key, p, e.max_amount))
        return out

    # ---- one subset of non-borrowing options -------------------------------------------------

    def _subset(self, subset: tuple[_Lever, ...]) -> tuple:
        """(paths, outcome costs, deterministic path) for a subset; cached."""
        key = tuple(lv.key for lv in subset)
        if key in self._subset_cache:
            return self._subset_cache[key]
        lv = self.levers
        engine = self.sim.engine
        changes = [c for x in subset for c in x.changes]
        items, _, _ = apply_changes(self.store, self.business_id, self.fc, changes)
        chased = {x.invoice_id for x in subset if x.invoice_id}
        discount = any(x.info.kind == "discount" for x in subset)
        lossable = (
            {self.open[i].counterparty_id for i in chased if i in self.open}
            if lv.customer_loss_pct
            else set()
        )
        offer = self._index(self.as_of + timedelta(days=lv.discount_days))

        flows = [0] * len(self.days)
        entries = []  # (key, pool, amount, mode, arg, forecast index)
        for k, it in zip(_item_keys(items), items, strict=True):
            pool = engine._pool(it) if it.source in RANDOM_SOURCES else None
            mode, arg = "plain", None
            if it.source == "open_invoice" and it.ref in chased:
                inv = self.open[it.ref]
                on_time = max(inv.due_date, self.as_of + timedelta(days=LATE_RECEIPT_DAYS))
                mode, arg = "chase", self._index(on_time)
            elif it.source == "open_invoice" and discount:
                cut = _cents((it.amount * lv.discount_pct / 100).quantize(CENT))
                mode, arg = "discount", cut
            elif it.source == "expected_invoice" and it.counterparty_id in lossable:
                mode, arg = "loss", it.counterparty_id
            if pool is None and mode == "plain":
                i = self._index(it.date)
                if i is not None:
                    flows[i] += _cents(it.amount)
                continue
            if pool is None:
                pool = [self._index(it.date)]
            entries.append((k, pool, _cents(it.amount), mode, arg, self._index(it.date)))

        n = self.n
        uniforms = self.sim.uniforms
        chase_p = lv.chase_on_time_pct / 100
        accept_p = lv.discount_accept_pct / 100
        loss_p = lv.customer_loss_pct / 100
        coins = {
            e[0]: self.coins.get("chase" if e[3] == "chase" else "accept", e[0])
            for e in entries
            if e[3] in ("chase", "discount")
        }
        loss_coins = {cid: self.coins.get("loss", cid) for cid in lossable}

        paths: list[list[int]] = []
        discounts = [0] * n
        lost_runs: list[tuple[str, ...]] = []
        for r in range(n):
            u = uniforms[r]
            f = flows[:]
            gone = tuple(sorted(c for c in lossable if loss_coins[c][r] < loss_p))
            for k, pool, amount, mode, arg, _ in entries:
                i = pool[int(u.get(k, 0.0) * len(pool))]
                if mode == "chase" and coins[k][r] < chase_p:
                    i = arg if i is None else min(i, arg)
                elif mode == "discount" and coins[k][r] < accept_p:
                    i = offer if i is None else min(i, offer)
                    amount -= arg
                    discounts[r] += arg
                elif mode == "loss" and arg in gone:
                    continue
                if i is not None:
                    f[i] += amount
            paths.append(list(accumulate(f, initial=self.start))[1:])
            lost_runs.append(gone)

        # If everything works: forecast dates, chase on time, discount taken, nobody lost.
        f = flows[:]
        for _, _, amount, mode, arg, i in entries:
            if mode == "chase":
                i = arg if i is None else min(i, arg)
            elif mode == "discount":
                i = offer if i is None else min(i, offer)
                amount -= arg
            if i is not None:
                f[i] += amount
        det = list(accumulate(f, initial=self.start))[1:]
        result = (paths, discounts, lost_runs, det)
        self._subset_cache[key] = result
        return result

    def _index(self, day: date) -> int | None:
        i = (day - self.as_of).days - 1
        return i if 0 <= i < len(self.days) else None

    # ---- scoring ------------------------------------------------------------------------------

    def _score(
        self,
        subset: tuple[_Lever, ...],
        fin: _Finance | None,
        keep: bool = False,
    ) -> tuple[PlanScore, _Outcome, list[list[int]], list[list[int]]] | None:
        paths, discounts, lost_runs, det = self._subset(subset)
        n, floor = self.n, self.floor
        out = _Outcome(n)
        out.costs = {"discounts": discounts}
        loss_cost = [sum(self.margins.get(c, 0) for c in g) for g in lost_runs]
        out.costs["lost_customers"] = loss_cost
        for g in lost_runs:
            out.lost.update(g)
        d = self.sim.d
        line: CreditLine | None = None
        loan: LoanTerms | None = None
        kept_paths: list[list[int]] = []
        drawn_paths: list[list[int]] = []
        low_det = det

        if fin is None:
            for r, p in enumerate(paths):
                out.fails[r] = _first_fail(p, floor)
                out.lowest[r] = min(p)
                out.on_day[r] = p[d]
            kept_paths = paths if keep else []
            out.costs["fees"] = [0] * n
            out.costs["interest"] = [0] * n
        elif fin.line:
            product = fin.product
            rate = product.annual_rate_pct / 100
            cap = _cents(fin.max_amount)
            fee_cap = _cents(upfront_fees(product, fin.max_amount))
            first = [_line(p, self.start, floor, None, rate, fee_cap, d) for p in paths]
            peaks = sorted(x[2] for x in first)
            needed = peaks[self.need - 1]
            limit = max(math.ceil(needed / LINE_STEP) * LINE_STEP, _cents(product.min_amount))
            capped = limit > cap
            limit = min(limit, cap)
            fee = _cents(upfront_fees(product, _money(limit)))
            interest, fees, end_drawn = [0] * n, [fee] * n, [0] * n
            for r, p in enumerate(paths):
                x = first[r]
                if keep or x[2] > limit or fee != fee_cap:
                    x = _line(p, self.start, floor, limit, rate, fee, d, keep)
                cash, fail, _, intr, drawn_end, drawn_days, low, at_d = x
                out.fails[r] = fail
                out.lowest[r] = low
                out.on_day[r] = at_d
                interest[r] = intr
                end_drawn[r] = drawn_end
                if keep:
                    kept_paths.append(cash)
                    drawn_paths.append(drawn_days)
            out.costs["fees"] = fees
            out.costs["interest"] = interest
            ends = sorted(end_drawn)
            line = CreditLine(
                product_id=product.id,
                limit=_money(limit),
                needed_for_target=_money(needed),
                capped=capped,
                runs_drawing_pct=_pct(sum(1 for x in first if x[2] > 0), n),
                drawn_at_end_p50=_money(ends[_rank(50, n)]),
                drawn_at_end_p90=_money(ends[_rank(90, n)]),
            )
            low_det = _line(det, self.start, floor, limit, rate, fee, d, keep=True)[0]
        else:
            path_det = [(day, _money(b)) for day, b in zip(self.days, det, strict=True)]
            need = funding_need(self.as_of, path_det, _money(floor))
            if need is None:
                return None  # nothing to borrow for in this plan
            qkey = (fin.product.id, need.model_dump_json())
            if qkey not in self._quotes:
                self._quotes[qkey] = quote(fin.product, need)
            q = self._quotes[qkey]
            if q.amount > fin.max_amount:
                return None
            offset = [0] * len(self.days)
            for it in loan_items(q):
                i = self._index(it.date)
                if i is not None:
                    offset[i] += _cents(it.amount)
            offset = list(accumulate(offset))
            for r, p in enumerate(paths):
                adj = list(map(add, p, offset))
                out.fails[r] = _first_fail(adj, floor)
                out.lowest[r] = min(adj)
                out.on_day[r] = adj[d]
                if keep:
                    kept_paths.append(adj)
            out.costs["fees"] = [_cents(q.total_fees)] * n
            out.costs["interest"] = [_cents(q.total_interest)] * n
            loan = LoanTerms(
                product_id=q.product_id,
                amount=q.amount,
                draw_date=q.draw_date,
                term_months=q.term_months,
                total_cost=q.total_cost,
                eir_pct=q.eir_pct,
            )
            low_det = list(map(add, det, offset))

        survivors = sum(f is None for f in out.fails)
        modal, _ = _modal(out.fails)
        horizon = len(self.days)
        days_survived = sum(horizon if f is None else f for f in out.fails)
        parts = [
            CostPart(key=k, label=label, amount=(_money(sum(out.costs[k])) / n).quantize(CENT))
            for k, label in (
                ("discounts", "Discounts given"),
                ("fees", "Financing fees"),
                ("interest", "Interest"),
                ("lost_customers", f"Lost customers ({LOSS_MONTHS} months' gross profit)"),
            )
        ]
        on_day = sorted(out.on_day)
        worst = on_day[_rank(100 - self.target_pct, n)]
        buffers = sorted(max(0, floor - low) for low in out.lowest)
        low_i = min(range(horizon), key=lambda i: (low_det[i], i))
        titles = [x.info.title for x in subset]
        tools = [x.info.follow_up_tool for x in subset if x.info.follow_up_tool]
        if fin is not None:
            titles.append(self._finance_title(fin, line, loan))
            tools.append("prefill_application")
        keys = [x.key for x in subset] + ([fin.key] if fin else [])
        score = PlanScore(
            key="+".join(keys) or NOTHING,
            rank=0,
            actions=titles,
            option_keys=[x.key for x in subset],
            financing_key=fin.key if fin else None,
            survival_pct=_pct(survivors, n),
            meets_target=survivors >= self.need,
            mean_days_survived=(Decimal(days_survived) / n).quantize(Decimal("0.1")),
            cost_vs_nothing=sum((p.amount for p in parts), Decimal("0")),
            cost_parts=parts,
            low_point=_money(low_det[low_i]),
            low_point_date=self.days[low_i],
            gap_on_risk_day=_money(max(0, floor - worst)),
            most_likely_failure_day=self.days[modal] if modal is not None else None,
            extra_buffer=_money(buffers[self.need - 1]),
            credit_line=line,
            loan=loan,
            customer_loss=[
                LossRisk(
                    customer_id=cid,
                    name=self.names.get(cid, cid),
                    runs_pct=_pct(count, n),
                    cost_if_lost=_money(self.margins.get(cid, 0)),
                )
                for cid, count in sorted(out.lost.items())
            ],
            follow_up_tools=tools,
        )
        return score, out, kept_paths, drawn_paths

    def _finance_title(self, fin: _Finance, line: CreditLine | None, loan: LoanTerms | None) -> str:
        p = fin.product
        if line is not None:
            return (
                f"Open a {sgd(line.limit)} {p.name} ({p.lender}, "
                f"{p.annual_rate_pct.normalize():f}% a year), drawn only when cash is short"
            )
        assert loan is not None
        return (
            f"Borrow {sgd(loan.amount)} with {p.name} ({p.lender}) from "
            f"{loan.draw_date.isoformat()} for {loan.term_months} month"
            + ("s" if loan.term_months != 1 else "")
        )

    def run(self) -> list[tuple[PlanScore, tuple[_Lever, ...], _Finance | None]]:
        plans = []
        for size in range(len(self.levers_list) + 1):
            for subset in combinations(self.levers_list, size):
                for fin in [None, *self.finance]:
                    scored = self._score(subset, fin)
                    if scored is not None:
                        plans.append((scored[0], subset, fin))
        return _rank_plans(plans)


def _rank_plans(plans: list) -> list:
    """Meets the target -> lowest cost -> fewer actions -> key. If none meets it: most runs
    surviving -> most days survived -> lowest cost -> key (Jun Ze's pickBest, our cost)."""

    def order(p):
        s: PlanScore = p[0]
        size = len(s.option_keys) + (s.financing_key is not None)
        if s.meets_target:
            return (0, s.cost_vs_nothing, size, s.key)
        return (1, -s.survival_pct, -s.mean_days_survived, s.cost_vs_nothing, size, s.key)

    ranked = sorted(plans, key=order)
    return [(p[0].model_copy(update={"rank": i}), *p[1:]) for i, p in enumerate(ranked, 1)]


def _frontier(scores: list[PlanScore]) -> list[FrontierPoint]:
    """Plans no other plan beats on both survival (higher) and cost (lower); cheapest first.
    Equal (cost, survival) points keep the better-ranked plan."""
    points: list[FrontierPoint] = []
    for s in scores:  # ranked order, so the first of equal points is the better-ranked
        if any(
            o.survival_pct >= s.survival_pct
            and o.cost_vs_nothing <= s.cost_vs_nothing
            and (o.survival_pct > s.survival_pct or o.cost_vs_nothing < s.cost_vs_nothing)
            for o in scores
        ):
            continue
        if any(p.cost == s.cost_vs_nothing and p.survival_pct == s.survival_pct for p in points):
            continue
        points.append(FrontierPoint(key=s.key, cost=s.cost_vs_nothing, survival_pct=s.survival_pct))
    return sorted(points, key=lambda p: (p.cost, p.survival_pct))


def _cost_bridge(best: PlanScore) -> list[BridgeStep]:
    steps, level = [], Decimal("0")
    for part in best.cost_parts:
        if part.amount == 0:
            continue
        steps.append(
            BridgeStep(
                key=part.key,
                label=part.label,
                kind="up",
                amount=part.amount,
                start=level,
                end=level + part.amount,
            )
        )
        level += part.amount
    if level != best.cost_vs_nothing:
        raise AssertionError("cost bridge does not add up")  # pragma: no cover
    steps.append(
        BridgeStep(
            key="total",
            label="Cost vs doing nothing",
            kind="total",
            amount=level,
            start=Decimal("0"),
            end=level,
        )
    )
    return steps


def _bands(days: list[date], forecast: list[Decimal], paths: list[list[int]]) -> list[DayBand]:
    n = len(paths)
    return [
        DayBand(
            date=day,
            forecast=fc,
            p10=_money(col[_rank(10, n)]),
            p50=_money(col[_rank(50, n)]),
            p90=_money(col[_rank(90, n)]),
        )
        for day, fc, col in zip(
            days, forecast, (sorted(c) for c in zip(*paths, strict=True)), strict=True
        )
    ]


def _message(best: PlanScore, nothing: PlanScore, target_pct: int, floor: Decimal) -> str:
    line = "zero" if floor == 0 else sgd(floor)
    if best.key == NOTHING:
        return (
            f"Doing nothing already keeps cash above {line} in {nothing.survival_pct}% of runs "
            f"(target {target_pct}%). No action or borrowing is needed."
        )
    cost = (
        f"costing about {sgd(best.cost_vs_nothing)} vs doing nothing"
        if best.cost_vs_nothing
        else "at no cost vs doing nothing"
    )
    head = (
        f"Best plan: {'; '.join(best.actions)}. With it {best.survival_pct}% of runs stay above "
        f"{line} (doing nothing: {nothing.survival_pct}%), {cost}."
    )
    if not best.meets_target:
        head += (
            f" No plan reaches {target_pct}%: this one gets closest; about "
            f"{sgd(best.extra_buffer)} more cash from today would."
        )
    return head


def _assumptions(levers: Levers, runs: int, target_pct: int, margin_note: str | None) -> list[str]:
    out = [
        f"Every plan is run on the same {runs:,} simulated runs as the stress test (same draw for "
        f"the same customer payment). Survival = share of runs never below the floor; target "
        f"{target_pct}%.",
        f"Chasing an invoice: {levers.chase_on_time_pct}% chance it is paid by its due date "
        "(overdue: within 7 days), otherwise as the customer usually pays. Our assumption, "
        "not data.",
        f"Discount offer: {levers.discount_pct.normalize():f}% off if paid within "
        f"{levers.discount_days} days; each customer takes it with a "
        f"{levers.discount_accept_pct}% chance (our assumption, not data).",
        "Customer loss from chasing: "
        + (
            f"{levers.customer_loss_pct}% chance per chased customer (your setting); a lost "
            f"customer's expected invoices stop and it costs {LOSS_MONTHS} months of its gross "
            f"profit ({margin_note})."
            if levers.customer_loss_pct
            else "off (0%) unless you set a chance."
        ),
        "Credit line: the smallest limit (rounded up to S$1,000) that reaches the target, drawn "
        "at the end of a day when cash is below the floor and repaid when above it; interest "
        "daily on what is drawn, charged every 30 days; a run fails only when the line is used "
        "up. Interest after the forecast is not counted.",
        "Loans: priced like find_financing for the gap left by the plan's other steps; cost is "
        "the loan's whole-life interest and fees. Rescheduling a bill is counted as free, but "
        "the supplier may charge for it.",
        "'Low point' assumes every step works (chase paid on time, discount taken, nobody lost).",
    ]
    return out


# --------------------------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------------------------


def search(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    sim: Sim,
    target_pct: int,
    levers: Levers | None = None,
) -> tuple[_Search, list]:
    s = _Search(store, sandbox, business_id, sim, target_pct, levers or Levers())
    return s, s.run()


def compare_options(
    store: Store,
    sandbox: Sandbox,
    business_id: str,
    target_pct: int = 95,
    buffer: Decimal = Decimal("0"),
    shock_amount: Decimal = Decimal("0"),
    shock_date: date | None = None,
    levers: Levers | None = None,
    as_of: date | None = None,
    runs: int | None = None,
    seed: int | None = None,
) -> DomainResult[OptionsComparison]:
    if not 50 <= target_pct <= 99:
        raise ValueError("target must be between 50 and 99 percent")
    levers = levers or Levers()
    sim = prepare(store, sandbox, business_id, shock_amount, shock_date, buffer, as_of, True)
    kwargs = {k: v for k, v in (("runs", runs), ("seed", seed)) if v is not None}
    sim_runs(sim, **kwargs)
    s, ranked = search(store, sandbox, business_id, sim, target_pct, levers)
    fc = sim.forecast.value
    scores = [p[0] for p in ranked]
    by_key = {p[0].key: p for p in ranked}
    best_score, best_subset, best_fin = ranked[0]
    nothing = by_key[NOTHING][0]

    # Table: doing nothing, each option alone, each financing choice alone, the best plan.
    rows = [nothing]
    rows += [by_key[lv.key][0] for lv in s.levers_list if lv.key in by_key]
    rows += [by_key[f.key][0] for f in s.finance if f.key in by_key]
    if best_score.key not in {r.key for r in rows}:
        rows.append(best_score)
    names = {lv.key: lv.info.title for lv in s.levers_list}
    table = [
        TableRow(
            key=r.key,
            name="Do nothing"
            if r.key == NOTHING
            else (
                "Best combination: " + "; ".join(r.actions)
                if len(r.actions) > 1
                else names.get(r.key, r.actions[0])
            ),
            survival_pct=r.survival_pct,
            meets_target=r.meets_target,
            cost_vs_nothing=r.cost_vs_nothing,
            gap_on_risk_day=r.gap_on_risk_day,
            customer_loss=r.customer_loss,
            recommended=r.key == best_score.key,
        )
        for r in rows
    ]

    # Daily bands for the best plan, and credit-line use for the best plan with a line.
    _, _, best_paths, _ = s._score(best_subset, best_fin, keep=True)  # type: ignore[misc]
    forecast_path = [b for _, b in balance_path(fc.as_of, fc.start_balance, s.fc.items)]
    best_daily = _bands(s.days, forecast_path, best_paths)
    line_entry = next((p for p in ranked if p[2] is not None and p[2].line), None)
    line_daily: list[LineDay] = []
    if line_entry is not None:
        _, _, _, drawn = s._score(line_entry[1], line_entry[2], keep=True)  # type: ignore[misc]
        n = len(drawn)
        line_daily = [
            LineDay(
                date=day,
                drawn_p10=_money(col[_rank(10, n)]),
                drawn_p50=_money(col[_rank(50, n)]),
                drawn_p90=_money(col[_rank(90, n)]),
            )
            for day, col in zip(s.days, (sorted(c) for c in zip(*drawn, strict=True)), strict=True)
        ]

    margin_note = getattr(s, "margin_source", None)
    warnings = list(sim.forecast.warnings) + s.warnings
    if best_score.credit_line is not None and best_score.credit_line.drawn_at_end_p90 > 0:
        warnings.append(
            "In 1 run in 10 the credit line still has "
            f"{sgd(best_score.credit_line.drawn_at_end_p90)} or more drawn at the end of the "
            "forecast; interest after that isn't counted."
        )
    value = OptionsComparison(
        as_of=fc.as_of,
        horizon_end=horizon_end(fc.as_of),
        runs=s.n,
        seed=sim.seed,
        target_pct=target_pct,
        floor=buffer,
        shock=Shock(amount=shock_amount, date=shock_date),
        risk_day=s.days[sim.d],
        levers=levers,
        options=[lv.info for lv in s.levers_list],
        financing=s.financing_info,
        plans_compared=len(ranked),
        best=best_score,
        table=table,
        ranked=scores[:TOP_PLANS],
        frontier=_frontier(scores),
        cost_bridge=_cost_bridge(best_score),
        line_plan=line_entry[0].key if line_entry else None,
        line_daily=line_daily,
        best_daily=best_daily,
        message=_message(best_score, nothing, target_pct, buffer),
        disclaimer=DISCLAIMER,
        assumptions=_assumptions(levers, s.n, target_pct, margin_note),
    )
    return DomainResult[OptionsComparison](
        value=value,
        drivers=[
            Driver(label=p.label, amount=p.amount, detail="best plan's cost")
            for p in best_score.cost_parts
            if p.amount
        ],
        data_coverage=sim.forecast.data_coverage,
        warnings=warnings,
    )
