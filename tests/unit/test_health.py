"""Chunk 8 health measures: ageing, cash trend, debt service cover, break-even, net working
capital and supplier concentration.

Synthetic scenarios are scored against ground_truth.json (computed by the generator from its own
truth, not by this code); edge cases against a tiny hand-checked business.
"""

from datetime import date
from decimal import Decimal

import pytest

from copilot.analysis.health import (
    ageing,
    break_even_sales,
    bucket_for,
    cash_trend,
    complete_months,
    debt_service_cover,
)
from copilot.analysis.metrics import supplier_concentration, working_capital
from copilot.sandbox.bank import Sandbox
from copilot.schemas import (
    Account,
    Bill,
    Business,
    Counterparty,
    CounterpartyKind,
    DocumentStatus,
    Invoice,
    Transaction,
)
from copilot.schemas import TransactionCategory as Cat
from copilot.store import Store

SCENARIOS = ["cash_crunch", "concentrated_b2b"]
TODAY = date(2026, 9, 30)


def by_category(truth: dict, month: str) -> dict[str, Decimal]:
    cats = truth["monthly_totals"][month]["by_category"]
    return {c: Decimal(v) for c, v in cats.items() if c != "transfer"}


# --- Ground truth -----------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("kind", ["receivables", "payables"])
def test_ageing_buckets_match_ground_truth(load_scenario, scenario, kind):
    s = load_scenario(scenario)
    result = ageing(s.store, s.business_id, s.as_of, kind).value
    truth = s.truth[f"{kind}_ageing"]
    assert {b.bucket: b.amount for b in result.buckets} == {k: Decimal(v) for k, v in truth.items()}
    assert result.total == sum(Decimal(v) for v in truth.values())
    assert result.basis == "invoice"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_overdue_invoices_and_payment_habits_match_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = ageing(s.store, s.business_id, s.as_of, "receivables").value
    overdue_ids = sorted(d.id for d in result.oldest_overdue)
    assert overdue_ids == s.truth["overdue_invoices"]
    for habit in result.customers:
        expected = s.truth["customers"][habit.customer_id]["observed_mean_delay_days"]
        assert habit.avg_days_late == Decimal(str(expected))
    delays = [h.avg_days_late for h in result.customers]
    assert delays == sorted(delays, reverse=True)  # slowest payer first


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_cash_trend_months_match_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = cash_trend(s.store, s.business_id, s.as_of)
    trend = result.value
    assert [m.month for m in trend.months] == list(s.truth["monthly_totals"])  # Oct 25 - Sep 26
    for m in trend.months:
        cats = by_category(s.truth, m.month)
        assert m.revenue == cats.get("sales", Decimal("0")), m.month
        assert m.net == sum(cats.values()), m.month
        assert m.gross_burn == -sum(v for v in cats.values() if v < 0), m.month
    recent = [sum(by_category(s.truth, m.month).values()) for m in trend.months[-3:]]
    assert trend.avg_net_recent == (sum(recent) / 3).quantize(Decimal("0.01"))
    assert trend.net_burn_recent == max(-trend.avg_net_recent, Decimal("0"))
    assert trend.basis == "cash"


def test_cash_trend_direction_and_volatility(load_scenario):
    crunch = cash_trend(*_args(load_scenario("cash_crunch"))).value
    b2b = cash_trend(*_args(load_scenario("concentrated_b2b"))).value
    # cash_crunch: lumpy receipts from a few big customers; Clearpath: steady monthly billing.
    assert crunch.revenue_volatility > b2b.revenue_volatility
    assert b2b.direction == "improving"


def _args(s):
    return s.store, s.business_id, s.as_of


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_debt_service_cover_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = debt_service_cover(*_args(s))
    months = s.truth["monthly_totals"]
    available = sum(
        v
        for m in months
        for c, v in by_category(s.truth, m).items()
        if c not in ("loan_repayment", "financing_inflow")
    )
    service = -sum(by_category(s.truth, m).get("loan_repayment", Decimal("0")) for m in months)
    v = result.value
    assert v.cash_available == available and v.debt_service == service
    if service:
        assert v.dscr == (available / service).quantize(Decimal("0.01"))
    else:  # concentrated_b2b has no loan
        assert v.dscr is None
        assert any("No loan repayments" in w for w in result.warnings)
    assert any("uncategorised payments" in w for w in result.warnings)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_break_even_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    v = break_even_sales(*_args(s)).value
    groups = [s.truth["monthly_totals"][m]["by_group"] for m in ("2026-07", "2026-08", "2026-09")]
    revenue = sum(Decimal(g["revenue"]) for g in groups)
    cogs = -sum(Decimal(g["cogs"]) for g in groups)
    fixed = -sum(Decimal(g["opex"]) for g in groups)  # truth opex includes what we left unlabelled
    margin = ((revenue - cogs) / revenue).quantize(Decimal("0.0001"))
    assert v.gross_margin == margin
    assert v.avg_monthly_fixed_costs == (fixed / 3).quantize(Decimal("0.01"))
    assert v.break_even_monthly_sales == (fixed / 3 / margin).quantize(Decimal("0.01"))
    assert v.headroom == v.avg_monthly_revenue - v.break_even_monthly_sales


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_supplier_concentration_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    start = date.fromisoformat(s.truth["history_start"])
    result = supplier_concentration(s.store, s.business_id, start, s.as_of).value
    for x in result.suppliers:
        truth = s.truth["suppliers"][x.supplier_id]
        assert x.billed == Decimal(truth["billed"])
        assert x.share.quantize(Decimal("0.001")) == Decimal(truth["share_of_billed"])
    assert result.largest == result.suppliers[0]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_net_working_capital_at_as_of(load_scenario, scenario):
    s = load_scenario(scenario)
    start = date(2026, 7, 1)
    v = working_capital(s.store, s.business_id, start, s.as_of, sandbox=s.sandbox).value
    cash = sum(Decimal(x) for x in s.truth["closing_balances"].values())
    ar = sum(Decimal(x) for x in s.truth["receivables_ageing"].values())
    ap = sum(Decimal(x) for x in s.truth["payables_ageing"].values())
    assert (v.cash, v.receivables, v.payables) == (cash, ar, ap)
    assert v.net_working_capital == cash + ar - ap
    assert working_capital(s.store, s.business_id, start, s.as_of).value.cash is None


# --- Hand-checked edge cases ------------------------------------------------------------------


def test_buckets_and_complete_months():
    assert [bucket_for(d) for d in (-5, 0, 1, 30, 31, 60, 61, 90, 91)] == [
        "not_due",
        "not_due",
        "1_30",
        "1_30",
        "31_60",
        "31_60",
        "61_90",
        "61_90",
        "over_90",
    ]
    assert complete_months(date(2026, 9, 30), 12) == (date(2025, 10, 1), date(2026, 9, 30))
    assert complete_months(date(2026, 10, 7), 3) == (date(2026, 7, 1), date(2026, 9, 30))


def _doc(cls, id, cp, due, amount, paid="0"):
    status = DocumentStatus.PAID if Decimal(paid) == Decimal(amount) else DocumentStatus.OPEN
    return cls(
        id=id,
        business_id="b1",
        counterparty_id=cp,
        number=id.upper(),
        issue_date=date(2026, 1, 1),
        due_date=due,
        amount=Decimal(amount),
        amount_paid=Decimal(paid),
        status=status,
    )


def _txn(id, day, amount, category):
    return Transaction(
        id=id,
        business_id="b1",
        account_id="a1",
        date=day,
        amount=Decimal(amount),
        description=id,
        category=category,
    )


@pytest.fixture
def shop():
    store = Store(":memory:")
    store.add_business(
        Business(
            id="b1",
            name="Shop",
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
            opening_balance=Decimal("10000"),
            opening_date=date(2026, 1, 1),
        )
    )
    for cid, kind in (("c1", "customer"), ("s1", "supplier")):
        store.add_counterparty(
            Counterparty(id=cid, business_id="b1", name=cid.upper(), kind=CounterpartyKind(kind))
        )
    for kind, doc in [
        ("invoice", _doc(Invoice, "i1", "c1", date(2026, 10, 10), "1000")),  # not due
        ("invoice", _doc(Invoice, "i2", "c1", date(2026, 8, 15), "2000", paid="500")),  # 46 d
        ("invoice", _doc(Invoice, "i3", "c1", date(2026, 5, 1), "3000")),  # 152 days
        ("invoice", _doc(Invoice, "i4", "c1", date(2026, 5, 1), "9000", paid="9000")),  # paid
        ("bill", _doc(Bill, "b1", "s1", date(2026, 7, 20), "400")),  # 72 days
    ]:
        store.add_document(kind, doc)
    # Sep: sales 1,000, stock 1,200 -> negative margin. Aug: one unlabelled payment.
    store.add_transaction(_txn("t1", date(2026, 9, 3), "1000", Cat.SALES))
    store.add_transaction(_txn("t2", date(2026, 9, 4), "-1200", Cat.COGS))
    store.add_transaction(_txn("t3", date(2026, 9, 5), "-300", Cat.RENT))
    store.add_transaction(_txn("t4", date(2026, 8, 6), "-50", Cat.UNCATEGORISED))
    yield store
    store.close()


def test_ageing_by_hand(shop):
    r = ageing(shop, "b1", TODAY, "receivables")
    v = r.value
    amounts = {b.bucket: b.amount for b in v.buckets}
    assert amounts == {
        "not_due": Decimal("1000"),
        "1_30": Decimal("0"),
        "31_60": Decimal("1500"),  # only the unpaid part of i2
        "61_90": Decimal("0"),
        "over_90": Decimal("3000"),
    }
    assert v.total == Decimal("5500") and v.overdue == Decimal("4500")
    assert v.overdue_share == Decimal("0.8182")
    assert [d.id for d in v.oldest_overdue] == ["i3", "i2"]
    assert any("part-paid" in w for w in r.warnings)
    bills = ageing(shop, "b1", TODAY, "payables").value
    assert {b.bucket: b.amount for b in bills.buckets}["61_90"] == Decimal("400")
    assert bills.customers == []


def test_no_unpaid_documents(shop):
    r = ageing(shop, "b1", date(2025, 12, 31), "receivables")  # before anything was issued
    assert r.value.total == 0 and r.value.overdue_share is None
    assert any("No unpaid invoices" in w for w in r.warnings)


def test_negative_margin_has_no_break_even(shop):
    r = break_even_sales(shop, "b1", TODAY)
    assert r.value.gross_margin == Decimal("-0.2000")
    assert r.value.break_even_monthly_sales is None and r.value.headroom is None
    assert any("can't be calculated" in w for w in r.warnings)
    assert r.value.avg_monthly_fixed_costs == Decimal("116.67")  # (300 + 50) / 3
    assert any("1 uncategorised payments" in w for w in r.warnings)


def test_short_history_has_no_trend(shop):
    r = cash_trend(shop, "b1", TODAY)
    assert [m.month for m in r.value.months] == ["2026-08", "2026-09"]
    assert r.value.direction == "not enough history"
    assert r.value.avg_net_before is None
    assert any("needs 6" in w for w in r.warnings)


def test_no_loans_means_no_dscr(shop):
    r = debt_service_cover(shop, "b1", TODAY)
    assert r.value.dscr is None and r.value.debt_service == 0


def test_dscr_below_one_is_flagged(shop):
    shop.add_transaction(_txn("t5", date(2026, 9, 20), "-1000", Cat.LOAN_REPAYMENT))
    r = debt_service_cover(shop, "b1", TODAY)
    assert r.value.cash_available == Decimal("-550")  # 1,000 - 1,200 - 300 - 50
    assert r.value.dscr == Decimal("-0.55")
    assert any("did not cover" in w for w in r.warnings)


def test_nwc_needs_the_sandbox(shop):
    sandbox = Sandbox(shop)
    sandbox.set_today("b1", TODAY)
    v = working_capital(shop, "b1", date(2026, 9, 1), TODAY, sandbox=sandbox).value
    assert v.cash == Decimal("9450")  # 10,000 + 1,000 - 1,200 - 300 - 50
    assert v.net_working_capital == v.cash + v.receivables - v.payables


def test_share_paid_by_the_due_date_by_hand(shop):
    # i4 (due 1 May, S$9,000) paid 3 days early; a second paid invoice paid 10 days late.
    shop.add_document("invoice", _doc(Invoice, "i5", "c1", date(2026, 6, 1), "700", paid="700"))
    for tid, day, amount in (("r1", date(2026, 4, 28), "9000"), ("r2", date(2026, 6, 11), "700")):
        txn = _txn(tid, day, amount, Cat.SALES).model_copy(update={"counterparty_id": "c1"})
        shop.add_transaction(txn)
    habit = ageing(shop, "b1", TODAY, "receivables").value.customers[0]
    assert habit.paid_invoices_matched == 2
    assert habit.avg_days_late == Decimal("3.5")  # (-3 + 10) / 2
    assert habit.paid_by_due_pct == Decimal("50.0")


def test_share_paid_by_the_due_date_is_none_without_matches(shop):
    habit = ageing(shop, "b1", TODAY, "receivables").value.customers[0]
    assert habit.paid_invoices_matched == 0 and habit.paid_by_due_pct is None


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_share_paid_by_the_due_date_is_a_valid_share(load_scenario, scenario):
    s = load_scenario(scenario)
    for habit in ageing(s.store, s.business_id, s.as_of, "receivables").value.customers:
        assert Decimal("0") <= habit.paid_by_due_pct <= Decimal("100")
