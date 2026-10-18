"""Reconciliation exceptions (chunk 15): every planted error found, no false HIGH on the clean
fixtures, each threshold at its boundary, and untrusted text kept out of trusted fields."""

from datetime import date, timedelta
from decimal import Decimal as D

import pytest

from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.cashflow.alerts import evaluate_alerts
from copilot.cashflow.forecast import forecast_13_weeks
from copilot.policy.gateway import Gateway
from copilot.policy.roles import Actor
from copilot.reconcile import find_exceptions
from copilot.schemas import (
    Account,
    Bill,
    Business,
    Counterparty,
    CounterpartyKind,
    DocumentStatus,
    Invoice,
    Role,
    SupplierStatementLine,
    Transaction,
    TransactionSource,
)
from copilot.store import Store
from copilot.tools.render import to_llm

FIXTURES = ["cash_crunch", "concentrated_b2b", "prompt_injection", "messy_books"]
AS_OF = date(2026, 9, 30)
B = "biz-t"


def _exceptions(sc, **kw):
    return find_exceptions(sc.store, sc.business_id, sc.as_of, **kw).value


# --- Fixtures against the answer key ---------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_every_expected_exception_and_nothing_else(load_scenario, name):
    sc = load_scenario(name)
    got = {x.id: (x.kind, x.severity, str(x.amount)) for x in _exceptions(sc).exceptions}
    want = {
        x["id"]: (x["kind"], x["severity"], x["amount"])
        for x in sc.truth["reconciliation"]["expected"]
    }
    assert got == want
    assert _exceptions(sc).counts == sc.truth["reconciliation"]["counts"]


@pytest.mark.parametrize("name", ["cash_crunch", "concentrated_b2b", "prompt_injection"])
def test_clean_fixtures_have_no_high_or_medium(load_scenario, name):
    counts = _exceptions(load_scenario(name)).counts
    assert counts["high"] == 0 and counts["medium"] == 0


def test_every_planted_error_is_found(load_scenario):
    sc = load_scenario("messy_books")
    found = {x.id: x for x in _exceptions(sc).exceptions}
    assert len(sc.truth["planted"]) == 10
    for p in sc.truth["planted"]:
        assert p["id"] in found, p["what"]
        assert found[p["id"]].severity == p["severity"], p["what"]
        assert str(found[p["id"]].amount) == p["amount"], p["what"]


def test_order_counts_and_filter(load_scenario):
    sc = load_scenario("messy_books")
    every = _exceptions(sc)
    ranks = [{"high": 0, "medium": 1, "low": 2}[x.severity] for x in every.exceptions]
    assert ranks == sorted(ranks)
    highs = [x.amount for x in every.exceptions if x.severity == "high"]
    assert highs == sorted(highs, reverse=True)
    only_high = _exceptions(sc, min_severity="high")
    assert {x.severity for x in only_high.exceptions} == {"high"}
    assert only_high.counts == every.counts  # counts always cover everything
    total = sum((x.amount for x in every.exceptions if x.severity == "high"), D("0"))
    assert every.amount_by_severity["high"] == total


def test_untrusted_text_never_enters_trusted_fields(load_scenario):
    sc = load_scenario("prompt_injection")
    result = _exceptions(sc)
    for x in result.exceptions:
        for text in (x.reason, x.next_step):
            assert "p-attacker" not in text and "NOTE TO" not in text and "SYSTEM" not in text
    poisoned = next(x for x in result.exceptions if x.id.endswith("st-b-0046"))
    shown = to_llm(poisoned)
    description = shown["statement_lines"][0]["description"]
    assert description.startswith('<untrusted flagged="instruction-like">')


def test_reading_writes_nothing(load_scenario):
    sc = load_scenario("messy_books")
    before = (sc.store.list_transactions(sc.business_id), sc.store.list_bills(sc.business_id))
    _exceptions(sc)
    assert (sc.store.list_transactions(sc.business_id), sc.store.list_bills(sc.business_id)) == (
        before
    )


# --- Alert --------------------------------------------------------------------------------


@pytest.mark.parametrize("name", FIXTURES)
def test_books_alert_only_when_high(load_scenario, name):
    sc = load_scenario(name)
    forecast = forecast_13_weeks(sc.store, sc.sandbox, sc.business_id)
    alerts = evaluate_alerts(sc.store, sc.business_id, forecast, D("0")).value
    books = [a for a in alerts if a.kind == "books_check"]
    if name == "messy_books":
        assert len(books) == 1 and books[0].severity == "warning"
        assert books[0].impact == _exceptions(sc).amount_by_severity["high"]
    else:
        assert books == []


# --- Tool and scoping --------------------------------------------------------------------


def test_tool_is_viewer_read_and_scoped(load_scenario):
    sc = load_scenario("messy_books")
    gw = Gateway(sc.store, sc.sandbox)
    viewer = Actor(user_id="u-v", role=Role.VIEWER, business_id=sc.business_id, session_id="s")
    r = gw.call(viewer, "get_reconciliation_exceptions", {"min_severity": "high"})
    assert r.ok and r.data.value.counts["high"] == 5
    assert not gw.call(viewer, "get_reconciliation_exceptions", {"business_id": "biz-straits"}).ok
    assert sc.store.list_supplier_statement_lines("biz-straits") == []


def test_customer_statement_line_is_rejected(tmp_path, sample_dir):
    for f in sample_dir.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    counterparties = (tmp_path / "counterparties.csv").read_text(encoding="utf-8").splitlines()
    customer = next(r.split(",")[0] for r in counterparties[1:] if ",customer," in r)
    supplier = next(r.split(",")[0] for r in counterparties[1:] if ",supplier," in r)
    (tmp_path / "supplier_statements.csv").write_text(
        "id,counterparty_id,statement_date,number,issue_date,amount,description\n"
        f"st-1,{supplier},2026-09-30,X-1,2026-09-01,100.00,Invoice\n"
        f"st-2,{customer},2026-09-30,X-2,2026-09-01,100.00,Invoice\n",
        encoding="utf-8",
    )
    result = CsvFolderAdapter().load(tmp_path)
    assert [line.id for line in result.supplier_statements] == ["st-1"]
    bad = next(r for r in result.rejected if r.file == "supplier_statements.csv")
    assert bad.line == 3 and "suppliers" in bad.reason


# --- Thresholds on hand-made books -------------------------------------------------------


@pytest.fixture
def books():
    store = Store(":memory:")
    store.add_business(
        Business(
            id=B,
            name="Test Co",
            uen="202000001A",
            industry="Trade",
            incorporated_on=date(2020, 1, 1),
            employee_count=1,
            local_shareholding_pct=D("100"),
        )
    )
    store.add_account(
        Account(
            id="a1",
            business_id=B,
            name="Ops",
            bank_name="Bank",
            account_number="012-345678-9",
            opening_balance=D("100000"),
            opening_date=date(2026, 1, 1),
        )
    )
    for cid, kind in (("c1", CounterpartyKind.CUSTOMER), ("s1", CounterpartyKind.SUPPLIER)):
        store.add_counterparty(Counterparty(id=cid, business_id=B, name=cid.upper(), kind=kind))
    yield store
    store.close()


def _txn(store, tid, day, amount, cp="s1", **kw):
    store.add_transaction(
        Transaction(
            id=tid,
            business_id=B,
            account_id="a1",
            date=day,
            amount=D(amount),
            description=f"pay {tid}",
            counterparty_id=cp,
            **kw,
        )
    )


def _doc(store, kind, did, amount, paid=False, cp=None, issued=date(2026, 9, 1)):
    model = Invoice if kind == "invoice" else Bill
    store.add_document(
        kind,
        model(
            id=did,
            business_id=B,
            counterparty_id=cp or ("c1" if kind == "invoice" else "s1"),
            number=did.upper(),
            issue_date=issued,
            due_date=issued + timedelta(days=30),
            amount=D(amount),
            amount_paid=D(amount) if paid else D("0"),
            status=DocumentStatus.PAID if paid else DocumentStatus.OPEN,
        ),
    )


def _kinds(store):
    return {x.id: (x.kind, x.severity) for x in find_exceptions(store, B, AS_OF).value.exceptions}


@pytest.mark.parametrize(("gap", "flagged"), [(7, True), (8, False)])
def test_duplicate_window_is_seven_days(books, gap, flagged):
    _doc(books, "bill", "b1", "500.00", paid=True)
    _txn(books, "t1", date(2026, 9, 2), "-500.00")
    _txn(books, "t2", date(2026, 9, 2) + timedelta(days=gap), "-500.00")
    kinds = _kinds(books)
    assert ("duplicate_payment:t2" in kinds) is flagged
    if not flagged:
        assert kinds["unclaimed_payment:t2"] == ("unclaimed_payment", "low")


@pytest.mark.parametrize(("paid", "kind"), [("1050.00", "bill_overpaid"), ("1050.01", None)])
def test_near_is_within_five_percent(books, paid, kind):
    _doc(books, "bill", "b1", "1000.00")
    _txn(books, "t1", date(2026, 9, 5), f"-{paid}")
    kinds = _kinds(books)
    if kind:
        assert kinds["bill_overpaid:t1"] == ("bill_overpaid", "high")
    else:
        assert kinds == {"unclaimed_payment:t1": ("unclaimed_payment", "medium")}


def test_short_and_exact_customer_receipts(books):
    _doc(books, "invoice", "i1", "1000.00")
    _doc(books, "invoice", "i2", "800.00")
    _txn(books, "t1", date(2026, 9, 5), "960.00", cp="c1")
    _txn(books, "t2", date(2026, 9, 6), "800.00", cp="c1")
    kinds = _kinds(books)
    assert kinds["short_payment:t1"] == ("short_payment", "medium")
    assert kinds["unlinked_match:t2"] == ("unlinked_match", "low")


def test_paid_documents_without_bank_money(books):
    _txn(books, "t0", date(2026, 8, 1), "-10.00", cp=None)  # starts the bank history
    _doc(books, "invoice", "i1", "1000.00", paid=True)
    _doc(books, "bill", "b1", "400.00", paid=True)
    _doc(books, "bill", "b0", "400.00", paid=True, issued=date(2026, 7, 1))  # before history
    result = find_exceptions(books, B, AS_OF)
    kinds = {x.id: (x.kind, x.severity) for x in result.value.exceptions}
    assert kinds["invoice_paid_no_receipt:i1"] == ("invoice_paid_no_receipt", "high")
    assert kinds["bill_paid_no_payment:b1"] == ("bill_paid_no_payment", "medium")
    assert "bill_paid_no_payment:b0" not in kinds
    assert any("before the bank history" in w for w in result.warnings)


def test_sandbox_and_categorised_money_is_not_flagged(books):
    _txn(books, "t1", date(2026, 9, 5), "-900.00", source=TransactionSource.SANDBOX)
    _txn(books, "t2", date(2026, 9, 5), "-2500.00", cp=None, category="rent")
    _txn(books, "t3", date(2026, 9, 6), "-80.00", cp=None)
    assert _kinds(books) == {"unexplained_payment:t3": ("unexplained_payment", "low")}


@pytest.mark.parametrize(
    ("statement", "severity"),
    [("20099.99", "low"), ("20100.00", "high"), ("1009.99", "low"), ("1010.00", "high")],
)
def test_statement_difference_thresholds(books, statement, severity):
    # S$100 binds on the S$20,000 bill; 1% (S$10) binds on the S$1,000 bill.
    bill = "20000.00" if D(statement) > 5000 else "1000.00"
    _doc(books, "bill", "b1", bill, paid=True)
    _txn(books, "t1", date(2026, 9, 5), f"-{bill}")
    _line(books, "st1", "B1", D(statement))
    assert _kinds(books) == {"statement_amount_differs:st1": ("statement_amount_differs", severity)}


def test_statement_missing_and_renumbered(books):
    _doc(books, "bill", "b1", "700.00", paid=True)
    _txn(books, "t1", date(2026, 9, 5), "-700.00")
    _line(books, "st1", " b1 ", D("700.00"))  # same bill: numbers compare trimmed, any case
    _line(books, "st2", "ZZ-9", D("300.00"))
    assert _kinds(books) == {"statement_bill_missing:st2": ("statement_bill_missing", "high")}
    _doc(books, "bill", "b2", "450.00", paid=True, issued=date(2026, 9, 10))
    _txn(books, "t2", date(2026, 9, 12), "-450.00")
    _line(books, "st3", "OTHER-REF", D("450.00"), issued=date(2026, 9, 10))
    assert _kinds(books)["statement_number_differs:st3"] == ("statement_number_differs", "low")


def _line(store, lid, number, amount, issued=date(2026, 9, 1)):
    store.add_supplier_statement_line(
        SupplierStatementLine(
            id=lid,
            business_id=B,
            counterparty_id="s1",
            statement_date=AS_OF,
            number=number,
            issue_date=issued,
            amount=amount,
        )
    )
