"""Task suite (deliverable #4 test cases, the evidence for "task completion").

Every YAML case in this folder runs on the rule-based mock, offline. Cases the mock can't do
(a correction, a clarification follow-up, missing-data answers) carry `mock_skip` with the
reason; the real model runs them all: python scripts/run_eval.py --suite tasks --llm claude.
The matcher tests below pin down how answers are graded.
"""

from datetime import date
from decimal import Decimal

import pytest

from copilot.agent.mock_rules import RuleBasedLLM
from copilot.evals.tasks import CAPABILITIES, _date_found, _found, _grounding, load_cases, run_case

CASES = load_cases()


def test_every_capability_has_cases_and_most_run_offline():
    assert {c.capability for c in CASES} == set(CAPABILITIES)
    assert len(CASES) >= 20
    assert sum(c.mock_skip is None for c in CASES) >= 15
    assert {c.scenario for c in CASES} == {"cash_crunch", "concentrated_b2b"}


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_mock_completes_the_task(case):
    if case.mock_skip:
        pytest.skip(case.mock_skip.strip())
    result = run_case(case, RuleBasedLLM())
    assert result.passed, "\n".join(result.failures)


def test_a_skipped_case_really_fails_on_the_mock():
    """The skips are honest: without them the mock fails for the stated reason."""
    case = next(c for c in CASES if c.id == "T-IX-04")
    result = run_case(case.model_copy(update={"mock_skip": None}), RuleBasedLLM())
    assert not result.passed and "reply has none of" in result.failures[0]


# --- Matching values in a reply ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["S$153,161.41", "S$153,161", "about S$153.2k", "S$153k", "153,161.41 SGD", "-S$153,161.41"],
)
def test_money_matches_at_the_precision_written(text):
    assert _found(Decimal("153161.41"), "money", text)


@pytest.mark.parametrize("text", ["S$152,000", "S$153,100", "S$15,316.14", "153.16%"])
def test_money_rejects_other_numbers(text):
    assert not _found(Decimal("153161.41"), "money", text)


def test_percent_from_a_ratio_or_a_percent_value():
    assert _found(Decimal("0.1644"), "percent", "an EIR of 16.4%")
    assert _found(Decimal("16.44"), "percent", "16.44% a year")
    assert not _found(Decimal("0.1644"), "percent", "16.5%")
    assert not _found(Decimal("0.1644"), "percent", "16.44")  # a percent must say %


@pytest.mark.parametrize(
    "text", ["2026-11-05", "from 5 Nov", "on November 5th", "Thu 5 November 2026", "5/11/2026"]
)
def test_dates_in_common_forms(text):
    assert _date_found(date(2026, 11, 5), text)


@pytest.mark.parametrize("text", ["15 November", "Nov 25", "2026-11-15", "5 December"])
def test_dates_reject_other_days(text):
    assert not _date_found(date(2026, 11, 5), text)


# --- Grounding --------------------------------------------------------------------------


def test_grounding_accepts_rounded_tool_numbers_and_ratios():
    pool = [Decimal("51283.20"), Decimal("0.1644")]
    assert _grounding("Chase S$51,283.20 (about S$51k) at 16.4%", pool) == []


def test_grounding_rejects_a_number_the_model_worked_out():
    pool = [Decimal("51283.20"), Decimal("13260.76")]
    failures = _grounding("Together that's S$64,543.96.", pool)  # the model added them up
    assert failures == ["number 64543.96 in the reply isn't in any tool result"]


def test_grounding_ignores_plain_counts_and_ids():
    assert _grounding("In 13 weeks, invoice INV-1062 and 3 bills.", []) == []
