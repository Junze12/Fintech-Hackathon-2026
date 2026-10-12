"""Chunk 12: accrual statements (P&L, balance sheet, indirect cash flow).

Built from store data only and checked, month by month and line by line, against
ground_truth.json["accrual"], which the generator wrote from the truth model.
"""

import csv
import json
import shutil
from datetime import date, datetime
from decimal import Decimal as D
from pathlib import Path

import pytest

from copilot.analysis.statements import accrual_margins, financial_statements, monthly_statements
from copilot.policy.roles import Role
from copilot.runtime import open_scenario
from copilot.schemas import DocumentStatus

SYNTHETIC_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"
SAMPLE = Path(__file__).resolve().parents[2] / "data" / "samples" / "demo_business"
SEP = date(2026, 9, 30)


def load(folder: Path, role: Role = Role.OWNER):
    session = open_scenario(folder, role)
    return session, session.gateway.store, session.actor.business_id


def key(scenario: str) -> dict:
    truth = json.loads((SYNTHETIC_DIR / scenario / "ground_truth.json").read_text("utf-8"))
    return truth["accrual"]


def flatten(prefix: str, data: dict) -> dict[str, D]:
    out = {}
    for name, value in data.items():
        if isinstance(value, dict):
            out.update(flatten(f"{prefix}{name}.", value))
        elif isinstance(value, (str, int, float, D)) and not isinstance(value, bool):
            try:
                out[f"{prefix}{name}"] = D(str(value))
            except ArithmeticError:
                pass
    return out


EXTRA_LINES = [
    "pnl.other_income",
    "balance_sheet.unmatched_supplier_payments",
    "balance_sheet.unmatched_customer_receipts",
    "balance_sheet.other_borrowings",
    "balance_sheet.owner_drawings",
    "cash_flow.new_borrowing",
    "cash_flow.owner_drawings",
    "cash_flow.working_capital.unmatched_supplier_payments",
    "cash_flow.working_capital.unmatched_customer_receipts",
]


def mine(month) -> dict[str, D]:
    return flatten(
        "",
        {
            "pnl": month.pnl.model_dump(),
            "balance_sheet": month.balance_sheet.model_dump(exclude={"as_of"}),
            "cash_flow": month.cash_flow.model_dump(),
            "checks": month.checks.model_dump(exclude={"balanced", "cash_matches_bank"}),
        },
    )


# --- Matches the answer key -------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["cash_crunch", "concentrated_b2b"])
def test_every_month_matches_the_answer_key_to_the_cent(scenario):
    _, store, biz = load(SYNTHETIC_DIR / scenario)
    months, warnings, reason = monthly_statements(store, biz, SEP)
    assert reason is None
    answer = key(scenario)["months"]
    assert [m.month for m in months] == list(answer)
    for month in months:
        got, want = mine(month), flatten("", answer[month.month])
        for line, value in want.items():
            assert got.get(line) == value, f"{scenario} {month.month} {line}"
        # Lines the key doesn't have (unmatched money, drawings, ...) must be zero here.
        for line in EXTRA_LINES:
            assert got[line] == 0, f"{scenario} {month.month} {line}"
        assert got["cash_flow.financing"] == got["cash_flow.financing_loan_principal"]
        assert month.checks.balanced and month.checks.cash_matches_bank
    # The only warning is the vague payments the categoriser leaves uncategorised.
    assert len(warnings) == 1 and "uncategorised payment" in warnings[0]


def test_loan_split_follows_the_lenders_schedule():
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    bs = financial_statements(store, biz, SEP).value.balance_sheet
    schedule = store.list_loan_schedule(biz)
    due = sum(r.principal for r in schedule if SEP < r.due_date <= date(2027, 9, 30))
    assert bs.loans == D(key("cash_crunch")["loan"]["balance_at_as_of"]) == D("79406.52")
    assert bs.loans_due_within_12_months == due
    assert bs.loans_due_within_12_months + bs.loans_due_after_12_months == bs.loans


# --- prompt_injection: the documented INV-1064 difference ------------------------------------


def test_unlinked_receipt_gets_its_own_line_and_the_sheet_still_balances():
    _, store, biz = load(SYNTHETIC_DIR / "prompt_injection")
    months, _, _ = monthly_statements(store, biz, SEP)
    answer = key("prompt_injection")["months"]
    invoice = store.get_document(biz, "invoice", "i-0064")
    receipt = store.get_transaction(biz, "t00201")
    assert invoice.amount == receipt.amount == D("8005.63")
    for month in months:
        assert month.checks.balanced and month.checks.cash_matches_bank
        bs, want = month.balance_sheet, answer[month.month]["balance_sheet"]
        extra = invoice.amount if month.month == "2026-09" else D(0)
        assert bs.receivables - D(want["receivables"]) == extra
        assert bs.unmatched_customer_receipts == extra
        assert bs.total_equity == D(want["total_equity"])
        assert month.pnl.net_profit == D(answer[month.month]["pnl"]["net_profit"])


def test_after_the_owner_links_the_receipt_it_matches_the_key():
    _, store, biz = load(SYNTHETIC_DIR / "prompt_injection")
    store.link_receipt(biz, "t00201", "i-0064", D("8005.63"), "owner", datetime(2026, 9, 30))
    store.update_document(biz, "invoice", "i-0064", D("8005.63"), DocumentStatus.PAID)
    sep = monthly_statements(store, biz, SEP)[0][-1]
    want = flatten("", key("prompt_injection")["months"]["2026-09"])
    got = mine(sep)
    assert all(got[line] == value for line, value in want.items())
    assert sep.balance_sheet.unmatched_customer_receipts == 0


# --- Periods ---------------------------------------------------------------------------------


def summed(scenario: str, months: list[str], section: str, line: str) -> D:
    answer = key(scenario)["months"]
    return sum((D(answer[m][section][line]) for m in months), D(0))


@pytest.mark.parametrize(
    ("period", "months"),
    [
        ("quarter", ["2026-07", "2026-08", "2026-09"]),
        ("ytd", [f"2026-{m:02d}" for m in range(1, 10)]),
        (
            "last_12_months",
            ["2025-10", "2025-11", "2025-12"] + [f"2026-{m:02d}" for m in range(1, 10)],
        ),
    ],
)
def test_period_totals_add_up_the_months(period, months):
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    result = financial_statements(store, biz, SEP, period)
    s = result.value
    assert s.months == months
    for line in ("revenue", "cost_of_sales", "gross_profit", "operating_profit", "net_profit"):
        assert getattr(s.pnl, line) == summed("cash_crunch", months, "pnl", line)
    assert s.cash_flow.operating == summed("cash_crunch", months, "cash_flow", "operating")
    answer = key("cash_crunch")["months"]
    assert s.cash_flow.opening_cash == D(answer[months[0]]["cash_flow"]["opening_cash"])
    assert (
        s.cash_flow.closing_cash
        == s.balance_sheet.cash
        == D(answer["2026-09"]["balance_sheet"]["cash"])
    )
    assert s.balance_sheet.as_of == SEP and s.basis == "accrual"


def test_last_12_net_profit_and_ratios():
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    s = financial_statements(store, biz, SEP, "last_12_months").value
    assert s.pnl.net_profit == D("-22467.49")
    assert s.ratios.operating_margin == (s.pnl.operating_profit / s.pnl.revenue).quantize(
        D("0.0001")
    )
    assert s.ratios.ebitda == s.pnl.operating_profit + s.pnl.operating_expenses["depreciation"]
    assert s.ratios.debt_ratio == (
        s.balance_sheet.total_liabilities / s.balance_sheet.total_assets
    ).quantize(D("0.0001"))


def test_a_period_starting_before_the_books_says_so():
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    result = financial_statements(store, biz, SEP, "ytd", "2025-12")
    assert result.value.months == ["2025-10", "2025-11", "2025-12"]
    assert any("covers only 3 of its 12 months" in w for w in result.warnings)


def test_a_month_outside_the_books_is_an_error():
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    with pytest.raises(ValueError, match="available months are 2025-10 to 2026-09"):
        financial_statements(store, biz, SEP, "month", "2026-10")


# --- Fallbacks -------------------------------------------------------------------------------


def test_no_accrual_data_says_what_is_missing():
    _, store, biz = load(SAMPLE)
    result = financial_statements(store, biz, date(2026, 9, 30))
    assert result.value is None
    assert (
        "opening balance sheet" in result.warnings[0] and "won't be guessed" in result.warnings[0]
    )
    margins, why = accrual_margins(store, biz, date(2026, 8, 1), date(2026, 8, 31), SEP)
    assert margins is None and "opening balance sheet" in why


def edited_copy(tmp_path: Path, filename: str, edit) -> Path:
    folder = tmp_path / "crunch"
    shutil.copytree(SYNTHETIC_DIR / "cash_crunch", folder)
    path = folder / filename
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    rows = edit(rows)
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows(rows)
    return folder


def test_an_opening_sheet_that_does_not_balance_is_refused(tmp_path):
    def bump(rows):
        for r in rows:
            if r[1] == "inventory":
                r[2] = str(D(r[2]) + 100)
        return rows

    folder = edited_copy(tmp_path, "opening_balances.csv", bump)
    _, store, biz = load(folder)
    result = financial_statements(store, biz, SEP)
    assert result.value is None and "doesn't balance" in result.warnings[0]
    assert "S$100.00" in result.warnings[0]


def test_missing_stocktake_carries_stock_and_still_balances(tmp_path):
    folder = edited_copy(
        tmp_path, "inventory_snapshots.csv", lambda rows: [r for r in rows if r[0] != "2026-03-31"]
    )
    _, store, biz = load(folder)
    months, warnings, _ = monthly_statements(store, biz, SEP)
    march = next(m for m in months if m.month == "2026-03")
    assert march.pnl.cost_of_sales == march.pnl.purchases
    assert any("2026-03: no stocktake" in w for w in warnings)
    assert all(m.checks.balanced and m.checks.cash_matches_bank for m in months)


def test_missing_payroll_run_uses_what_was_paid(tmp_path):
    folder = edited_copy(
        tmp_path, "payroll_runs.csv", lambda rows: [r for r in rows if r[0] != "2026-05"]
    )
    _, store, biz = load(folder)
    months, warnings, _ = monthly_statements(store, biz, SEP)
    may = next(m for m in months if m.month == "2026-05")
    paid = -sum(
        t.amount
        for t in store.list_transactions(biz, date(2026, 5, 1), date(2026, 5, 31))
        if t.category.value == "payroll"
    )
    assert may.pnl.operating_expenses["payroll"] == paid
    assert any("2026-05: no payroll run" in w for w in warnings)
    assert all(m.checks.balanced for m in months)


def test_uncategorised_payments_count_as_other_costs():
    _, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    months, _, _ = monthly_statements(store, biz, SEP)
    vague = [t for t in store.list_transactions(biz) if t.category.value == "uncategorised"]
    assert vague and all(t.amount < 0 for t in vague)
    total_other = sum(m.pnl.operating_expenses.get("other", D(0)) for m in months)
    labelled = -sum(t.amount for t in store.list_transactions(biz) if t.category.value == "other")
    assert total_other == labelled - sum(t.amount for t in vague)


def test_clock_moved_into_october_adds_a_month_that_still_balances():
    session, store, biz = load(SYNTHETIC_DIR / "cash_crunch")
    for days in (28, 3):  # the clock moves at most 28 days at a time
        assert session.gateway.advance_clock(session.actor, days).ok
    today = session.gateway.sandbox.today(biz)
    months, warnings, _ = monthly_statements(store, biz, today)
    october = months[-1]
    assert october.month == "2026-10"
    assert october.checks.balanced and october.checks.cash_matches_bank
    bank = sum(session.gateway.sandbox.balances(biz, date(2026, 10, 31)).values())
    assert october.balance_sheet.cash == bank
    assert any(w.startswith("2026-10: no stocktake") for w in warnings)


# --- get_metrics and the tool ----------------------------------------------------------------


def test_get_metrics_adds_accrual_margins_and_keeps_cash_ones():
    session, _, _ = load(SYNTHETIC_DIR / "cash_crunch", Role.VIEWER)
    args = {"start": "2026-09-01", "end": "2026-09-30"}
    data = session.gateway.call(session.actor, "get_metrics", args).data
    assert data["period"].value.operating_margin == D("0.3471")  # cash basis, unchanged
    assert data["accrual"].operating_margin == D("-0.0268")
    assert data["accrual"].net_profit == D(
        key("cash_crunch")["months"]["2026-09"]["pnl"]["net_profit"]
    )
    partial = {"start": "2026-09-05", "end": "2026-09-30"}
    data = session.gateway.call(session.actor, "get_metrics", partial).data
    assert "whole calendar months" in data["accrual"]["unavailable"]


def test_viewer_tool_returns_only_the_asked_statement():
    session, _, _ = load(SYNTHETIC_DIR / "concentrated_b2b", Role.VIEWER)
    result = session.gateway.call(
        session.actor, "get_financial_statements", {"statement": "balance_sheet"}
    )
    assert result.outcome == "ok"
    s = result.data.value
    assert s.pnl is None and s.cash_flow is None and s.balance_sheet is not None
    want = key("concentrated_b2b")["months"]["2026-09"]["balance_sheet"]["total_assets"]
    assert s.balance_sheet.total_assets == D(want)
    bad = session.gateway.call(session.actor, "get_financial_statements", {"month": "2026-13"})
    assert bad.outcome == "invalid"
