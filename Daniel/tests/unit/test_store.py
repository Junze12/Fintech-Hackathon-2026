import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from copilot.schemas import (
    Account,
    Business,
    DocumentStatus,
    Transaction,
    TransactionSource,
)
from copilot.store import NotFoundError, Store, from_cents, to_cents

BIZ = "biz-kopi"


def other_business(store: Store) -> None:
    store.add_business(
        Business(
            id="biz-other",
            name="Other Pte Ltd",
            uen="201999999A",
            industry="Retail",
            incorporated_on=date(2019, 1, 1),
            employee_count=3,
            local_shareholding_pct=Decimal("50"),
        )
    )
    store.add_account(
        Account(
            id="b-acc",
            business_id="biz-other",
            name="Main",
            bank_name="Bank",
            account_number="999-000",
            opening_balance=Decimal("100"),
            opening_date=date(2026, 7, 1),
        )
    )


def test_cents_conversion_is_exact():
    assert to_cents(Decimal("12.30")) == 1230
    assert from_cents(1230) == Decimal("12.30")
    assert from_cents(to_cents(Decimal("0.10")) + to_cents(Decimal("0.20"))) == Decimal("0.30")
    with pytest.raises(ValueError):
        to_cents(Decimal("1.234"))


def test_round_trip_preserves_values(store, sample_import):
    assert store.get_business(BIZ) == sample_import.business
    assert store.list_accounts(BIZ) == sorted(sample_import.accounts, key=lambda a: a.id)
    assert store.list_transactions(BIZ) == sorted(
        sample_import.transactions, key=lambda t: (t.date, t.id)
    )
    assert {i.id for i in store.list_invoices(BIZ)} == {i.id for i in sample_import.invoices}
    assert {b.id for b in store.list_bills(BIZ)} == {b.id for b in sample_import.bills}
    assert {p.id for p in store.list_payees(BIZ)} == {"p-beans", "p-landlord"}


def test_account_number_survives_as_secret(store):
    account = store.get_account(BIZ, "a-ops")
    assert account.account_number.get_secret_value() == "012-345678-9"
    assert "345678" not in repr(account)


def test_date_filters(store):
    september = store.list_transactions(BIZ, start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert {t.date.month for t in september} == {9}
    reserve = store.list_transactions(BIZ, account_id="a-res")
    assert [t.id for t in reserve] == ["t20"]


def test_status_filter(store):
    assert {i.id for i in store.list_invoices(BIZ, DocumentStatus.OPEN)} == {"i-0098", "i-0104"}


def test_businesses_are_isolated(store):
    other_business(store)
    assert store.list_transactions("biz-other") == []
    assert [a.id for a in store.list_accounts("biz-other")] == ["b-acc"]
    assert "b-acc" not in {a.id for a in store.list_accounts(BIZ)}
    with pytest.raises(NotFoundError):
        store.get_account("biz-other", "a-ops")


def test_cannot_reference_another_business_account(store):
    other_business(store)
    stolen = Transaction(
        id="x1",
        business_id="biz-other",
        account_id="a-ops",  # belongs to biz-kopi
        date=date(2026, 9, 1),
        amount=Decimal("-10"),
        description="cross-business",
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.add_transaction(stolen)


def test_failed_import_leaves_nothing_behind(sample_import):
    store = Store(":memory:")
    broken = sample_import.model_copy(
        update={
            "transactions": [
                *sample_import.transactions,
                sample_import.transactions[0].model_copy(update={"account_id": "nope"}),
            ]
        }
    )
    with pytest.raises(sqlite3.IntegrityError):
        store.save_import(broken)
    with pytest.raises(NotFoundError):
        store.get_business(BIZ)


def test_update_document_revalidates(store):
    with pytest.raises(ValueError):
        store.update_document(BIZ, "bill", "b-1250", Decimal("9999"), DocumentStatus.OPEN)
    store.update_document(BIZ, "bill", "b-1250", Decimal("2880.00"), DocumentStatus.PAID)
    assert store.get_document(BIZ, "bill", "b-1250").status is DocumentStatus.PAID


def test_sum_and_latest_date(store):
    assert store.latest_transaction_date(BIZ) == date(2026, 9, 30)
    assert store.sum_transactions(BIZ, "a-res", date(2026, 9, 30)) == Decimal("2000.00")
    assert store.list_transactions(BIZ)[0].source is TransactionSource.IMPORTED
