"""What-if scenarios on cash_crunch: change forecast items, re-walk, compare with the base."""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from copilot.cashflow.forecast import forecast_13_weeks
from copilot.cashflow.scenarios import (
    AddMonthly,
    AddOneOff,
    Change,
    CollectOnTime,
    DelayPayment,
    DelayReceipt,
    PauseRecurring,
    ScenarioError,
    apply_changes,
    what_if,
)
from copilot.schemas import TransactionCategory as Cat


@pytest.fixture
def crunch(load_scenario):
    s = load_scenario("cash_crunch")
    return s, forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of)


def inv_id(s, number):
    return next(i.id for i in s.store.list_invoices(s.business_id) if i.number == number)


def bill_id(s, number):
    return next(b.id for b in s.store.list_bills(s.business_id) if b.number == number)


def test_delaying_one_invoice_moves_exactly_that_item(crunch):
    s, fc = crunch
    items, changed, _ = apply_changes(
        s.store, s.business_id, fc.value, [DelayReceipt(invoice_id=inv_id(s, "INV-1062"), days=30)]
    )
    assert len(changed) == 1
    assert (changed[0].from_date, changed[0].to_date) == (date(2026, 11, 10), date(2026, 12, 10))
    before = {(it.label, it.date) for it in fc.value.items}
    after = {(it.label, it.date) for it in items}
    assert before - after == {(changed[0].label, date(2026, 11, 10))}
    assert after - before == {(changed[0].label, date(2026, 12, 10))}


def test_scenario_diff_is_scenario_minus_base_and_base_is_untouched(crunch):
    s, fc = crunch
    base_items = list(fc.value.items)
    result = what_if(
        s.store, s.business_id, fc, [DelayReceipt(invoice_id=inv_id(s, "INV-1062"), days=30)]
    ).value
    assert fc.value.items == base_items
    for w in result.weeks:
        assert w.difference == w.scenario_end_balance - w.base_end_balance
    # S$51,283.20 is missing from weeks 7-10 (Nov 10 to Dec 10), then back.
    moved = Decimal("-51283.20")
    assert [w.difference for w in result.weeks] == [0] * 6 + [moved] * 4 + [0] * 3
    assert result.low_point_change == result.scenario_low.balance - result.base_low.balance


def test_collect_on_time_closes_the_november_breach(crunch):
    s, fc = crunch
    result = what_if(
        s.store, s.business_id, fc, [CollectOnTime(invoice_id=inv_id(s, "INV-1062"))]
    ).value
    assert result.base_first_below_zero == date(2026, 11, 5)
    assert result.scenario_first_below_zero == date(2026, 12, 6)
    assert result.changed_items[0].to_date == date(2026, 10, 19)  # its due date
    assert [(g.start, g.end) for g in result.gaps_closed] == [
        (date(2026, 11, 5), date(2026, 11, 9))
    ]
    assert result.gaps_new == [] and result.gaps_changed == []
    assert result.timing_only
    assert [(r.first_week, r.last_week, r.difference) for r in result.week_runs] == [
        (4, 6, Decimal("51283.20"))
    ]


def test_deeper_and_new_gaps(crunch):
    s, fc = crunch
    deeper = what_if(
        s.store, s.business_id, fc, [DelayReceipt(invoice_id=inv_id(s, "INV-1063"), days=10)]
    ).value
    (change,) = deeper.gaps_changed
    assert change.worse and change.after.lowest_balance == Decimal("-37291.21")
    assert [g.start for g in change.before] == [date(2026, 11, 5)]
    assert deeper.gaps_closed == [] and deeper.gaps_new == []

    hire = what_if(
        s.store,
        s.business_id,
        fc,
        [AddMonthly(amount=Decimal("-5000.00"), start=date(2026, 10, 1), label="new hire")],
    ).value
    assert not hire.timing_only
    assert [(g.start, g.end) for g in hire.gaps_new] == [(date(2026, 12, 20), date(2026, 12, 21))]
    assert len(hire.gaps_changed) == 3 and all(c.worse for c in hire.gaps_changed)


def test_customer_wide_delay_moves_open_and_expected_receipts(crunch):
    s, fc = crunch
    _, changed, notes = apply_changes(
        s.store, s.business_id, fc.value, [DelayReceipt(customer_id="c-bayfront", days=21)]
    )
    labels = [c.label for c in changed]
    assert any(label.startswith("Invoice INV-1062") for label in labels)
    assert any(label.startswith("Expected invoice from Bayfront") for label in labels)
    assert all(c.amount > 0 for c in changed)
    dropped = [c for c in changed if c.to_date is None]  # pushed past 2026-12-27
    assert dropped and any("drops out" in n for n in notes)


def test_bill_delay_and_new_costs(crunch):
    s, fc = crunch
    changes = [
        DelayPayment(bill_id=bill_id(s, "MFI-88120"), days=14),
        AddOneOff(amount=Decimal("-20000.00"), date=date(2026, 10, 7), label="new van"),
        AddMonthly(amount=Decimal("-5000.00"), start=date(2026, 10, 31), label="new hire"),
    ]
    items, _, _ = apply_changes(s.store, s.business_id, fc.value, changes)
    mfi = next(it for it in items if it.ref == bill_id(s, "MFI-88120"))
    assert mfi.date == date(2026, 11, 19)
    hire = [it.date for it in items if it.label == "new hire"]
    assert hire == [date(2026, 10, 31), date(2026, 11, 30)]  # Dec 31 is after the horizon
    result = what_if(s.store, s.business_id, fc, changes).value
    assert result.scenario_end_balance - result.base_end_balance == Decimal("-30000.00")


def test_pause_recurring(crunch):
    s, fc = crunch
    items, changed, _ = apply_changes(
        s.store,
        s.business_id,
        fc.value,
        [PauseRecurring(category=Cat.SOFTWARE, until=date(2026, 11, 30))],
    )
    assert [c.from_date for c in changed] == [date(2026, 10, 3), date(2026, 11, 3)]
    assert any(it.ref == "software" and it.date == date(2026, 12, 3) for it in items)
    with pytest.raises(ScenarioError):
        apply_changes(
            s.store,
            s.business_id,
            fc.value,
            [PauseRecurring(category=Cat.MARKETING, until=date(2026, 12, 1))],
        )


@pytest.mark.parametrize(
    "change",
    [
        DelayReceipt(invoice_id="inv-does-not-exist", days=5),
        DelayReceipt(customer_id="s-meridian", days=5),  # a supplier, not a customer
        DelayPayment(bill_id="bill-nope", days=5),
        AddOneOff(amount=Decimal("-1.00"), date=date(2027, 6, 1), label="outside horizon"),
    ],
)
def test_unknown_ids_and_dates_are_rejected_not_guessed(crunch, change):
    s, fc = crunch
    with pytest.raises(ScenarioError):
        apply_changes(s.store, s.business_id, fc.value, [change])


def test_ids_are_looked_up_within_the_session_business_only(store, sandbox):
    # The same store holds biz-kopi's invoices; asking as another business must not find them.
    fc = forecast_13_weeks(store, sandbox, "biz-kopi").value
    kopi_invoice = store.list_invoices("biz-kopi")[0].id
    with pytest.raises(ScenarioError, match="not found"):
        apply_changes(store, "biz-other", fc, [DelayReceipt(invoice_id=kopi_invoice, days=5)])


def test_change_validation():
    adapter = TypeAdapter(Change)
    assert isinstance(
        adapter.validate_python({"kind": "collect_on_time", "invoice_id": "x"}), CollectOnTime
    )
    for bad in [
        {"kind": "delay_receipt", "days": 5},  # neither invoice nor customer
        {"kind": "delay_receipt", "invoice_id": "a", "customer_id": "b", "days": 5},
        {"kind": "delay_payment", "bill_id": "b", "days": 0},
        {"kind": "add_one_off", "amount": "0.00", "date": "2026-10-10", "label": "x"},
        {"kind": "add_one_off", "amount": 5.5, "date": "2026-10-10", "label": "x"},  # float
        {"kind": "move_money", "amount": "1.00"},
    ]:
        with pytest.raises(ValidationError):
            adapter.validate_python(bad)
