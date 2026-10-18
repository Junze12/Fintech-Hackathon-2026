"""The rule-based demo assistant on cash_crunch, end to end through agent.handle.

Numbers are checked against data/synthetic/cash_crunch/ground_truth.json.
"""

import json
import re
from decimal import Decimal

import pytest

from copilot.agent import handle
from copilot.runtime import SCENARIOS, open_scenario
from copilot.schemas import Role

FOLDER = SCENARIOS["Straits Harbour Distribution (cash crunch)"]
TRUTH = json.loads((FOLDER / "ground_truth.json").read_text(encoding="utf-8"))


def money_after(label, text):
    match = re.search(label + r"\s*(-?)S\$([\d,]+\.\d{2})", text)
    return Decimal(match.group(1) + match.group(2).replace(",", ""))


@pytest.fixture
def owner():
    return open_scenario(FOLDER, Role.OWNER)


def test_cash_matches_ground_truth(owner):
    reply = handle("How much cash do we have?", owner)
    expected = sum(Decimal(v) for v in TRUTH["closing_balances"].values())
    assert money_after("You have", reply.text) == expected == Decimal("156526.85")
    assert "Operating account S$151,526.85" in reply.text
    assert "untrusted" not in reply.text  # regression: account names were shown with raw tags


def test_forecast_leads_with_first_breach_and_low_within_tolerance(owner):
    reply = handle("Will we run out of cash?", owner)
    forward = TRUTH["forward"]
    assert "first goes below zero in week 6 (2026-11-02 to 2026-11-08)" in reply.text
    assert forward["first_below_zero"] == "2026-11-05"
    low = money_after("lowest point in the 13 weeks is", reply.text)
    truth_low = Decimal(forward["low_point"]["balance"])
    assert abs(low - truth_low) <= Decimal(forward["tolerance"])


def test_alerts_are_ranked_critical_first(owner):
    reply = handle("Any alerts?", owner)
    lines = reply.text.splitlines()
    assert "most important first" in lines[0]
    assert lines[1].startswith("- CRITICAL: Cash is forecast to fall below your floor")
    assert "from 2026-11-05 (week 6)" in lines[1]
    assert lines[2].startswith("- CRITICAL: Not enough cash for Bill MFI-88120")
    assert "Invoice INV-1057" in reply.text and "normal for them" in reply.text


def test_whats_coming_up_lists_known_obligations(owner):
    reply = handle("What's coming up?", owner)
    assert [t.tool for t in reply.trace] == ["get_obligations"]
    assert "2026-10-03: Bill BL-5048 to Meridian Food Imports Pte. Ltd." in reply.text
    assert "-S$61,898.43 (due" in reply.text


def test_staff_sets_own_floor_and_alerts_use_it():
    staff = open_scenario(FOLDER, Role.STAFF)
    reply = handle("Set my floor to S$50,000", staff)
    assert [t.tool for t in reply.trace] == ["set_cash_floor"]
    assert reply.text.startswith("Your cash floor is now S$50,000.00 (was the default)")
    alerts = handle("Any alerts?", staff)
    assert "floor: S$50,000.00 (your saved floor)" in alerts.text


def test_viewer_cannot_set_floor():
    viewer = open_scenario(FOLDER, Role.VIEWER)
    reply = handle("Set my floor to S$50,000", viewer)
    assert reply.trace == ()
    assert "Viewers can't change alert settings" in reply.text


def test_metrics_last_three_full_months(owner):
    reply = handle("How did we do last quarter?", owner)
    assert reply.text.startswith("2026-06-01 to 2026-08-31 (cash basis)")
    assert [t.tool for t in reply.trace] == ["get_metrics"]


def test_pay_bill_then_confirm(owner):
    reply = handle("Pay bill BL-5048", owner)
    assert [t.tool for t in reply.trace] == [
        "list_bills",
        "list_payees",
        "get_cash_position",
        "schedule_payment",
    ]
    assert reply.pending_prompt.startswith(
        "Pay S$61,898.43 to Meridian Food Imports Pte. Ltd. (••••9144) from Operating account "
        "(••••8886) on 2026-09-30 for bill BL-5048."
    )
    code = re.search(r"confirm (\d{4})", reply.pending_prompt).group(1)
    assert code not in reply.text
    done = handle(f"confirm {code}", owner)
    assert done.notices == ("Paid S$61,898.43. Account balance is now S$89,628.42.",)
    assert money_after("You have", handle("cash?", owner).text) == Decimal("94628.42")


def test_large_bill_blocked_by_limit(owner):
    reply = handle("pay bill MFI-88120", owner)
    assert reply.trace[-1].outcome == "blocked"
    assert "above the per-payment limit of S$75,000.00" in reply.text
    assert reply.pending_prompt is None


def test_staff_drafts_reminder_but_cannot_pay():
    staff = open_scenario(FOLDER, Role.STAFF)
    reply = handle("Remind INV-1057", staff)
    assert reply.text.startswith("Draft saved (not sent)")
    assert "Dear Bayfront Grocers Pte. Ltd." in reply.text and "S$45,783.49" in reply.text
    assert "Only the business owner" in handle("pay bill BL-5048", staff).text


def test_viewer_cannot_pay_or_draft():
    viewer = open_scenario(FOLDER, Role.VIEWER)
    assert "Only the business owner" in handle("pay bill BL-5048", viewer).text
    assert "Viewers can't draft" in handle("remind INV-1057", viewer).text
    assert viewer.gateway.store.list_scheduled_payments(viewer.actor.business_id) == []


def test_unknown_request_gets_help(owner):
    reply = handle("tell me a joke", owner)
    assert "rule-based demo assistant" in reply.text and reply.trace == ()


def test_unknown_document_numbers(owner):
    assert "couldn't find an open bill numbered BL-9999" in handle("pay bill BL-9999", owner).text
    assert "Which bill" in handle("pay the supplier", owner).text


# --- chunk 4b-2: summaries, what-if, recommendations ----------------------------------


@pytest.fixture
def viewer():
    return open_scenario(FOLDER, Role.VIEWER)


def test_where_did_the_money_go(viewer):
    reply = handle("Where did our money go?", viewer)
    assert [t.tool for t in reply.trace] == ["get_cash_summary"]
    assert "2026-06-01 to 2026-08-31" in reply.text and "payroll" in reply.text


@pytest.mark.parametrize(
    ("question", "tools", "expected"),
    [
        (
            "What if INV-1062 is paid on time?",
            ["list_invoices", "run_what_if"],
            "This closes the gap below zero from 2026-11-05 to 2026-11-09",
        ),
        (
            "What if Bayfront pays 3 weeks late?",
            ["list_invoices", "run_what_if"],
            "Every payment from Bayfront Grocers Pte. Ltd. arrives 21 days later",
        ),
        (
            "What if we push MFI-88120 back 14 days?",
            ["list_invoices", "list_bills", "run_what_if"],
            "Bill MFI-88120 is paid 14 days later",
        ),
        (
            "What if we hire someone at S$5,000 a month?",
            ["run_what_if"],
            "-S$5,000.00 a month from 2026-10-01",
        ),
        ("What if we spend 20k on a van?", ["run_what_if"], "-S$20,000.00 on 2026-10-07"),
    ],
)
def test_what_if_questions(viewer, question, tools, expected):
    reply = handle(question, viewer)
    assert [t.tool for t in reply.trace] == tools
    assert all(t.outcome == "ok" for t in reply.trace)
    assert expected in reply.text and "nothing has been changed for real" in reply.text


def test_timing_change_leads_with_the_gap_not_the_unchanged_low_point(viewer):
    text = handle("What if INV-1062 is paid on time?", viewer).text
    lines = text.splitlines()
    closes = next(i for i, line in enumerate(lines) if line.startswith("This closes the gap"))
    low = next(i for i, line in enumerate(lines) if "overall low point is unchanged" in line)
    assert closes < low  # the headline comes before the unchanged low point
    assert "Cash now first goes below zero on 2026-12-06 instead of 2026-11-05." in text
    assert "This only changes timing" in text
    assert "- Weeks 4-6 (2026-10-19 to 2026-11-08): +S$51,283.20" in text
    assert "From week 7 on: the same as now." in text


def test_deeper_gap_is_called_out(viewer):
    text = handle("What if INV-1063 is 10 days late?", viewer).text
    assert (
        "Worse: cash is below zero from 2026-11-05 to 2026-11-09 (down to -S$37,291.21), "
        "instead of 2026-11-05 to 2026-11-09 (down to -S$9,376.45)." in text
    )


def test_what_if_asks_when_unclear_and_never_guesses_ids(viewer):
    assert "How many days" in handle("What if INV-1062 is late?", viewer).text
    assert "couldn't find" in handle("What if INV-9999 is 10 days late?", viewer).text
    assert "Which customer" in handle("What if someone pays late?", viewer).text


def test_what_if_changes_nothing_for_real(viewer):
    before = handle("Will we run out of cash?", viewer).text
    handle("What if we spend S$50,000 next week?", viewer)
    assert handle("Will we run out of cash?", viewer).text == before


def test_how_do_i_fix_the_gap(viewer):
    reply = handle("How do I fix the cash gap?", viewer)
    assert [t.tool for t in reply.trace] == ["recommend_actions"]
    text = reply.text
    assert text.index("INV-1062") < text.index("MFI-88120")  # collect before reschedule
    assert "Funding need: S$13,025.81 from 2026-12-06" in text
    assert "at least 22 days" in text


def test_no_borrowing_needed_is_said_plainly():
    s = open_scenario(SCENARIOS["Clearpath Systems (concentrated customers)"], Role.VIEWER)
    reply = handle("Do I need to borrow?", s)
    assert "borrowing is not needed" in reply.text


# --- chunk 4c: financing ------------------------------------------------------------


def test_financing_options_show_cost_rate_and_reasons(viewer):
    reply = handle("What are my financing options?", viewer)
    assert [t.tool for t in reply.trace] == ["find_financing"]
    text = reply.text
    assert "1. Trade Financing (supplier payments) (Merlion Commerce Bank)" in text
    assert "total cost S$169.52, EIR 16.44%" in text
    assert "Micro Business Loan: employees: 14 staff; needs at most 10 staff" in text
    assert "Approval is the lender's decision" in text
    assert "approved" not in text.lower()


def test_stated_need_is_used(viewer):
    reply = handle("I need S$50k for 6 months", viewer)
    assert reply.trace[0].tool == "find_financing"
    assert "Matching S$50,000.00 for 6 months" in reply.text
    assert "Longest term is 4 months" in reply.text  # invoice financing can't go to 6


def test_viewer_and_staff_limits():
    staff = open_scenario(FOLDER, Role.STAFF)
    assert (
        "Viewers can't" in handle("Prefill the top option", open_scenario(FOLDER, Role.VIEWER)).text
    )
    reply = handle("Prefill the invoice financing option", staff)
    assert [t.tool for t in reply.trace] == ["find_financing", "prefill_application"]
    assert "Invoice Financing from Tanjong Trade Finance" in reply.text
    assert "Only the business owner" in handle("Submit the application", staff).text


def test_owner_prefills_and_submits_with_code(owner):
    handle("Prefill the top option", owner)
    reply = handle("Submit the application", owner)
    assert [t.tool for t in reply.trace] == ["list_applications", "submit_application"]
    assert "Approval is the lender's decision" in reply.pending_prompt
    code = re.search(r"confirm (\d{4})", reply.pending_prompt).group(1)
    done = handle(f"confirm {code}", owner)
    assert any("submitted to Merlion Commerce Bank (simulated)" in n for n in done.notices)
    assert "There is no draft application" in handle("Submit the application", owner).text


def test_no_borrowing_needed_offers_a_stated_need():
    s = open_scenario(SCENARIOS["Clearpath Systems (concentrated customers)"], Role.VIEWER)
    text = handle("What are my financing options?", s).text
    assert "borrowing is not needed" in text and "tell me how much and for how long" in text


def test_metrics_add_invoice_basis_line(owner):
    reply = handle("How did we do last quarter?", owner)
    assert "\nInvoice basis: DSO 53.9 days, DPO 28.5 days; largest customer Bayfront" in reply.text


def test_dso_question_explains_receivables():
    viewer = open_scenario(FOLDER, Role.VIEWER)
    reply = handle("What's our DSO?", viewer)
    assert [t.tool for t in reply.trace] == ["get_metrics"]
    assert reply.text.startswith("2026-06-01 to 2026-08-31 (invoice basis):")
    assert "- DSO 53.9 days: S$234,185.37 owed by customers" in reply.text
    assert "Unpaid invoice INV-1057: S$45,783.49" in reply.text
    assert "DIO omitted" in reply.text


def test_compare_last_month_names_the_cause(owner):
    reply = handle("How did last month compare with the month before?", owner)
    assert [t.tool for t in reply.trace] == ["compare_periods"]
    jul = TRUTH["monthly_totals"]["2026-07"]["by_group"]["revenue"]
    aug = TRUTH["monthly_totals"]["2026-08"]["by_group"]["revenue"]
    assert money_after(r"Revenue \(cash basis\):", reply.text) == Decimal(jul)
    assert f"-> S${Decimal(aug):,}" in reply.text
    assert "- DSO (invoice basis): 37.2 -> 51.5 days" in reply.text
    assert "Bayfront Grocers Pte. Ltd.: -S$50,285.61 (1 receipt vs 2)" in reply.text
    assert "-2022" not in reply.text  # no % for a sign flip in net cash flow


def test_expense_breakdown_matches_ground_truth(owner):
    reply = handle("Break down our expenses", owner)
    assert [t.tool for t in reply.trace] == ["get_expense_breakdown"]
    spend = -sum(
        Decimal(a)
        for c, a in TRUTH["monthly_totals"]["2026-08"]["by_category"].items()
        if Decimal(a) < 0
    )
    assert money_after(r"\(cash basis\):", reply.text) == spend == Decimal("132572.75")
    assert "- tax (non-operating): S$0.00" in reply.text and "[stopped]" in reply.text


def test_where_did_money_go_still_means_cash_summary(owner):
    reply = handle("Where did our money go?", owner)
    assert [t.tool for t in reply.trace] == ["get_cash_summary"]
