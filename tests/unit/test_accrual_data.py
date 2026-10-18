"""Chunk 11: accrual inputs (adapter, store, generator) and their answer key.

The statements themselves are chunk 12. These tests check that the data chunk 12 will read
loads cleanly, is rejected with reasons when wrong, stays inside its business, and agrees with
ground_truth.json["accrual"] (whose own checks the generator asserts as it writes them).
"""

import shutil
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import pytest

from copilot.adapters.csv_folder import CsvFolderAdapter
from copilot.cashflow.forecast import forecast_13_weeks
from copilot.schemas import BalanceLine, TransactionCategory, balance_difference
from copilot.store import Store
from copilot.synthetic import SCENARIOS, generate, gst_in

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"

CRUNCH = SYNTHETIC_DIR / "cash_crunch"
B2B = SYNTHETIC_DIR / "concentrated_b2b"


@pytest.fixture(scope="module")
def crunch_import():
    return CsvFolderAdapter().load(CRUNCH)


# --- Adapter ----------------------------------------------------------------------------


def test_generated_accrual_files_load_without_rejects(crunch_import):
    r = crunch_import
    assert r.rejected == [] and r.warnings == []
    assert len(r.opening_balances) == len(BalanceLine)
    assert len(r.inventory_snapshots) == 13  # opening + 12 month-ends
    assert len(r.fixed_assets) == 3 and len(r.loans) == 1
    assert len(r.loan_schedule) == r.loans[0].term_months
    assert len(r.payroll_runs) == 12
    assert balance_difference(r.opening_balances) == 0
    assert all(i.gst > 0 for i in r.invoices)


def test_b2b_has_no_stock_or_loan():
    r = CsvFolderAdapter().load(B2B)
    assert r.rejected == [] and r.warnings == []
    assert r.inventory_snapshots == [] and r.loans == [] and r.loan_schedule == []
    assert len(r.fixed_assets) == 3 and len(r.payroll_runs) == 12


def test_folders_without_accrual_files_still_load_quietly(sample_import):
    # The hand-made sample has none of the new files: nothing is loaded, nothing is warned.
    assert sample_import.opening_balances == [] and sample_import.payroll_runs == []
    assert not any("opening_balances" in w for w in sample_import.warnings)
    assert all(i.gst == 0 for i in sample_import.invoices)


@pytest.fixture
def crunch_copy(tmp_path):
    folder = tmp_path / "crunch"
    shutil.copytree(CRUNCH, folder)
    return folder


def _append(path, line):
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(line + "\n")


def test_bad_accrual_rows_are_rejected_with_reasons(crunch_copy):
    _append(crunch_copy / "loan_schedule.csv", "TL-20817,61,2028-06-10,100.00,10.00,80.00,0.00")
    _append(crunch_copy / "loan_schedule.csv", "TL-99999,1,2028-06-10,100.00,10.00,90.00,0.00")
    _append(crunch_copy / "loan_schedule.csv", "TL-20817,1,2023-06-10,4200.00,1162.72,3037.28,0")
    _append(crunch_copy / "payroll_runs.csv", "2026-13,100,0,0,100,2026-12-27,2027-01-14")
    _append(crunch_copy / "payroll_runs.csv", "2026-01,100,5,5,100,2026-01-27,2026-02-14")
    _append(crunch_copy / "fixed_assets.csv", "fa-x,Bad asset,2024-01-01,100.00,200.00,12")
    _append(crunch_copy / "inventory_snapshots.csv", "2026-10-31,-5.00")
    result = CsvFolderAdapter().load(crunch_copy)
    reasons = " | ".join(r.reason for r in result.rejected)
    assert len(result.rejected) == 7, reasons
    assert "interest + principal must equal instalment" in reasons
    assert "loan_id 'TL-99999' not found in loans" in reasons
    assert "duplicate loan_id/instalment_no" in reasons
    assert "period" in reasons  # month 13
    assert "gross_pay must equal net_pay + employee_cpf" in reasons
    assert "residual_value must not exceed cost" in reasons
    assert "greater than or equal to 0" in reasons  # negative stock


def test_opening_balance_that_does_not_balance_is_warned(crunch_copy):
    path = crunch_copy / "opening_balances.csv"
    text = path.read_text(encoding="utf-8").replace("cash,176000.00", "cash,176100.00")
    path.write_text(text, encoding="utf-8")
    result = CsvFolderAdapter().load(crunch_copy)
    assert any("minus liabilities and equity is 100.00, not 0" in w for w in result.warnings)


def test_gst_must_be_less_than_the_amount(crunch_copy):
    path = crunch_copy / "invoices.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    cells = lines[1].split(",")
    cells[-1] = cells[5]  # gst = whole amount
    lines[1] = ",".join(cells)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = CsvFolderAdapter().load(crunch_copy)
    assert any("gst must be at least 0 and less than amount" in r.reason for r in result.rejected)


# --- Store ------------------------------------------------------------------------------


def test_store_round_trip_and_business_scoping(crunch_import):
    store = Store(":memory:")
    store.save_import(crunch_import)
    store.save_import(CsvFolderAdapter().load(B2B))
    crunch = crunch_import.business.id
    assert store.list_opening_balances(crunch) == crunch_import.opening_balances
    assert store.list_inventory_snapshots(crunch) == crunch_import.inventory_snapshots
    assert store.list_fixed_assets(crunch) == sorted(
        crunch_import.fixed_assets, key=lambda a: (a.acquired_on, a.id)
    )
    assert store.list_loans(crunch) == crunch_import.loans
    assert store.list_loan_schedule(crunch, "TL-20817") == crunch_import.loan_schedule
    assert store.list_payroll_runs(crunch) == crunch_import.payroll_runs
    assert store.list_invoices(crunch)[0].gst > 0
    # The other business sees only its own rows.
    assert store.list_loans("biz-clearpath") == []
    assert store.list_loan_schedule("biz-clearpath", "TL-20817") == []
    assert {a.id for a in store.list_fixed_assets("biz-clearpath")}.isdisjoint(
        {a.id for a in crunch_import.fixed_assets}
    )


# --- Generator and answer key ---------------------------------------------------------


@pytest.fixture(scope="module", params=sorted(SCENARIOS))
def truth(request):
    return generate(SCENARIOS[request.param], seed=42).ground_truth


def test_every_month_balances_and_cash_matches_the_bank(truth):
    accrual = truth["accrual"]
    assert len(accrual["months"]) == 12
    for month in accrual["months"].values():
        assert month["checks"] == {
            "balance_sheet_difference": "0.00",
            "closing_cash_minus_bank": "0.00",
        }
    last = accrual["months"]["2026-09"]["balance_sheet"]
    assert D(last["cash"]) == sum(D(v) for v in truth["closing_balances"].values())


def test_pnl_lines_add_up(truth):
    for month in truth["accrual"]["months"].values():
        p = month["pnl"]
        assert D(p["gross_profit"]) == D(p["revenue"]) - D(p["cost_of_sales"])
        opex = sum(D(v) for v in p["operating_expenses"].values())
        assert D(p["total_operating_expenses"]) == opex
        assert D(p["operating_profit"]) == D(p["gross_profit"]) - opex
        assert D(p["net_profit"]) == D(p["operating_profit"]) - D(p["interest"])


def test_gst_payments_equal_the_quarter_returns(truth):
    returns = truth["accrual"]["gst_returns"]
    paid = {
        "2025-Q3": "2025-10",
        "2025-Q4": "2026-01",
        "2026-Q1": "2026-04",
        "2026-Q2": "2026-07",
    }
    for quarter, month in paid.items():
        tax_paid = -D(truth["monthly_totals"][month]["by_category"]["tax"])
        assert tax_paid == D(returns[quarter]["net_payable"])
    # What is owed at the end of September is the return paid on 29 October.
    september = truth["accrual"]["months"]["2026-09"]["balance_sheet"]
    assert september["gst_payable"] == returns["2026-Q3"]["net_payable"]


def test_gst_is_nine_percent_of_the_inclusive_amount():
    assert gst_in(D("109.00")) == D("9.00")
    assert gst_in(D("42000.00")) == D("3467.89")  # 42000 x 9/109 = 3467.889...


def test_cash_crunch_loan_and_stock_story():
    truth = generate(SCENARIOS["cash_crunch"], seed=42).ground_truth["accrual"]
    loan = truth["loan"]
    assert loan["principal"] == "214656.45"  # what S$4,200 x 60 months repays at 6.5%
    september = truth["months"]["2026-09"]
    # The S$85,000 bulk stock bill (S$77,981.65 before GST) is bought but not yet sold.
    assert D(september["balance_sheet"]["inventory"]) > D("77981.65")
    assert D(september["pnl"]["purchases"]) > D(september["pnl"]["cost_of_sales"])


def test_loan_schedule_instalments_match_the_bank(crunch_import):
    schedule = {(r.due_date.year, r.due_date.month): r for r in crunch_import.loan_schedule}
    repayments = [t for t in crunch_import.transactions if "LOAN" in t.description and t.amount < 0]
    assert len(repayments) == 12
    for t in repayments:
        row = schedule[(t.date.year, t.date.month)]
        assert row.due_date == t.date and row.instalment == -t.amount


# --- Forecast uses the GST data -----------------------------------------------------------


def test_forecast_takes_the_october_gst_payment_from_the_documents(load_scenario):
    s = load_scenario("cash_crunch")
    fc = forecast_13_weeks(s.store, s.sandbox, s.business_id, s.as_of).value
    tax = [i for i in fc.items if i.ref == TransactionCategory.TAX.value]
    assert len(tax) == 1 and tax[0].date == date(2026, 10, 29)
    expected = s.truth["accrual"]["gst_returns"]["2026-Q3"]["net_payable"]
    assert tax[0].amount == -D(expected) == D("-9867.75")
    assert tax[0].label.startswith("GST return 2026-07-01 to 2026-09-30")
