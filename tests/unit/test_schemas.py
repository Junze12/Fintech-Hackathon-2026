"""Tests for the shared schema contract (src/copilot/schemas.py)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from copilot.schemas import (
    SGT,
    Account,
    Business,
    Counterparty,
    CounterpartyKind,
    DataCoverage,
    DocumentStatus,
    DomainResult,
    Driver,
    EligibilityMetric,
    EligibilityRule,
    Fee,
    FeeKind,
    FinancingProduct,
    Invoice,
    Operator,
    Payee,
    ProductType,
    RateType,
    RepaymentStructure,
    ScheduledPayment,
    Transaction,
    TransactionCategory,
    mask,
    sgd,
    untrusted_fields,
)


def txn(**overrides):
    fields = dict(
        id="t1",
        business_id="b1",
        account_id="a1",
        date=date(2026, 9, 1),
        amount="100.00",
        description="Payment from customer",
    )
    fields.update(overrides)
    return Transaction(**fields)


def invoice(**overrides):
    fields = dict(
        id="i1",
        business_id="b1",
        counterparty_id="c1",
        number="INV-001",
        issue_date=date(2026, 9, 1),
        due_date=date(2026, 9, 30),
        amount="500.00",
    )
    fields.update(overrides)
    return Invoice(**fields)


def product(**overrides):
    fields = dict(
        id="p1",
        lender="Example Bank",
        name="Working Capital Loan",
        type=ProductType.WORKING_CAPITAL_LOAN,
        min_amount="10000",
        max_amount="300000",
        min_term_months=6,
        max_term_months=60,
        rate_type=RateType.REDUCING_BALANCE,
        annual_rate_pct="7.5",
        repayment=RepaymentStructure.AMORTISING,
        typical_use="Day-to-day operating costs",
    )
    fields.update(overrides)
    return FinancingProduct(**fields)


# --- Money ------------------------------------------------------------------


@pytest.mark.parametrize("value", [12.5, 0.1, True])
def test_money_rejects_float_and_bool(value):
    with pytest.raises(ValidationError):
        txn(amount=value)


def test_money_rejects_more_than_two_decimal_places():
    with pytest.raises(ValidationError):
        txn(amount="12.345")


@pytest.mark.parametrize("value", ["12.30", 12, Decimal("-7.5")])
def test_money_accepts_str_int_decimal(value):
    assert txn(amount=value).amount == Decimal(str(value))


# --- Sign convention --------------------------------------------------------


def test_transaction_rejects_zero_amount():
    with pytest.raises(ValidationError):
        txn(amount="0")


def test_transaction_accepts_inflow_and_outflow():
    assert txn(amount="250.00").amount > 0
    assert txn(amount="-250.00").amount < 0


def test_category_groups_cover_every_category():
    for category in TransactionCategory:
        assert category.group  # raises KeyError if a category has no group


# --- Invoices and bills -----------------------------------------------------


def test_invoice_rejects_due_before_issue():
    with pytest.raises(ValidationError):
        invoice(due_date=date(2026, 8, 1))


def test_invoice_rejects_overpayment():
    with pytest.raises(ValidationError):
        invoice(amount_paid="600.00")


def test_paid_invoice_must_be_fully_paid():
    with pytest.raises(ValidationError):
        invoice(status=DocumentStatus.PAID, amount_paid="100.00")
    assert invoice(status=DocumentStatus.PAID, amount_paid="500.00").status is DocumentStatus.PAID


# --- Secrets ----------------------------------------------------------------


def test_account_number_never_leaks():
    account = Account(
        id="a1",
        business_id="b1",
        name="Operating",
        bank_name="Example Bank",
        account_number="123-456-7890",
        opening_balance="1000.00",
        opening_date=date(2026, 1, 1),
    )
    assert "7890" not in repr(account)
    assert "7890" not in account.model_dump_json()
    assert mask(account.account_number) == "••••7890"


def test_account_number_format_is_validated():
    with pytest.raises(ValidationError):
        Payee(id="p1", business_id="b1", name="X", account_number="abc", bank_name="B")


# --- Strictness -------------------------------------------------------------


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        txn(role="owner")


def test_models_are_immutable():
    t = txn()
    with pytest.raises(ValidationError):
        t.amount = Decimal("1")


# --- Financing --------------------------------------------------------------


def test_fee_needs_exactly_one_of_flat_or_pct():
    with pytest.raises(ValidationError):
        Fee(kind=FeeKind.PROCESSING)
    with pytest.raises(ValidationError):
        Fee(kind=FeeKind.PROCESSING, flat="100", pct="1")
    assert Fee(kind=FeeKind.PROCESSING, pct="1").pct == Decimal("1")


def test_product_rejects_inverted_ranges():
    with pytest.raises(ValidationError):
        product(min_amount="500000")
    with pytest.raises(ValidationError):
        product(min_term_months=72)


def test_eligibility_rule_threshold_types():
    rule = EligibilityRule(
        metric=EligibilityMetric.LOCAL_SHAREHOLDING_PCT,
        operator=Operator.GE,
        threshold="30",
        description="At least 30% local shareholding",
    )
    assert rule.threshold == Decimal("30")
    with pytest.raises(ValidationError):
        EligibilityRule(
            metric=EligibilityMetric.ANNUAL_REVENUE,
            operator=Operator.GE,
            threshold=True,
            description="bad",
        )
    with pytest.raises(ValidationError):
        EligibilityRule(
            metric=EligibilityMetric.REGISTERED_IN_SG,
            operator=Operator.GE,
            threshold=True,
            description="bad operator",
        )


# --- Untrusted text and personal data ---------------------------------------


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (Transaction, "description"),
        (Counterparty, "name"),
        (Payee, "name"),
        (Invoice, "notes"),
        (ScheduledPayment, "reference"),
    ],
)
def test_untrusted_text_is_discoverable(model, field):
    assert field in untrusted_fields(model)


def test_trusted_fields_are_not_marked():
    assert "amount" not in untrusted_fields(Transaction)
    assert "business_id" not in untrusted_fields(Transaction)


def test_business_has_no_personal_characteristics():
    forbidden = {"nationality", "gender", "religion", "age", "race", "date_of_birth"}
    assert forbidden.isdisjoint(Business.model_fields)


# --- Timestamps -------------------------------------------------------------


def test_timestamps_must_be_utc_plus_8():
    base = dict(
        id="s1",
        business_id="b1",
        payee_id="p1",
        from_account_id="a1",
        amount="100.00",
        pay_on=date(2026, 10, 5),
    )
    ok = ScheduledPayment(**base, created_at=datetime(2026, 10, 1, 9, 0, tzinfo=SGT))
    assert ok.created_at.utcoffset() == timedelta(hours=8)
    with pytest.raises(ValidationError):
        ScheduledPayment(**base, created_at=datetime(2026, 10, 1, 1, 0, tzinfo=UTC))
    with pytest.raises(ValidationError):
        ScheduledPayment(**base, created_at=datetime(2026, 10, 1, 9, 0))


# --- Domain result contract -------------------------------------------------


def test_domain_result_round_trips_through_json():
    result = DomainResult[Decimal](
        value=Decimal("0.42"),
        drivers=[Driver(label="COGS up", amount="-1200.50", detail="Supplier price rise")],
        data_coverage=DataCoverage(
            period_start=date(2026, 7, 1), period_end=date(2026, 9, 30), record_count=312
        ),
        warnings=["Cash basis used"],
    )
    restored = DomainResult[Decimal].model_validate_json(result.model_dump_json())
    assert restored == result


def test_counterparty_kind_values():
    assert {k.value for k in CounterpartyKind} == {"customer", "supplier", "both"}


# --- Money display ----------------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        (Decimal("1234.56"), "S$1,234.56"),
        (Decimal("-13260.76"), "-S$13,260.76"),
        (Decimal("0"), "S$0.00"),
        ("-18113.86", "-S$18,113.86"),
        (85000, "S$85,000.00"),
    ],
)
def test_sgd_display(amount, shown):
    assert sgd(amount) == shown
