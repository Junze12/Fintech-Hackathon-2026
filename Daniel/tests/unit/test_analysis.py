"""Chunk 4a analysis: working capital, concentration, period comparison, top movers, expense
breakdown, and categorising sandbox postings.

Synthetic scenarios are scored against ground_truth.json; DSO / DPO against a tiny hand-checked
business.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from copilot.analysis.breakdown import expense_breakdown
from copilot.analysis.compare import compare_periods, pct_change, top_movers
from copilot.analysis.metrics import customer_concentration, working_capital
from copilot.dates import previous_period
from copilot.ingest import ingest_folder
from copilot.reconcile import match_settlements, outstanding_at
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

SYNTHETIC = Path(__file__).resolve().parents[2] / "data" / "synthetic"
SEP = (date(2026, 9, 1), date(2026, 9, 30))
JUL = (date(2026, 7, 1), date(2026, 7, 31))
AUG = (date(2026, 8, 1), date(2026, 8, 31))


# --- A tiny business whose DSO / DPO can be checked by hand --------------------------------


def _doc(cls, id, cp, issued, due, amount, paid=False):
    return cls(
        id=id,
        business_id="b1",
        counterparty_id=cp,
        number=id.upper(),
        issue_date=issued,
        due_date=due,
        amount=Decimal(amount),
        amount_paid=Decimal(amount) if paid else Decimal("0"),
        status=DocumentStatus.PAID if paid else DocumentStatus.OPEN,
    )


def _txn(id, day, amount, cp, category):
    return Transaction(
        id=id,
        business_id="b1",
        account_id="a1",
        date=day,
        amount=Decimal(amount),
        description=id,
        counterparty_id=cp,
        category=category,
    )


@pytest.fixture
def tiny():
    store = Store(":memory:")
    store.add_business(
        Business(
            id="b1",
            name="Tiny Co",
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
            opening_balance=Decimal("50000"),
            opening_date=date(2026, 1, 1),
        )
    )
    for cid, kind in (("c1", "customer"), ("c2", "customer"), ("s1", "supplier")):
        store.add_counterparty(
            Counterparty(id=cid, business_id="b1", name=cid.upper(), kind=CounterpartyKind(kind))
        )
    docs = [
        # issued in August, paid in October -> still owed at the end of September
        ("invoice", _doc(Invoice, "i0", "c1", date(2026, 8, 20), date(2026, 9, 19), "2000", True)),
        # issued and paid in September
        ("invoice", _doc(Invoice, "i1", "c1", date(2026, 9, 5), date(2026, 10, 5), "10000", True)),
        ("invoice", _doc(Invoice, "i2", "c1", date(2026, 9, 15), date(2026, 10, 15), "5000")),
        ("invoice", _doc(Invoice, "i3", "c2", date(2026, 9, 28), date(2026, 10, 28), "5000")),
        ("bill", _doc(Bill, "b1", "s1", date(2026, 9, 1), date(2026, 10, 1), "6000", True)),
        # paid, but no bank transaction matches it -> assumed paid on its due date (Oct 10)
        ("bill", _doc(Bill, "b2", "s1", date(2026, 9, 10), date(2026, 10, 10), "3000", True)),
    ]
    for kind, doc in docs:
        store.add_document(kind, doc)
    store.add_transaction(_txn("t1", date(2026, 9, 20), "10000", "c1", Cat.SALES))
    store.add_transaction(_txn("t2", date(2026, 9, 25), "-6000", "s1", Cat.COGS))
    store.add_transaction(_txn("t3", date(2026, 10, 2), "2000", "c1", Cat.SALES))
    yield store
    store.close()


def test_dso_dpo_ccc_by_hand(tiny):
    result = working_capital(tiny, "b1", *SEP)
    v = result.value
    assert v.basis == "invoice" and v.days == 30
    # AR at Sep 30: i0 2,000 (paid Oct 2) + i2 5,000 + i3 5,000 = 12,000; invoiced in Sep 20,000.
    assert v.receivables == Decimal("12000") and v.invoiced_sales == Decimal("20000")
    assert v.dso == Decimal("18.0")  # 12,000 / 20,000 x 30
    # AP at Sep 30: b2 3,000 (assumed paid Oct 10); bills received in Sep 9,000.
    assert v.payables == Decimal("3000") and v.bills_received == Decimal("9000")
    assert v.dpo == Decimal("10.0")  # 3,000 / 9,000 x 30
    assert v.ccc == Decimal("8.0")
    assert any(w.startswith("DIO omitted") for w in result.warnings)
    assert any("1 documents could not be matched" in w for w in result.warnings)


def test_outstanding_follows_settlement_dates(tiny):
    invoices = match_settlements(tiny, "b1", "invoice")
    assert invoices.paid_on == {"i0": date(2026, 10, 2), "i1": date(2026, 9, 20)}
    open_invoices = tiny.list_invoices("b1", DocumentStatus.OPEN)
    assert outstanding_at(open_invoices, invoices, date(2026, 9, 19)).total == Decimal("17000")
    assert outstanding_at(open_invoices, invoices, date(2026, 9, 20)).total == Decimal("7000")
    assert outstanding_at(open_invoices, invoices, date(2026, 10, 2)).total == Decimal("10000")
    bills = match_settlements(tiny, "b1", "bill")
    assert bills.unmatched == ["b2"]


def test_no_documents_means_no_ratio_and_a_reason(tiny):
    result = working_capital(tiny, "b1", date(2026, 1, 1), date(2026, 1, 31))
    assert result.value.dso is None and result.value.dpo is None and result.value.ccc is None
    assert any("DSO can't be calculated" in w for w in result.warnings)
    assert any("DPO can't be calculated" in w for w in result.warnings)


def test_concentration_by_hand(tiny):
    result = customer_concentration(tiny, "b1", *SEP)
    largest = result.value.largest
    assert largest.customer_id == "c1" and largest.share == Decimal("0.7500")
    assert result.value.basis == "invoice"
    assert any("more than 50%" in w for w in result.warnings)


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_concentration_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    start = date.fromisoformat(s.truth["history_start"])
    result = customer_concentration(s.store, s.business_id, start, s.as_of).value
    truth = s.truth["largest_customer"]
    assert result.largest.customer_id == truth["id"]
    assert result.largest.share.quantize(Decimal("0.001")) == Decimal(truth["share_of_invoiced"])
    for c in result.customers:
        assert c.invoiced == Decimal(s.truth["customers"][c.customer_id]["invoiced"])


# --- Comparison and top movers --------------------------------------------------------------


def test_previous_period_defaults():
    assert previous_period(*SEP) == AUG
    assert previous_period(date(2026, 7, 1), date(2026, 9, 30)) == (
        date(2026, 4, 1),
        date(2026, 6, 30),
    )
    assert previous_period(date(2026, 9, 10), date(2026, 9, 19)) == (
        date(2026, 8, 31),
        date(2026, 9, 9),
    )


def test_pct_change_has_no_base_or_sign_flip():
    assert pct_change(Decimal("100"), Decimal("125")) == Decimal("0.2500")
    assert pct_change(Decimal("-100"), Decimal("-150")) == Decimal("-0.5000")
    assert pct_change(Decimal("0"), Decimal("5")) is None
    assert pct_change(Decimal("3880.43"), Decimal("-74601.05")) is None


def test_compare_matches_ground_truth(load_scenario):
    s = load_scenario("cash_crunch")
    result = compare_periods(s.store, s.business_id, *AUG)
    assert (result.value.previous.start, result.value.previous.end) == JUL
    metrics = {m.name: m for m in result.value.metrics}
    revenue = metrics["revenue"]
    truth = s.truth["monthly_totals"]
    assert revenue.previous == Decimal(truth["2026-07"]["by_group"]["revenue"])
    assert revenue.current == Decimal(truth["2026-08"]["by_group"]["revenue"])
    assert revenue.change == revenue.current - revenue.previous
    assert metrics["DSO"].basis == "invoice" and metrics["revenue"].basis == "cash"
    assert metrics["net cash flow"].pct_change == Decimal("-12.1133")  # -S$5.7k -> -S$74.6k
    # Whole calendar months of 31 vs 30 days are still like-for-like.
    sep = compare_periods(s.store, s.business_id, *SEP)
    assert not any("different lengths" in w for w in sep.warnings)


def test_top_movers_explain_the_august_revenue_drop(load_scenario):
    s = load_scenario("cash_crunch")
    movers = top_movers(s.store, s.business_id, *AUG).value.movers
    sales = movers[0]
    assert sales.category is Cat.SALES and sales.effect == "less money in"
    assert sales.note == "3 receipts vs 5"
    assert sales.causes[0].counterparty_id == "c-bayfront"
    assert sales.causes[0].note == "1 receipt vs 2"
    orchid = next(c for c in sales.causes if c.counterparty_id == "c-orchid")
    assert orchid.note == "only in the previous period"
    tax = next(m for m in movers if m.category is Cat.TAX)  # quarterly GST paid in July only
    assert tax.note == "only in the previous period" and tax.effect == "less spending"
    assert [m.change for m in movers] == sorted((m.change for m in movers), key=abs, reverse=True)


def test_custom_comparison_periods_are_validated(load_scenario):
    s = load_scenario("cash_crunch")
    with pytest.raises(ValueError, match="both"):
        compare_periods(s.store, s.business_id, *AUG, compare_start=JUL[0])
    result = top_movers(s.store, s.business_id, *SEP, *JUL)
    assert result.value.previous.start == JUL[0]


# --- Expense breakdown ------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_expense_breakdown_matches_ground_truth(load_scenario, scenario):
    s = load_scenario(scenario)
    result = expense_breakdown(s.store, s.business_id, *AUG)
    v = result.value
    truth = s.truth["monthly_totals"]

    def spend(month):
        return {
            Cat(c): -Decimal(a)
            for c, a in truth[month]["by_category"].items()
            if Decimal(a) < 0 and c != "transfer"
        }

    aug, jul = spend("2026-08"), spend("2026-07")
    assert v.total == sum(aug.values()) and v.previous_total == sum(jul.values())
    lines = {line.category: line for line in v.lines}
    for category in set(aug) | set(jul):
        if category is Cat.OTHER:  # the answer key files uncategorised bank fees under other
            continue
        line = lines[category]
        assert line.amount == aug.get(category, Decimal("0")), category
        assert line.change == aug.get(category, Decimal("0")) - jul.get(category, Decimal("0"))
    assert all(line.amount >= 0 for line in v.lines)
    assert sum(line.share for line in v.lines if line.share) == pytest.approx(1, abs=0.001)


def test_expense_breakdown_flags_stopped_and_groups(load_scenario):
    s = load_scenario("cash_crunch")
    lines = {x.category: x for x in expense_breakdown(s.store, s.business_id, *AUG).value.lines}
    assert lines[Cat.TAX].status == "stopped" and lines[Cat.TAX].amount == 0
    assert lines[Cat.LOAN_REPAYMENT].group.value == "financing"
    assert lines[Cat.COGS].status is None


# --- Sandbox postings are categorised on the way in -------------------------------------------


def test_sandbox_postings_are_categorised():
    store = Store(":memory:")
    ingest_folder(store, SYNTHETIC / "cash_crunch")
    sandbox = Sandbox(store)
    sandbox.set_today("biz-straits", date(2026, 10, 3))
    paid = sandbox.pay_bill_directly(
        "biz-straits", "b-0048", "a-ops", txn_id="w1", description="IBG DR BL-5048"
    )
    gst = sandbox.post_external(
        "biz-straits",
        txn_id="w2",
        account_id="a-ops",
        amount=Decimal("-100.00"),
        description="IRAS GST payment",
        category=Cat.UNCATEGORISED,
        action="world_debit",
    )
    vague = sandbox.post_external(
        "biz-straits",
        txn_id="w3",
        account_id="a-ops",
        amount=Decimal("-50.00"),
        description="POS 4471 misc",
        category=Cat.UNCATEGORISED,
        action="world_debit",
    )
    posted = {t.id: t.category for t in store.list_transactions("biz-straits")}
    assert posted[paid.transaction_id] is Cat.COGS  # Meridian is a supplier
    assert posted[gst.transaction_id] is Cat.TAX  # keyword rule
    assert posted[vague.transaction_id] is Cat.UNCATEGORISED  # never guessed
